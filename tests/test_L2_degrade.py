import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L2_degrade.py —— 降级（撑不住就降配，不是死）

判据：
  ① 单个风险源出现 → 分数上去
  ② 风险够了 → 降级（low / survival）
  ③ 降级后参数被压
  ④ 风险消失 → 能回升，但带滞回（防抖）
  ⑤ 正常时不乱降
"""

import importlib.util
import os

BASE = SRC_DIR
spec = importlib.util.spec_from_file_location("l2", os.path.join(BASE, "l2_ownership.py"))
l2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


print("=" * 62)
print("① 单个风险源")
print("=" * 62)
r1 = l2.compute_risk({"wounds": [{"kind": "state_corrupt"}]})
check("身体坏过 = 0.40", r1["score"] == 0.40, f"({r1['reasons']})")

r2 = l2.compute_risk({"intero": {"hunger": {"value": 0.9}}})
check("快没钱 = 0.30", r2["score"] == 0.30, f"({r2['reasons']})")

r3 = l2.compute_risk({"trace": [{"wounds": ["a"]}] * 3})
check("连错三次 = 0.30", r3["score"] == 0.30)

r4 = l2.compute_risk({"intero": {"breath": {"value": 0.95}}})
check("上下文快满 = 0.20", r4["score"] == 0.20)

print()
print("=" * 62)
print("② 组合 → 降级级别")
print("=" * 62)
# 身体坏 + 没钱 = 0.70 → survival
st = {"wounds": [{"kind": "state_corrupt"}], "intero": {"hunger": {"value": 0.9}}}
lvl = l2.degrade_level(st)
check("0.70 → survival", lvl == "survival", f"(得分 {l2.compute_risk(st)['score']})")

# 只有没钱 = 0.30 → low
st2 = {"intero": {"hunger": {"value": 0.9}}}
check("0.30 → low", l2.degrade_level(st2) == "low")

# 都没事 → normal
st3 = {}
check("0 → normal", l2.degrade_level(st3) == "normal")

print()
print("=" * 62)
print("③ 降级后参数被压")
print("=" * 62)
base = {"max_tokens": 800, "temperature": 0.7}
p_low = l2.degrade({"intero": {"hunger": {"value": 0.9}}}, base)
check("low: 400 / 0.5", p_low["max_tokens"] == 400 and p_low["temperature"] == 0.5, f"({p_low})")

st4 = {"wounds": [{"kind": "state_corrupt"}], "intero": {"hunger": {"value": 0.9}}}
p_sur = l2.degrade(st4, base)
check("survival: 200 / 0.3", p_sur["max_tokens"] == 200 and p_sur["temperature"] == 0.3, f"({p_sur})")

p_norm = l2.degrade({}, base)
check("normal: 不动", p_norm["max_tokens"] == 800 and p_norm["temperature"] == 0.7)

print()
print("=" * 62)
print("④ 回升带滞回（防抖）")
print("=" * 62)
# 先降到 survival
st5 = {"wounds": [{"kind": "state_corrupt"}], "intero": {"hunger": {"value": 0.9}}}
l2.degrade_level(st5)
check("已在 survival", st5["degrade_level"] == "survival")

# 从 survival 出来：风险要 < 0.45 才回 low（滞回）
# 造一个 0.50 的风险：没钱(0.30) + 上下文满(0.20)
st5["wounds"] = []
st5["trace"] = []
st5["intero"] = {"hunger": {"value": 0.9}, "breath": {"value": 0.95}}
r_mid = l2.compute_risk(st5)["score"]
lvl_mid = l2.degrade_level(st5)
check("风险 0.50 时仍留在 survival（滞回挡住）",
      r_mid == 0.50 and lvl_mid == "survival", f"(得分 {r_mid} → {lvl_mid})")

# 风险降到 0.30 → 允许回 low
st5["intero"] = {"hunger": {"value": 0.9}}
r_low = l2.compute_risk(st5)["score"]
lvl_low = l2.degrade_level(st5)
check("风险降到 0.30 → 回 low", r_low == 0.30 and lvl_low == "low", f"(得分 {r_low} → {lvl_low})")

# 完全恢复 → normal（low 出来要 < 0.15）
st5["intero"] = {}
st5["trace"] = []
for _ in range(3):
    l2.degrade_level(st5)
check("风险清零后回到 normal", st5["degrade_level"] == "normal", f"({st5['degrade_level']})")

print()
print("=" * 62)
print("⑤ 人话")
print("=" * 62)
st6 = {"wounds": [{"kind": "state_corrupt"}], "intero": {"hunger": {"value": 0.9}}}
l2.degrade_level(st6)
line = l2.degrade_line(st6)
print(f"  {line}")
check("能说出原因", "降级中" in line and "身体" in line)

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
