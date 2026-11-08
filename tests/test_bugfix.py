import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

import importlib.util, os
spec = importlib.util.spec_from_file_location("l0", os.path.join(SRC_DIR, "l0_sense.py"))
l0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(l0)

print("=== Bug B 验证：个体 wound_min 现在生效 ===")
short = {"identity": {"traits": {"pain": {"wound_min": 5}}}}
long_ = {"identity": {"traits": {"pain": {"wound_min": 60}}}}
l0.add_wound(short, "api_error", 0.6)   # 不传 duration
l0.add_wound(long_, "api_error", 0.6)
print(f"  设定 5 分钟 → 记录 total_min={short['wounds'][0]['total_min']}")
print(f"  设定 60 分钟 → 记录 total_min={long_['wounds'][0]['total_min']}")
assert short["wounds"][0]["total_min"] == 5, "Bug B 没修好"
assert long_["wounds"][0]["total_min"] == 60, "Bug B 没修好"

print()
print("=== Bug A 验证：个体 sens_max 现在在衰减里生效 ===")
frag = {"identity": {"traits": {"pain": {"sens_max": 1.2, "sens_gain": 0.5}}}}
l0.add_wound(frag, "tool_error", 0.9)
for _ in range(5):
    l0.pain(frag)          # 触发 _touch_sens 衰减
print(f"  设定 sens_max=1.2，多次受伤后实际 sens={l0.sens_of(frag,'tool_error')}")
assert l0.sens_of(frag, "tool_error") <= 1.21, "Bug A 没修好"
print("  两个 bug 都已修好 ✅")
