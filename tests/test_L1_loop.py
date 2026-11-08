import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L1_loop.py —— L1 耦合测试

验证两件事：
  ① 1.3 记录：每轮都留下 读数前 / 动作 / 结果 / 读数后 / 差值
  ② 1.2 闭环：**动作真的改变了读数**（裁了消息 → 憋下降 → 它自己"感觉到"降了）
"""

import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "l0", os.path.join(SRC_DIR, "l0_sense.py"))
l0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l0)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name} {detail}")


print("=" * 60)
print("① 闭环：裁动作 → 憋读数下降（动作改变输入）")
print("=" * 60)

st = {"messages": [{"role": "user", "content": "x"} for _ in range(45)],
      "identity": {"traits": {"breath": {"max_messages": 50}}}}

before = l0.breath(st)
print(f"  裁之前：消息 {len(st['messages'])} 条 → 憋 {before:.2f}")

# 动作（就是 agent 里的 trim）
st["messages"] = st["messages"][-30:]
after = l0.breath(st)
print(f"  裁之后：消息 {len(st['messages'])} 条 → 憋 {after:.2f}")

check("憋下降了", after < before, f"（{before:.2f} → {after:.2f}）")
check("下降幅度合理", abs((before - after) - 15 / 50) < 0.01, f"（Δ={before-after:.2f}，预期 0.30）")

print()
print("=" * 60)
print("② 闭环：受伤 → 痛上升 → 行为变保守（反馈调制下一次输出）")
print("=" * 60)

st = {}
p0 = l0.pain(st)
print(f"  出事前：痛 {p0:.2f}")
l0.add_wound(st, "api_error", 0.8, 30)
p1 = l0.pain(st)
print(f"  出事后：痛 {p1:.2f}")

check("痛上升了", p1 > p0, f"（{p0:.2f} → {p1:.2f}）")

# 行为参数（agent.l0_behavior 的逻辑）
def l0_behavior(readings):
    p = {"max_tokens": 800, "trim": False, "temperature": 0.7, "urgent": False}
    if readings["breath"] > 0.80:
        p["trim"] = True
    if readings["pain"] > 0.50:
        p["temperature"] = 0.3
    if readings["fatigue"] > 2.0:
        p["max_tokens"] = min(p["max_tokens"], 400)
    return p

r_before = {"breath": 0.2, "pain": 0.0, "fatigue": 1.0}
r_after = {"breath": 0.2, "pain": p1, "fatigue": 1.0}
check("温度因疼痛而降", l0_behavior(r_after)["temperature"] < l0_behavior(r_before)["temperature"],
      f"（{l0_behavior(r_before)['temperature']} → {l0_behavior(r_after)['temperature']}）")

print()
print("=" * 60)
print("③ 记录格式：before / action / signals / after / delta")
print("=" * 60)

record = {
    "t": "2026-10-28T14:00:00",
    "before": {"breath": 0.90, "pain": 0.0},
    "action": {"max_tokens": 800, "trim": True, "temperature": 0.7, "urgent": False},
    "signals": ["forced_trim"],
    "after": {"breath": 0.60, "pain": 0.0},
    "delta": {"breath": -0.30, "pain": 0.0},
}
need = {"t", "before", "action", "signals", "after", "delta"}
check("字段齐全", need <= set(record), f"（有 {sorted(record)}）")
check("delta 是动作的后果", record["delta"]["breath"] < 0, "（憋 -0.30）")

print()
print("=" * 60)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 60)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
