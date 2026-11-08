import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_avoid.py —— ④ 每种疤都有自己的绕法

用户 10-31 定的（他的痛点）：
  "如果它知道我这里有疤，它就会避开，就不会崩那么多次。
   等疤修好了，那没关系了，它又能用这只手。"
"""

import importlib.util
import io
import os

BASE = SRC_DIR


def load(n):
    spec = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l0 = load("l0_sense")
l2 = load("l2_ownership")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


def fresh():
    return {"wounds": [], "scars": [], "sens": {}, "pain_pool": {"kinds": {}},
            "spend": {"date": "2026-10-31", "today_cny": 0.0, "history": []},
            "intero": {}, "learned": {}, "trace": [], "identity": {},
            "dead_channels": [], "channel_fails": {}, "balance_history": [],
            "external_history": {}, "messages": [], "maintenance_budget": 0.1}


print("=" * 66)
print("① 没疤 → 一点不动（不乱紧张）")
print("=" * 66)
st = fresh()
base = {"max_tokens": 800, "temperature": 0.7}
p = l2.apply_avoid(st, base)
check("参数不变", p == base, f"({p})")
check("没有绕开记录", "avoid_applied" not in p)

print()
print("=" * 66)
print("② api_error 有疤 → 请求自动收紧（这就是不崩的原因）")
print("=" * 66)
st = fresh()
l0._add_scar(st, "api_error", 0.8)
plan = l2.avoid_plan(st)
check("识别出 api_error 的绕法", "api_error" in plan, f"({list(plan)})")

p = l2.apply_avoid(st, base)
check("长度减半", p["max_tokens"] == 400, f"(800 → {p['max_tokens']})")
check("温度降低", p["temperature"] < base["temperature"], f"(0.7 → {p['temperature']})")
check("要先查余额", p.get("precheck_balance") is True)
check("记了绕开动作", p.get("avoid_applied") == ["api_error→请求收紧"], f"({p.get('avoid_applied')})")

print()
print("=" * 66)
print("③ tool_error 有疤 → 不调工具")
print("=" * 66)
st = fresh()
l0._add_scar(st, "tool_error", 0.3)
p = l2.apply_avoid(st, base)
check("被标成 block_tool", p.get("block_tool") is True)
check("tool 那条路不通", not l2.path_allowed(st, "tool_error"))

print()
print("=" * 66)
print("④ file_corrupt 有疤 → 存的时候多备份 + 验证")
print("=" * 66)
st = fresh()
l0._add_scar(st, "file_corrupt", 0.5)
check("要求多备份", l2.should_extra_backup(st) is True)

import shutil
import tempfile
tmp = tempfile.mkdtemp()
sf = os.path.join(tmp, "s.json")
bf = os.path.join(tmp, "s.backup.json")
io.open(bf, "w", encoding="utf-8").write("{}")      # 先有个旧备份
made = l2.maintain(st, sf, bf)
check("多备份+验证执行了", any("extra_backup" in m for m in made), f"({made})")

print()
print("=" * 66)
print("⑤ 疤修好了 → 立刻恢复正常（又能用这只手）")
print("=" * 66)
st = fresh()
l0._add_scar(st, "api_error", 0.8)
p1 = l2.apply_avoid(st, base)
check("有疤时收紧", p1["max_tokens"] == 400)

r = l0.fix_scar(st, "api_error", balance=100.0)
check("疤修掉了", r["ok"] and not l0.scars_of(st))

p2 = l2.apply_avoid(st, base)
check("修好后恢复原样", p2 == base, f"({p2})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 用完删掉临时目录（别再往工作区里留垃圾）
try:
    shutil.rmtree(tmp, ignore_errors=True)
except Exception:
    pass

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
