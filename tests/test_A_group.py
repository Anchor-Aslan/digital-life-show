import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_A_group.py —— 施工单 2 的 A 组四条（每条都用审稿方给的复现方法证明它没了）

A1 节奏永远是 fast
A2 想要覆盖了收紧（包括反射）
A3 confirm 规则永远触发不了
A4 一场会话 3 次变成一辈子 3 次
"""

import ast
import importlib.util
import os
import re
from datetime import datetime, timedelta

BASE = SRC_DIR


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l1 = load("l1_reflex")
l3 = load("l3_valence")
ag = load("agent")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


# ================= A1 =================
print("=" * 66)
print("A1：算特征之前不许先刷新 last_seen")
print("=" * 66)

src = open(os.path.join(BASE, "agent.py"), encoding="utf-8").read()
# 静态：extract_features 在前，刷新 last_seen 在后（按行号）
i_feat = src.find("feat = l3.extract_features(q, _feat_state)")
i_seen = src.find('state["last_seen"] = now_iso()')
check("源码里 extract_features 在 last_seen 刷新之后（用刷新前的值）",
      i_seen >= 0 and i_feat > i_seen and "_last_seen_before" in src,
      f"(刷新@{i_seen}, 特征@{i_feat})")

# 行为：伪造不同的间隔
for sec, want in ((20, "fast"), (100, "normal"), (2000, "slow")):
    st = {"last_seen": (datetime.now() - timedelta(seconds=sec)).isoformat()}
    got = l3.extract_features("你好", st)["pace"]
    check(f"伪造 {sec} 秒前 → {want}", got == want, f"({got})")

# ================= A2 =================
print()
print("=" * 66)
print("A2：有收紧时，'想要'不许顶掉它")
print("=" * 66)

combos = [
    ("疲劳反射(400)", {"fatigue": 2.6}, 400, None),
    ("痛反射(温度0.3)", {"pain": 1.2}, 800, 0.3),
    ("avoid(500/0.5)", {"valence_avoid": 0.7}, 500, 0.5),
    ("arousal(500)", {"arousal_axis": 0.8}, 500, None),
    ("effort(600)", {"valence_effort": 0.8}, 600, None),
]
for name, rd, cap, tcap in combos:
    p1, _ = l1.reflex({}, rd)
    rd2 = dict(rd); rd2["valence_approach"] = 0.3
    p2, ap2 = l1.reflex({}, rd2)
    ok = p2["max_tokens"] <= p1["max_tokens"] and p2["temperature"] <= p1["temperature"]
    check(f"{name} + approach → 不被顶掉", ok,
          f"(tokens {p1['max_tokens']}→{p2['max_tokens']}, temp {p1['temperature']}→{p2['temperature']})")

# 对照：没有任何收紧时，仍然放开
p_free, ap_free = l1.reflex({}, {"valence_approach": 0.3})
check("没有任何收紧 → 仍然放开到 900/0.8",
      p_free["max_tokens"] == 900 and abs(p_free["temperature"] - 0.8) < 1e-9,
      f"({p_free['max_tokens']}, {p_free['temperature']})")
check("被让位时留了痕", any(a.get("reaction", {}).get("suppressed") for a in ap_free) is False
      and any(a.get("kind") == "approach" for a in ap_free), f"({[a['kind'] for a in ap_free]})")

p_sup, ap_sup = l1.reflex({}, {"valence_avoid": 0.7, "valence_approach": 0.3})
check("冲突时记一条 suppressed", any(a.get("reaction", {}).get("suppressed") for a in ap_sup),
      f"({[a.get('reaction') for a in ap_sup if a.get('kind') == 'approach']})")

# ================= A3 =================
print()
print("=" * 66)
print("A3：precision 规则在真实链路里能触发（第一次见 → confirm）")
print("=" * 66)

st = ag.default_state()
st["messages"] = []
readings = {"pain": 0.0, "fatigue": 1.0, "breath": 0.0, "hunger": 0.0}
intero = {"pain": {"value": 0.0, "rate": 0.0}, "fatigue": {"value": 1.0, "rate": 0.0},
          "breath": {"value": 0.0, "rate": 0.0}, "hunger": {"value": 0.0, "rate": 0.0}}
feat = l3.extract_features("我想问一下这个方案行不行", st)
val = l3.value_of(st, feat, text="我想问一下这个方案行不行")
rl = ag.build_readings_l1(st, readings, intero, feat, val)
# 施工单 3 / 第 2 条：precision 改成按"见过几次"算（seen），没见过就是 0.0，不再返回 None
check("没见过 → precision 0.0（不是 None，也不再是错的 hits）",
      rl["valence_precision_epi"] == 0.0, f"({rl['valence_precision_epi']})")
p_first, _ = l1.reflex(st, rl)
check("第一次见 → style 里有 confirm", "confirm" in p_first["style"], f"({p_first['style']})")

# 学过 5 次之后：episodic=1.0 → 不该再 confirm
st2 = ag.default_state()
for _ in range(5):
    l3.note_seen(st2, feat)          # 见过 5 次（不是学过 5 次）
val2 = l3.value_of(st2, feat, text="我想问一下这个方案行不行")
rl2 = ag.build_readings_l1(st2, readings, intero, feat, val2)
check("见过 5 次 → episodic=1.0", rl2["valence_precision_epi"] == 1.0, f"({rl2['valence_precision_epi']})")
p_seen, _ = l1.reflex(st2, rl2)
check("学过之后 → 不再 confirm", "confirm" not in p_seen["style"], f"({p_seen['style']})")

# ================= A4 =================
print()
print("=" * 66)
print("A4：启动时 reaction_count 清零")
print("=" * 66)

src2 = open(os.path.join(BASE, "agent.py"), encoding="utf-8").read()
i_load = src2.find("state, notes = load_state()")
seg = src2[i_load:i_load + 400]
check("load_state 之后紧接着清零", 'state["reaction_count"] = 0' in seg, "(看那 400 字)")
check("prev_feat 也清", 'state["prev_feat"] = None' in seg)
check("prev_text_norm 也清", 'state["prev_text_norm"] = ""' in seg)

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
