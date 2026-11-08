import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L2_learn.py —— 测试"学会"

判据：
  同一类伤反复出现 → 学成"老毛病" → 从此提前防备
  而且这个"老"要长在它自己身上（存在 state 里），换一轮也记得
"""

import importlib.util
import os

BASE = SRC_DIR


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BASE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l0 = load("l0_sense")
l2 = load("l2_ownership")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


print("=" * 62)
print("① 只受一两次伤 → 学不成（不许见一次就成老毛病）")
print("=" * 62)
st = {"trace": [{"wounds": ["api_error"]}, {"wounds": ["api_error"]}]}
learned, newly = l2.learn(st)
check("两次不成老毛病", not learned and not newly, f"(learned={learned})")

print()
print("=" * 62)
print("② 第三次 → 学成")
print("=" * 62)
st["trace"].append({"wounds": ["api_error"]})
learned, newly = l2.learn(st)
check("第三次学成", "api_error" in learned, f"(新学成={newly})")
check("记了次数", learned["api_error"]["count"] == 3, f"(count={learned['api_error']['count']})")

print()
print("=" * 62)
print("③ 学成之后 → 提前收紧（不用等疼）")
print("=" * 62)
base = {"max_tokens": 800, "temperature": 0.7, "trim": False}
p = l2.apply_learned(st, base)
check("温度降了", p["temperature"] < base["temperature"], f"(0.7 → {p['temperature']})")
check("长度短了", p["max_tokens"] < base["max_tokens"], f"(800 → {p['max_tokens']})")

print()
print("=" * 62)
print("④ 没学成时不动（不许乱保守）")
print("=" * 62)
empty = {}
p2 = l2.apply_learned(empty, base)
check("无老毛病 → 参数不变", p2 == base, f"({p2})")

print()
print("=" * 62)
print("⑤ 学的种类要分开（api_error ≠ tool_error）")
print("=" * 62)
st2 = {"trace": []}
for _ in range(4):
    st2["trace"].append({"wounds": ["api_error"]})
st2["trace"].append({"wounds": ["tool_error"]})
learned2, _ = l2.learn(st2)
check("api_error 学成", "api_error" in learned2)
check("tool_error 没学成", "tool_error" not in learned2)

print()
print("=" * 62)
print("⑥ 越老越保守，但封顶（不许把自己憋死）")
print("=" * 62)
st3 = {"trace": []}
for kind in ("api_error", "tool_error", "file_corrupt"):
    for _ in range(3):
        st3["trace"].append({"wounds": [kind]})
l2.learn(st3)
p3 = l2.apply_learned(st3, base)
check("有下限", p3["temperature"] >= 0.1 and p3["max_tokens"] >= 200,
      f"(temp={p3['temperature']} tokens={p3['max_tokens']})")

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
