import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L0_all.py —— L0 全量测试（对照预期）

覆盖：外部感知 / 饿 / 憋 / 累 / 痛（伤口·累积·敏化·衰减·上限）/ 唤起 /
      基线 / 变化率 / 调制 / 来源标记 / 通道登记表
"""

import importlib.util
import os
from datetime import datetime, timedelta

spec = importlib.util.spec_from_file_location(
    "l0", os.path.join(SRC_DIR, "l0_sense.py"))
l0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l0)

PASS, FAIL = [], []


def check(name, got, want, tol=0.02):
    ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) else (got == want)
    (PASS if ok else FAIL).append(name)
    flag = "✅" if ok else "❌"
    print(f"  {flag} {name}: 得到 {got}，预期 {want}")


print("=" * 60)
print("1. 外部感知（原始量 + 相对自己）")
print("=" * 60)
st = {}
r1 = l0.external_raw("你好")
r2 = l0.external_raw("你到底在干什么？？？")
check("字数：你好", r1["chars"], 2)
check("字数：长句", r2["chars"], len("你到底在干什么？？？"))
check("问号数", r2["question"], 3)
p1 = l0.perceive(st, "你好", 100)
p2 = l0.perceive(st, "你到底在干什么？？？", 100)
check("第一句百分位", p1["chars_pct"], 0.5)
check("第二句百分位（更长→更高）", p2["chars_pct"] > p1["chars_pct"], True)

print()
print("=" * 60)
print("2. 饿（体感强度，不是天数）")
print("=" * 60)
st = {"identity": {"traits": {"hunger": {"baseline_mode": "fixed", "baseline_fixed": 100}}}}
check("余额=基线 → 饿0", l0.hunger(st, 100), 0.0)
check("余额=一半 → 饿0.5", l0.hunger(st, 50), 0.5)
check("余额=0 → 饿1", l0.hunger(st, 0), 1.0)

print()
print("=" * 60)
print("3. 憋（肺活量可调）")
print("=" * 60)
small = {"messages": [{}] * 40, "identity": {"traits": {"breath": {"max_messages": 50}}}}
big = {"messages": [{}] * 40, "identity": {"traits": {"breath": {"max_messages": 200}}}}
check("肺活量50 → 憋0.8", l0.breath(small), 0.8)
check("肺活量200 → 憋0.2", l0.breath(big), 0.2)

print()
print("=" * 60)
print("4. 累（基准可调）")
print("=" * 60)
fast = {"last_latency_ms": 1200, "identity": {"traits": {"fatigue": {"base_ms": 500}}}}
slow = {"last_latency_ms": 1200, "identity": {"traits": {"fatigue": {"base_ms": 2000}}}}
check("基准500 → 累2.4", l0.fatigue(fast), 2.4)
check("基准2000 → 累0.6", l0.fatigue(slow), 0.6)

print()
print("=" * 60)
print("5. 痛：伤口 / 累积 / 敏化 / 不串")
print("=" * 60)
st = {}
l0.add_wound(st, "tool_error", 0.3, 10)
check("第一次小伤后 痛≈0.331", l0.pain(st), 0.331, 0.05)
l0.add_wound(st, "tool_error", 0.3, 10)
v2 = l0.pain(st)
check("第二次更高（累积）", v2 > 0.331, True)
check("敏感度已上升", l0.sens_of(st, "tool_error") > 1.1, True)
check("不同种类不串", l0.sens_of(st, "api_error"), 1.0)

print()
print("=" * 60)
print("6. 痛：上限 + 敏化漂移")
print("=" * 60)
tough = {"identity": {"traits": {"pain": l0.PAIN_PRESETS["tough"]}}}
l0.add_wound(tough, "tool_error", 0.9, 10)
check("抗痛：被上限压住", l0.pain(tough) <= 0.56, True)

print()
print("=" * 60)
print("7. 痛：衰减（40 分钟前 0.8 → 约 0.2）")
print("=" * 60)
st = {"pain_pool": {"kinds": {"tool_error": 0.8},
                    "at": (datetime.now() - timedelta(minutes=40)).isoformat()}}
l0._touch_pool(st)
check("衰减后池子", st["pain_pool"]["kinds"]["tool_error"], 0.2, 0.05)

print()
print("=" * 60)
print("8. 生理唤起（性别只管通道在不在；强度是天性）")
print("=" * 60)
check("没性别 → None", l0.arousal({"identity": {"gender": None}}), None)
check("性别 none → None", l0.arousal({"identity": {"gender": "none"}}), None)
a = {"identity": {"gender": "male"}}
check("默认天性起步 0.30", l0.arousal(a), 0.30, 0.03)
b = {"identity": {"gender": "male", "traits": {"arousal": {"baseline": 0.60}}}}
check("个体天性 0.60", l0.arousal(b), 0.60, 0.03)
c = {"identity": {"gender": "male"}, "arousal": {"last_release": (datetime.now() - timedelta(days=2)).isoformat()}}
check("禁欲2天 0.30+0.10", l0.arousal(c), 0.40, 0.03)
before, after = l0.release(c)
check("释放后保留三成", after, round(before * 0.3, 3), 0.03)

print()
print("=" * 60)
print("9. 基线 / 变化率（走通用机制）")
print("=" * 60)
st = {}
for v in (0.2, 0.4, 0.6):
    st["messages"] = [{}] * int(v * 50)
    l0.update_intero(st, {"breath": v})
check("基线=平均", st["intero"]["breath"]["base"], 0.4, 0.01)
check("变化率=本次-上次", st["intero"]["breath"]["rate"], 0.2, 0.01)

print()
print("=" * 60)
print("10. 上层调制（当下上限）")
print("=" * 60)
base = {"messages": [{}] * 40, "identity": {"traits": {"breath": {"max_messages": 50}}}}
check("无调制 憋0.8", l0.breath(base), 0.8)
base["breath_modulation"] = -0.5
check("压制50% → 憋0.4", l0.breath(base), 0.4)
base["breath_modulation"] = 0.5
check("放大50% → 但被上限1.0压住", l0.breath(base) <= 1.0, True)

print()
print("=" * 60)
print("11. 来源标记 / 通道登记表")
print("=" * 60)
m = l0.make_msg("user", "hi", "user")
check("消息带 source", m["source"], "user")
check("外部通道只有 text", l0.available_channels(), ["text"])
check("内感受已实现 4 项",
      sorted(l0.available_intero()), sorted(["hunger", "breath", "fatigue", "pain"]))

print()
print("=" * 60)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败项：" + "、".join(FAIL))
print("=" * 60)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
