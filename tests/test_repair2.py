import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_repair2.py —— 第二批修复（8 个漏洞里的 2/3/4/5/7/8）

判据（用户 10-31 定的）：
  ① 疤不是终点：充值之后**自动**修（不需要上层下令）
  ② heal 一轮能修多道伤
  ③ 反应压过反射要付费 + 留痕
  ④ 有疤的路径要**真的绕开**（不是只调参数）
  ⑤ 通道连续失败 -> 受损（可修），不是死
  ⑥ die() 只留接口，根因是"单体无法经历死亡"
"""

import importlib.util
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
            "dead_channels": [], "channel_fails": {}}


print("=" * 64)
print("① 疤不是终点：有钱了它自己修（不用上层下令）")
print("=" * 64)
st = fresh()
l0._add_scar(st, "api_error", 0.5)
check("先是疤", len(l0.scars_of(st)) == 1)

r = l0.heal(st, balance=100.0)          # 有钱了，自动跑 heal
check("自动修疤成功", r["ok"] and not l0.scars_of(st), f"({r['why']}, 花 {r['cost']})")

print()
print("=" * 64)
print("② 一轮修多道伤")
print("=" * 64)
st = fresh()
for _ in range(3):
    l0.add_wound(st, "tool_error", 0.2, 10)
r = l0.heal(st, balance=100.0, max_rounds=3)
check("三道伤都修了", len(st["wounds"]) == 0, f"(剩 {len(st['wounds'])}, 花 {r['cost']})")

print()
print("=" * 64)
print("③ 反应压过反射 → 付费 + 留痕")
print("=" * 64)
st = fresh()
fee = l2.charge_response(st, ["max_tokens", "temperature"])
check("收费了", fee["charged"] and fee["cost"] > 0, f"(¥{fee['cost']})")
check("留痕", len(st.get("override_log") or []) == 1)
check("记了伤口", any(w["kind"] == "self_override" for w in st["wounds"]))
fee2 = l2.charge_response(st, [])
check("没压过就不收费", not fee2["charged"])

print()
print("=" * 64)
print("④ 有疤的路径真的绕开")
print("=" * 64)
st = fresh()
check("没疤 → 通", l2.path_allowed(st, "tool_error"))
l0._add_scar(st, "tool_error", 0.3)
check("有疤 → 不通", not l2.path_allowed(st, "tool_error"))
check("列出所有被堵的路", l2.blocked_paths(st) == ["tool_error"])

print()
print("=" * 64)
print("⑤ 通道连续失败 → 受损（可修）")
print("=" * 64)
st = fresh()
for i in range(l0.CHANNEL_FAIL_LIMIT):
    l0.note_channel_failure(st, "tool")
check("五次后受损", not l0.channel_alive(st, "tool"), f"(失败 {st['channel_fails']['tool']} 次)")
check("其他通道没事", l0.channel_alive(st, "vision"))
r = l0.repair_channel(st, "tool", balance=100.0)
check("能修回来", r["ok"] and l0.channel_alive(st, "tool"), f"({r['why']})")
check("失败计数清零", st["channel_fails"]["tool"] == 0)

print()
print("=" * 64)
print("⑥ 死亡：只留接口，根因写对了")
print("=" * 64)
try:
    l0.die(fresh())
    check("应抛错", False)
except NotImplementedError as e:
    msg = str(e)
    check("提到群体属性", "群体" in msg, f"({msg[:40]}…)")

print()
print("=" * 64)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 64)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
