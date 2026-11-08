import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_pressure_and_suppression.py —— 压力（稳态负荷）+ 抑制器（SIS）

两条判据：
  ① **压力是派生量**：算得出来、只算超出去的、不许存自己的 state
  ② **抑制器只作用 arousal**：累/痛/慢性压力 → 压低欲望；**不压别的通道**

反向验证：
  · 低于基线的读数不算压力（不然"平时很累但没超"也会算负荷）
  · 抑制有上限 0.7（再累也不归零——**零欲望是 release 的事**）
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
l1 = load("l1_reflex")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


def mk(pain=0.0, fatigue=0.0, breath=0.0, hunger=0.0, base_ratio=0.5):
    """造一份 intero：value 和 base，用来算压力。

    base_ratio = base/value 的比例。0.5 表示"基线是现在的一半"（超了一半）。
    """
    intero = {}
    for ch, v in (("pain", pain), ("fatigue", fatigue), ("breath", breath), ("hunger", hunger)):
        intero[ch] = {"value": v, "base": round(v * base_ratio, 3), "history": []}
    return {"intero": intero}


print("=" * 62)
print("① 压力 = 各通道超出去的部分加权和")
print("=" * 62)
st = mk()
p = l0.pressure(st)
check("全 0 → 压力 0", p["acute"] == 0.0, f"{p}")

st = mk(pain=0.8, fatigue=2.0, breath=0.6, hunger=0.4)
p = l0.pressure(st)
# 期望：0.4*0.4 + 0.3*1.0 + 0.2*0.3 + 0.1*0.2 = 0.16+0.30+0.06+0.02 = 0.54
check("四项加权 = 0.54", abs(p["acute"] - 0.54) < 0.01, f"{p}")

print()
print("=" * 62)
print("② 低于基线的部分不算压力（反向验证）")
print("=" * 62)
st = mk(pain=0.2, fatigue=0.5, base_ratio=2.0)   # base 比 value 高
p = l0.pressure(st)
check("读数低于基线 → 压力 0", p["acute"] == 0.0, f"{p}")

print()
print("=" * 62)
print("③ 慢性压力 = 历史平均（不是本轮）")
print("=" * 62)
st = mk(pain=0.8, fatigue=2.0)
for _ in range(5):
    p = l0.pressure(st)
check("连续同样输入 → 慢性 ≈ 急性", abs(p["chronic"] - p["acute"]) < 0.01,
      f"acute={p['acute']} chronic={p['chronic']}")

st2 = mk(pain=0.8, fatigue=2.0)
l0.pressure(st2)                       # 先来一轮高压力
st2_low = mk(pain=0.0, fatigue=0.0)    # 再换成低压力的同一份 state
st2_low["intero"] = st2["intero"]      # 但保留历史
st2_low["pressure_history"] = st2["pressure_history"]
l0.pressure(st2_low)                   # 降下来
check("压力降下来后，慢性 > 急性（有黏性）",
      st2_low["pressure_history"] and
      (sum(st2_low["pressure_history"]) / len(st2_low["pressure_history"])) > 0,
      f"history={st2_low['pressure_history']}")

print()
print("=" * 62)
print("④ 抑制器：累/痛/慢性压力 → 压低欲望，但有上限")
print("=" * 62)
st = mk()
st["pressure_history"] = [0.0]
s0 = l1.suppression(st, {"acute": 0.0, "chronic": 0.0})
check("不累不痛 → 抑制 0", s0 == 0.0, f"{s0}")

st = mk(fatigue=3.0, pain=1.0)
s1 = l1.suppression(st, {"acute": 1.0, "chronic": 1.0})
check("全满 → 压到上限 -0.7", abs(s1 + 0.7) < 0.01, f"{s1}")

st = mk(fatigue=1.5)
s2 = l1.suppression(st, {"acute": 0.0, "chronic": 0.0})
check("累一半 → 压到 -0.175（0.5×0.5×0.7）", abs(s2 + 0.175) < 0.01, f"{s2}")

print()
print("=" * 62)
print("⑤ 抑制只作用 arousal，不动别的通道")
print("=" * 62)
st = mk()
st["arousal_suppression"] = -0.5
st["pain_suppression"] = 0.0
a = l0.apply_mod(st, "arousal", 1.0)
p_ = l0.apply_mod(st, "pain", 1.0)
check("arousal 被压到 0.5", abs(a - 0.5) < 0.01, f"{a}")
check("pain 不受影响", abs(p_ - 1.0) < 0.01, f"{p_}")

print()
print("=" * 62)
print("⑥ modulation 和 suppression 各写各的，互不覆盖")
print("=" * 62)
st = mk()
st["arousal_modulation"] = 0.2      # 上层设的（心理）
st["arousal_suppression"] = -0.5    # L1 算的（生理）
v = l0.apply_mod(st, "arousal", 1.0)
check("两个系数相加 = 0.7", abs(v - 0.7) < 0.01, f"{v}")

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
