import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_batch4.py —— ① 覆盖真扣钱  ② 坏通道不许读

用户 10-31 定的：
  ① 只记疼不扣钱 = 意志免费，形同虚设。这一层钱是唯一真不可逆的代价。
  ② 通道坏了还照读 = 幻听，是病不是功能。
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
            "dead_channels": [], "channel_fails": {}, "balance_history": [],
            "external_history": {}, "messages": []}


print("=" * 64)
print("① 覆盖反射 → 真扣钱 + 疼 + 留痕")
print("=" * 64)
st = fresh()
before = st["spend"]["today_cny"]
fee = l2.charge_response(st, ["max_tokens", "temperature"])
check("扣了钱", st["spend"]["today_cny"] > before,
      f"(¥{before:.4f} → ¥{st['spend']['today_cny']:.4f})")
check("也疼了", any(w["kind"] == "self_override" for w in st["wounds"]))
check("留了痕", len(st.get("override_log") or []) == 1)
check("返回了花费", fee["cost"] > 0, f"(¥{fee['cost']})")

fee2 = l2.charge_response(st, [])
check("没压过 → 不扣钱", fee2["cost"] == 0 and not fee2["charged"])

print()
print("=" * 64)
print("② 通道受损 → 那条读数消失（不是变 0）")
print("=" * 64)
st = fresh()
r1 = l0.perceive(st, "你好", 100.0)
check("正常有 text 读数", "chars" in r1, f"(有 {len(r1)} 项)")

l0.channel_impairment(st, "text")
r2 = l0.perceive(st, "你好", 100.0)
check("text 坏了 → 外部读数消失", "chars" not in r2, f"(剩 {len(r2)} 项)")
check("内感受还在", "hunger" in r2)

l0.channel_impairment(st, "pain")
r3 = l0.perceive(st, "你好", 100.0)
check("pain 坏了 → 痛读数消失", "pain" not in r3, f"(剩 {sorted(r3)})")

r = l0.repair_channel(st, "text", balance=100.0)
r4 = l0.perceive(st, "你好", 100.0)
check("修好 → 读数回来", "chars" in r4, f"({r['why']})")

print()
print("=" * 64)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 64)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
