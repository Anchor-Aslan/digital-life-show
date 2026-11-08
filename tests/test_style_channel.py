import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_style_channel.py —— 任务 3：行为风格通道（封闭词表）

判据：
    ① 词表外的键不进提示词
    ② 两个来源都给 style 时，合成后不超过 2 条，且按优先级排序
    ③ 任一方给 tool_choice="none"，合成后就是 "none"
    ④ 反向测试：把词表临时改成含"你很累"，审计第 12 步必须判红
"""

import importlib.util
import os
import re

BASE = SRC_DIR


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l1 = load("l1_reflex")
ag = load("agent")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


print("=" * 66)
print("任务 3：风格通道（封闭词表）")
print("=" * 66)

# ① 词表外的键不进提示词
st = {"messages": []}
p_out = ag.build_prompt(st, {"style": ["不存在的键"]})
check("词表外的键不进提示词", p_out == ag.BASE_PROMPT, f"({p_out[:40]}…)")

p_in = ag.build_prompt(st, {"style": ["brief"]})
check("词表内的键进提示词", l1.STYLE_VOCAB["brief"] in p_in, f"({p_in[-30:]}…)")

# ② 合成：不超过 2 条 + 按优先级
base = {"max_tokens": 800, "temperature": 0.7, "trim": False, "urgent": False,
        "trim_keep": [], "style": ["no_suggest"], "tool_choice": "auto"}
resp = {"params": {"style": ["hedge", "brief", "confirm"]}}
final = l1.combine(base, resp)
check("合成后不超过 2 条", len(final["style"]) <= l1.STYLE_MAX, f"({final['style']})")
check("按优先级排序（brief 在 hedge 前）",
      final["style"] == ["brief", "hedge"] or final["style"] == ["brief", "confirm"],
      f"({final['style']})")

# ③ tool_choice
final2 = l1.combine(base, {"params": {"tool_choice": "none"}})
check("任一方 none → 合成后 none", final2["tool_choice"] == "none", f"({final2['tool_choice']})")

# ④ 反向测试：词表里混进"你很累" → 审计第 12 步那三条机检要红
BAD_WORDS = ("累", "痛", "饿", "憋", "怕", "紧张", "焦虑", "难受", "生气",
             "愤怒", "害怕", "恶心", "讨厌", "喜欢", "心情", "情绪", "感觉", "体感")
AXIS_WORDS = ("approach", "avoid", "conflict", "arousal", "control", "effort",
              "precision", "disgust", "pain", "fatigue", "hunger", "breath")


def audit_style_ok(vocab):
    bad = []
    for k, v in vocab.items():
        if re.search(r"\d", v):
            bad.append(f"{k} 含数字")
        if any(w in v for w in AXIS_WORDS):
            bad.append(f"{k} 含轴名")
        if any(w in v for w in BAD_WORDS):
            bad.append(f"{k} 含体感/情绪词")
        if any(w in v for w in getattr(l1, "STYLE_FORBIDDEN", ())):
            bad.append(f"{k} 在报告内部状态")
    return bad


ok_bad = audit_style_ok(l1.STYLE_VOCAB)
check("现有词表干净（机检 0 命中）", not ok_bad, f"({ok_bad})")

polluted = dict(l1.STYLE_VOCAB)
polluted["bad"] = "你很累，说短点。"
check("反向：混进'累'必须被抓到", bool(audit_style_ok(polluted)), f"({audit_style_ok(polluted)})")
polluted2 = dict(l1.STYLE_VOCAB)
polluted2["bad2"] = "avoid 高于 0.6，说短点。"
check("反向：混进轴名必须被抓到", bool(audit_style_ok(polluted2)), f"({audit_style_ok(polluted2)})")
polluted3 = dict(l1.STYLE_VOCAB)
polluted3["bad3"] = "说短点，最多 200 字。"
check("反向：混进数字必须被抓到", bool(audit_style_ok(polluted3)), f"({audit_style_ok(polluted3)})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
