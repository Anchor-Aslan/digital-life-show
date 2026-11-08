import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L2_boundary.py —— 边界（判谁）

判据：归属对象是**整个 agent**；但伤要分清是谁的：
  self    它自己这副身体
  world   外面的世界
  creator 造它的人（我写错代码）——不算它的伤
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
print("① 三种伤分得清")
print("=" * 62)
st = {"wounds": [
    {"kind": "api_error"}, {"kind": "api_error"},     # 外面
    {"kind": "file_corrupt"},                          # 自己
    {"kind": "code_error"},                            # 造物者
]}
c = l2.of_mine(st)
check("world = 2", c["world"] == 2, f"({c})")
check("self = 1", c["self"] == 1)
check("creator = 1", c["creator"] == 1)
check("我的 = 3（不含造物者）", c["mine"] == 3)

print()
print("=" * 62)
print("② 我代码写错 → 不算它的伤")
print("=" * 62)
st2 = {"wounds": [{"kind": "code_error"}]}
c2 = l2.of_mine(st2)
check("code_error 不进我的账", c2["mine"] == 0 and c2["creator"] == 1, f"({c2})")

print()
print("=" * 62)
print("③ 对象是整个身体，不是某个部件")
print("=" * 62)
st3 = {"wounds": [{"kind": "file_corrupt"}, {"kind": "state_corrupt"},
                  {"kind": "tool_error"}]}
c3 = l2.of_mine(st3)
check("三种自己身体的伤都算一处", c3["mine"] == 3, f"({c3})")

print()
print("=" * 62)
print("④ 人话")
print("=" * 62)
line = l2.boundary_line(st)
print(f"  {line}")
check("能说出人话", "我自己的" in line and "外面给的" in line)

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
