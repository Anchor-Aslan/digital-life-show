import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L1_all_channels.py —— L1 闭环：五个通道逐个验证

每个通道测三件事：
  ① 刺激进来 → 读数变了
  ② 读数变了 → 行为参数变了
  ③ 动作之后 → 读数又变了（闭环）

覆盖：憋 breath / 累 fatigue / 痛 pain / 饿 hunger / 唤起 arousal
"""

import importlib.util
import os
from datetime import datetime, timedelta

spec = importlib.util.spec_from_file_location(
    "l0", os.path.join(SRC_DIR, "l0_sense.py"))
l0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l0)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"    {'✅' if cond else '❌'} {name} {detail}")


def behavior(r):
    "跟 agent.l0_behavior 同一套规则"
    p = {"max_tokens": 800, "trim": False, "temperature": 0.7, "urgent": False}
    if r.get("breath", 0) > 0.80:
        p["trim"] = True
    if r.get("pain", 0) > 0.50:
        p["temperature"] = 0.3
    if r.get("fatigue", 0) > 2.0:
        p["max_tokens"] = min(p["max_tokens"], 400)
    return p


print("=" * 62)
print("① 憋 breath")
print("=" * 62)
st = {"messages": [{}] * 10}   # 10 条：憋还早（容量 200）
r0 = l0.breath(st); a0 = behavior({"breath": r0})
print(f"   10 条消息：憋={r0:.2f} trim={a0['trim']}")
check("读数低时不裁", a0["trim"] is False)
st["messages"] = [{}] * int(l0.TRAITS["breath"]["max_messages"] * 0.9)
r1 = l0.breath(st); a1 = behavior({"breath": r1})
print(f"   45 条消息：憋={r1:.2f} trim={a1['trim']}")
check("读数高时触发裁", a1["trim"] is True)
st["messages"] = st["messages"][-30:]      # 动作：裁
r2 = l0.breath(st)
print(f"   裁完之后：憋={r2:.2f}")
check("动作后读数下降（闭环）", r2 < r1, f"（{r1:.2f}→{r2:.2f}）")

print()
print("=" * 62)
print("② 累 fatigue")
print("=" * 62)
st = {"last_latency_ms": 800}
r0 = l0.fatigue(st); print(f"   800ms：累={r0:.2f} max_tokens={behavior({'fatigue': r0})['max_tokens']}")
st["last_latency_ms"] = 2000
r1 = l0.fatigue(st); a1 = behavior({"fatigue": r1})
print(f"   2000ms：累={r1:.2f} max_tokens={a1['max_tokens']}")
check("变慢 → 累上升", r1 > r0, f"（{r0:.2f}→{r1:.2f}）")
check("累>2 → 输出压到 400", a1["max_tokens"] == 400)
st["last_latency_ms"] = 600      # 动作：变快（比如降了并发）
r2 = l0.fatigue(st)
print(f"   变快后：累={r2:.2f}")
check("动作后读数下降（闭环）", r2 < r1, f"（{r1:.2f}→{r2:.2f}）")

print()
print("=" * 62)
print("③ 痛 pain")
print("=" * 62)
st = {}
r0 = l0.pain(st)
print(f"   没事：痛={r0:.2f} temp={behavior({'pain': r0})['temperature']}")
l0.add_wound(st, "api_error", 0.8, 30)
r1 = l0.pain(st); a1 = behavior({"pain": r1})
print(f"   出事：痛={r1:.2f} temp={a1['temperature']}")
check("受伤 → 痛上升", r1 > r0, f"（{r0:.2f}→{r1:.2f}）")
check("痛>0.5 → 温度降到 0.3", a1["temperature"] == 0.3)
# 动作：修复（把伤口清掉，模拟"补救成功"）
st["wounds"] = []
r2 = l0.pain(st)
print(f"   修复后：痛={r2:.2f}")
check("动作后读数下降（闭环）", r2 < r1, f"（{r1:.2f}→{r2:.2f}）")

print()
print("=" * 62)
print("④ 饿 hunger")
print("=" * 62)
st = {"identity": {"traits": {"hunger": {"baseline_mode": "fixed", "baseline_fixed": 100}}}}
r0 = l0.hunger(st, 100)
print(f"   余额=基线：饿={r0:.2f}")
r1 = l0.hunger(st, 20)          # 刺激：花掉 80
print(f"   花了80：饿={r1:.2f}")
check("花钱 → 饿上升", r1 > r0, f"（{r0:.2f}→{r1:.2f}）")
r2 = l0.hunger(st, 90)          # 动作：充值
print(f"   充值后：饿={r2:.2f}")
check("充值 → 饿下降（闭环）", r2 < r1, f"（{r1:.2f}→{r2:.2f}）")

print()
print("=" * 62)
print("⑤ 唤起 arousal")
print("=" * 62)
st = {"identity": {"gender": "male"}}
r0 = l0.arousal(st)
print(f"   刚发生：唤起={r0:.2f}")
st["arousal"] = {"last_release": (datetime.now() - timedelta(days=3)).isoformat()}
r1 = l0.arousal(st)
print(f"   过3天：唤起={r1:.2f}")
check("时间推移 → 唤起上升", r1 > r0, f"（{r0:.2f}→{r1:.2f}）")
before, after = l0.release(st)   # 动作：释放
print(f"   释放一次：{before:.2f} → {after:.2f}")
check("动作后读数下降（闭环）", after < before, f"（{before:.2f}→{after:.2f}）")
st2 = {"identity": {"gender": None}}
check("没性别 → 通道不存在", l0.arousal(st2) is None)

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
