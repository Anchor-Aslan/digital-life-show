import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_axis_outlets.py —— 任务 4：五根死轴接上行为出口

判据（施工单 §4.4）：
    ① 五根轴各两个用例：越过阈值时行为变了，没越过时完全不变
    ② 五根同时拉满：style ≤ 2 条，max_tokens 取最小
    ③ 反向：control_sense 没数据（0.5）不该误伤
"""

import importlib.util
import os

BASE = SRC_DIR
s = importlib.util.spec_from_file_location("l1", os.path.join(BASE, "l1_reflex.py"))
l1 = importlib.util.module_from_spec(s)
s.loader.exec_module(l1)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


def base_readings(**kw):
    r = {"pain": 0.0, "fatigue": 1.0, "breath": 0.0, "hunger": 0.0}
    r.update(kw)
    return r


WATCH = ("max_tokens", "temperature", "trim", "urgent", "style", "tool_choice")


def reflex_of(**kw):
    p, ap = l1.reflex({}, base_readings(**kw))
    return {k: p.get(k) for k in WATCH}, ap


print("=" * 66)
print("任务 4：五根轴 → 行为出口")
print("=" * 66)

cases = [
    ("conflict", "valence_conflict", 0.50, 0.10),
    ("arousal", "arousal_axis", 0.90, 0.30),
    ("control_sense", "valence_control", 0.10, 0.80),
    ("effort", "valence_effort", 0.80, 0.20),
]

for name, key, hi, lo in cases:
    p_hi, _ = reflex_of(**{key: hi})
    p_lo, _ = reflex_of(**{key: lo})
    check(f"{name} 越线 → 行为变", p_hi != p_lo, f"(hi={p_hi.get('style') or p_hi}, lo={p_lo.get('style') or p_lo})")
    p_mid, _ = reflex_of()
    check(f"{name} 没越线 → 完全不变", p_mid["style"] == [] and p_mid["max_tokens"] == 800,
          f"(style={p_mid['style']}, tokens={p_mid['max_tokens']})")

# precision 按"见过几次"算（施工单 3 / 第 2 条）：seen=0 → 0.0 → 触发；seen≥2 → ≥0.4 → 不触发
p_new, _ = reflex_of(valence_precision_epi=0.0)
p_seen, _ = reflex_of(valence_precision_epi=0.4)
check("没见过（precision 0.0）→ 加 confirm", "confirm" in p_new["style"], f"({p_new['style']})")
check("见过两次（precision 0.4）→ 不加 confirm（防每句都复述）",
      "confirm" not in p_seen["style"], f"({p_seen['style']})")

print()
print("=" * 66)
print("五根同时拉满：风格不超 2 条、max_tokens 取最小")
print("=" * 66)
p_all, ap_all = reflex_of(valence_conflict=0.9, arousal_axis=0.95, valence_control=0.05,
                          valence_effort=0.95, valence_precision_epi=0.0, _key_seen=False)
check("风格 ≤ 2 条", len(p_all["style"]) <= l1.STYLE_MAX, f"({p_all['style']})")
check("max_tokens 取最小 500", p_all["max_tokens"] == 500, f"({p_all['max_tokens']})")
check("tool_choice 变 none", p_all["tool_choice"] == "none", f"({p_all['tool_choice']})")
check("每次都进 applied", sum(1 for a in ap_all if str(a.get("channel", "")).startswith("axis:")) >= 3,
      f"({[a['channel'] for a in ap_all]})")

print()
print("=" * 66)
print("反向：没数据的轴不该误伤")
print("=" * 66)
p_none, _ = reflex_of(valence_control=0.5)
check("control 0.5（还没结论）→ 不动", p_none["style"] == [] and p_none["tool_choice"] == "auto",
      f"({p_none['style']}, {p_none['tool_choice']})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见

# ================= 施工单 4 / 第 1 条：冲突时不许放开 =================
print()
print("=" * 66)
print("冲突（又想要又怕）→ 挡住在放开")
print("=" * 66)
p_c, ap_c = reflex_of(valence_avoid=0.5, valence_approach=0.5, valence_conflict=0.5)
check("冲突 → max_tokens ≤ 800", p_c["max_tokens"] <= 800, f"({p_c['max_tokens']})")
check("冲突 → temperature ≤ 0.7", p_c["temperature"] <= 0.7, f"({p_c['temperature']})")
check("冲突 → style 里有 hedge", "hedge" in p_c["style"], f"({p_c['style']})")

p_c2, _ = reflex_of(valence_avoid=0.5, valence_approach=0.5, valence_conflict=0.35)
check("冲突刚过线(.35) → 也不放开", p_c2["max_tokens"] <= 800 and p_c2["temperature"] <= 0.7,
      f"({p_c2['max_tokens']}, {p_c2['temperature']})")

p_free2, _ = reflex_of(valence_approach=0.5)
check("对照：只有想要 → 仍然放开到 900/0.8",
      p_free2["max_tokens"] == 900 and abs(p_free2["temperature"] - 0.8) < 1e-9,
      f"({p_free2['max_tokens']}, {p_free2['temperature']})")

# ================= 11-07：生理恶心有自己的出口（稳态正态：平常不许触发）=================
print()
print("=" * 66)
print("disgust_physio：≥0.70 才话变短（日常 0 触发）")
print("=" * 66)
p_low, _ = reflex_of(disgust_physio=0.60)
check("恶心 0.60（单一脏东西最多到这）→ 完全不动",
      p_low["style"] == [] and p_low["max_tokens"] == 800,
      f"({p_low['style']}, {p_low['max_tokens']})")
p_hi, ap_hi = reflex_of(disgust_physio=0.70)
check("恶心 0.70（发两次才够）→ 话变短、不展开",
      p_hi["max_tokens"] == 600 and "brief" in p_hi["style"] and "no_extend" in p_hi["style"],
      f"({p_hi['max_tokens']}, {p_hi['style']})")
check("触发时 applied 里有它自己", any(a.get("channel") == "axis:disgust_physio" for a in ap_hi),
      f"({[a.get('channel') for a in ap_hi]})")

if FAIL:
    raise SystemExit(1)
