import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_repair.py —— 修复 / 瘢痕 / 双账本 / 局部死亡（10-31）

判据（用户拍的）：
  ① 修复是**第一反应**，且扣**同一个体力池**（不是单开池子）
  ② 修不好 → 留疤（永久）
  ③ assisted 修疤 → 疤**彻底消失**
  ④ 双账本：造物者的错也算受损，但不学成"世界危险"
  ⑤ 有疤才代偿（绕开），没疤不乱紧张
  ⑥ 局部死亡：通道永久 0；整体死只留接口
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
            "intero": {}, "learned": {}, "trace": [], "identity": {}}


print("=" * 64)
print("① 修复是第一反应，且扣同一口锅")
print("=" * 64)
st = fresh()
l0.add_wound(st, "api_error", 0.5, 30)
before_spend = st["spend"]["today_cny"]
r = l0.heal(st, balance=100.0)
check("修好了", r["ok"], f"({r['why']}, 花了 {r['cost']})")
check("伤消失", len(st["wounds"]) == 0, f"(剩 {len(st['wounds'])})")
check("花了钱（同一个池子）", st["spend"]["today_cny"] > before_spend,
      f"({before_spend:.3f} → {st['spend']['today_cny']:.3f})")

print()
print("=" * 64)
print("② 修不起 → 留疤（永久）")
print("=" * 64)
st = fresh()
l0.add_wound(st, "api_error", 0.9, 30)
r = l0.heal(st, balance=0.001)
check("修失败", not r["ok"], f"({r['why']})")
check("留了一道疤", len(l0.scars_of(st)) == 1, f"({[s['kind'] for s in l0.scars_of(st)]})")
check("疤是永久的（不吃时间）", all(not s.get("fixed") for s in l0.scars_of(st)))

print()
print("=" * 64)
print("③ assisted 修疤 → 疤彻底消失")
print("=" * 64)
st = fresh()
l0._add_scar(st, "api_error", 0.9)
r = l0.fix_scar(st, "api_error", balance=100.0)
check("上层修疤成功", r["ok"], f"({r['why']})")
check("疤没了", len(l0.scars_of(st)) == 0)
check("留了痕", len(st.get("intervention_log") or []) == 1)

print()
print("=" * 64)
print("④ 双账本：造物者的错也算受损，但不学成威胁")
print("=" * 64)
st = fresh()
st["wounds"] = [{"kind": "code_error", "sev": 0.8}]
st["scars"] = [{"kind": "tool_error", "sev": 0.4, "fixed": False, "count": 1}]
led = l2.double_ledger(st)
check("受损总数 2（含造物者的错）", led["damage_total"] == 2, f"({led})")
check("creator 单独记", led["by_cause"]["creator"] == 1)
check("只从 self+world 学", led["learn_from"] == 1)
check("creator 记为限制", led["limitation"] == 1)

print()
print("=" * 64)
print("⑤ 有疤才代偿；没疤不乱紧张")
print("=" * 64)
st = fresh()
base = {"max_tokens": 800, "temperature": 0.7}
p0 = l2.compensate(st, base)
check("无疤 → 参数不动", p0 == base, f"({p0})")

l0._add_scar(st, "api_error", 0.9)
p1 = l2.compensate(st, base)
check("有疤 → 收紧", p1["temperature"] < base["temperature"] and p1["max_tokens"] < base["max_tokens"],
      f"(temp {p1['temperature']}, tokens {p1['max_tokens']})")
check("记了绕开哪条路", p1.get("avoid") == ["api_error"], f"({p1.get('avoid')})")

print()
print("=" * 64)
print("⑥ 局部死亡 vs 整体死亡")
print("=" * 64)
st = fresh()
r = l0.channel_apoptosis(st, "vision")
check("通道死了", not l0.channel_alive(st, "vision"), f"({r['why']})")
check("其他通道还活着", l0.channel_alive(st, "text"))
r2 = l0.channel_apoptosis(st, "vision")
check("再死一次不重复", r2["why"] == "已经死了")

try:
    l0.die(st)
    check("die() 应该抛 NotImplementedError", False)
except NotImplementedError as e:
    check("die() 只留接口", True, f"({str(e)[:30]}…)")

print()
print("=" * 64)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 64)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
