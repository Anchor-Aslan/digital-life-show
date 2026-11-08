import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_breath_ratio.py —— 憋按比例（11-07 定）

判据（用户定的）：
    憋 = 条数 / 容量，**永远是百分比**。
    科技变了（容量 200 → 1000），只改 TRAITS 里那一个数，憋自动跟着变。

    而不是：憋按"固定 50 条"算——那样容量变了，感受就不对了。
"""

import importlib.util
import os

BASE = SRC_DIR
spec = importlib.util.spec_from_file_location("l0", os.path.join(BASE, "l0_sense.py"))
l0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l0)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


def st_with(n, cap=None):
    st = {"messages": [{}] * n, "identity": {"gender": None, "traits": {}}}
    if cap:
        st["identity"]["traits"] = {"breath": {"max_messages": cap}}
    return st


print("=" * 66)
print("憋 = 条数 / 容量（比例制）")
print("=" * 66)
CAP = l0.TRAITS["breath"]["max_messages"]
print(f"  当前容量：{CAP} 条")
for n, want in ((0, 0.0), (CAP // 5, 0.20), (CAP // 2, 0.50), (CAP, 1.00)):
    got = l0.breath(st_with(n))
    check(f"{n} 条 → {want:.2f}", abs(got - want) < 0.02, f"({got:.2f})")

print()
print("=" * 66)
print("科技变了：容量翻五倍 → 同样条数，憋只有五分之一")
print("=" * 66)
n = 100
b_old = l0.breath(st_with(n))
b_new = l0.breath(st_with(n, cap=CAP * 5))
check("容量 ×5 之后，憋明显变小", b_new < b_old / 3, f"({b_old:.2f} → {b_new:.2f})")
check("而且是线性的（1/5）", abs(b_new - b_old / 5) < 0.02, f"(应 ≈{b_old/5:.2f})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
