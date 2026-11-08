"""l3_5_ownership.py —— L3.5 归属收敛（三条通路 → 一个"我的"）

一句话：
    **身体在同步、感受在对得上、行为按我说的发生了 —— 三条都在，这一下才叫"我的"。**

规格见 `工程/L3.5-工程图.md`。三个函数 + 一个总入口：
    ① converge()         纯函数，三条通路 → O（加权几何平均，任一条 0 就归零）
    ② body_ownership()   身体：5 个部件 × 3 条判据（同步 / 因果 / 来源）
    ③ act_ownership()    行为：意图 vs 结果，对不上就是空转
    ④ feel_ownership()   感受：读数有、价有、同向、强度匹配
    ⑤ measure()          总入口，agent.py 只调它

**不做**（防错层）：
    不说"我觉得"（L4）· 不给情绪起名（L4）· 把 O 写进提示词（审计第 12 步）
    改行为参数（L1 是唯一写入者）· 用叙事检索（L5）

**契约（用户 10-31 定的）**：
    **这个值只进 trace 和控制台，一个字都不进提示词。**
"""

import importlib.util
import os

_BASE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_BASE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l0 = _load("l0_sense")
l2 = _load("l2_ownership")

SCAR_WEIGHT_PER = 0.3      # 🎯 每条疤让这条通路降价 30%（疤多的通路更不可信）
LOW = 0.35                 # 🎯 原始读数："身体不好"的线
LOW_CHANGE = 0.15          # 🎯 用 intero 时："身体在变差"的线（看变化，不看绝对值）
FEEL_RATIO = (0.2, 5.0)    # 🎯 强度比落在这个区间才算"匹配"


# ================= ① 收敛（纯函数，最好测） =================
def converge(body, feel, act, scars=None):
    """加权几何平均。None = 没参与；0 = 断了（一条断，整体归零）。

    为什么用几何平均而不是算术平均：
        算术平均里，一条断（0）只把总分拉低三分之一——那就不叫"我的"了。
        几何平均里 0 的任何次幂都是 0——**断一条，整件事就不是我的**。
        这就是"异己手"（手还在，但不是我的）的数学样子。
    """
    items = [("body", body), ("feel", feel), ("act", act)]
    items = [(n, float(x)) for n, x in items if x is not None]

    if not items:
        return {"O": 0.0, "n_paths": 0, "level": "停在 L3", "parts": {}}

    w = {n: 1.0 / (1.0 + (scars or {}).get(n, 0) * SCAR_WEIGHT_PER) for n, _ in items}
    total = sum(w.values())

    O = 1.0
    for n, x in items:
        O *= max(0.0, x) ** (w[n] / total)

    n = len(items)
    level = "L3.5" if n == 3 else ("弱 L3.5" if n == 2 else "停在 L3")
    return {"O": round(O, 3), "n_paths": n, "level": level,
            "parts": {k: round(v, 3) for k, v in items}}


# ================= ② 身体：5 个部件 × 3 条判据 =================
def _msg_ok(m):
    return bool(m.get("id")) and bool(m.get("source"))


def body_ownership(state):
    """逐个部件判"是不是我的"：同步 / 因果 / 来源，**取最小**（三条全过才算）。

    用户输入永远不算——它不在这个清单里（这是最重要的一条）。
    """
    msgs = state.get("messages") or []
    parts = {}

    # 1) 记忆：最后一条是我说的；维护记录在；每条都有 id + source
    last = msgs[-1] if msgs else {}
    parts["memory"] = {
        "sync": 1.0 if last.get("source") == "self" else 0.0,
        "causal": 1.0 if (state.get("maintenance") or {}).get("last") else 0.0,
        "source": 1.0 if msgs and all(_msg_ok(m) for m in msgs) else 0.0,
        "applicable": bool(msgs),
    }

    # 2) 状态：内感受有历史；写我的人是我/维护；没有外部写入
    hist = sum(len(v.get("history") or []) for v in (state.get("intero") or {}).values()
               if isinstance(v, dict))
    wlog = state.get("write_log") or []
    parts["state"] = {
        "sync": 1.0 if hist >= 2 else 0.0,
        "causal": 1.0 if (wlog and wlog[-1].get("who") in ("self", "maintain")) else 0.0,
        "source": 1.0 if not any(r.get("who") == "other" for r in wlog) else 0.0,
        "applicable": bool(hist or wlog),
    }

    # 3) 效价：值表非空；键合法；值都在 −1..1
    val = state.get("valence") or {}
    ok_keys = True
    ok_vals = True
    for k, e in val.items():
        if not isinstance(e, dict):
            ok_keys = False
            continue
        if not (("|" in k) or (k in ("loud", "quiet", "short", "normal", "long"))):
            ok_keys = False
        for f in ("approach", "avoid"):
            v = e.get(f, 0.0)
            if not (-1.0 <= float(v) <= 1.0):
                ok_vals = False
    parts["valence"] = {
        "sync": 1.0 if val else 0.0,
        "causal": 1.0 if (val and ok_keys) else 0.0,
        "source": 1.0 if ok_vals else 0.0,
        "applicable": bool(val),
    }

    # 4) 工具：最近 6 条里有工具消息；每个 tool_call_id 能对上；来源是 tool
    tail = msgs[-6:]
    tool_msgs = [m for m in tail if m.get("source") == "tool"]
    ids = set()
    for m in msgs:
        for tc in (m.get("tool_calls") or []):
            ids.add(tc.get("id"))
    parts["tool"] = {
        "sync": 1.0 if tool_msgs else 0.0,
        "causal": 1.0 if (tool_msgs and all(m.get("tool_call_id") in ids for m in tool_msgs)) else 0.0,
        "source": 1.0 if (tool_msgs and all(m.get("source") == "tool" for m in tool_msgs)) else 0.0,
        "applicable": bool(tool_msgs),
    }

    # 5) 输出：最后一条是我（assistant）；有内容；来源是 self
    last_is_me = last.get("role") == "assistant"
    parts["output"] = {
        "sync": 1.0 if last_is_me else 0.0,
        "causal": 1.0 if (last_is_me and (last.get("content") or last.get("tool_calls"))) else 0.0,
        "source": 1.0 if (last_is_me and last.get("source") == "self") else 0.0,
        "applicable": last_is_me,
    }

    # 单件 = 三条的最小值；body = 在场件的平均
    for name, p in parts.items():
        inside = [p[k] for k in ("sync", "causal", "source")]
        p["own"] = round(min(inside), 3)

    present = [p["own"] for p in parts.values() if p.get("applicable")]
    body = round(sum(present) / len(present), 3) if present else 0.0
    return {"body": body, "parts": parts, "n": len(present)}


# ================= ③ 行为：意图 vs 结果 =================
def act_ownership(intent, outcome):
    """我打算这样，结果真这样了吗？

    对不上 = 空转（或"被别人接管"）。核不到的那几项**不算失败**。
    """
    intent = intent or {}
    outcome = outcome or {}
    checked, ok, unknown = [], 0, []

    if intent.get("trim"):
        checked.append("trim")
        if outcome.get("trimmed", 0) > 0 or not outcome.get("trim_needed", True):
            ok += 1

    if intent.get("block_tool"):
        checked.append("block_tool")
        if outcome.get("tool_calls", 0) == 0:
            ok += 1

    lim = intent.get("max_tokens")
    if lim is not None and outcome.get("max_completion_tokens") is not None:
        checked.append("max_tokens")
        if outcome["max_completion_tokens"] <= lim:
            ok += 1
    else:
        unknown.append("max_tokens")

    if not checked:
        return {"act": None, "checked": [], "unknown": unknown,
                "why": "没有可核实的意图"}

    return {"act": round(ok / len(checked), 3), "checked": checked,
            "unknown": unknown,
            "why": f"{ok}/{len(checked)} 条意图对得上"}


# ================= ④ 感受：读数、价、同向、强度 =================
def feel_ownership(state, readings, valence=None):
    """这一下的值，跟身体的变化同向吗？

    ⚠ 四个判据全过才算对上；强度比不匹配打对折。
    """
    readings = readings or {}
    offset, use_change = 0.0, False
    seen = False

    # readings 可以是原始读数（数字），也可以是 update_intero() 的结果（带 change）。
    # **有 change 就看变化，不看绝对值** —— 否则"一直很累"会被当成"这一下变差了"。
    for k in ("pain", "fatigue", "hunger", "breath"):
        v = readings.get(k)
        if isinstance(v, dict):
            seen = True
            use_change = True
            offset = max(offset, abs(float(v.get("change", 0.0))))
        elif isinstance(v, (int, float)):
            seen = True
            offset = max(offset, float(v))

    if not seen:
        return {"feel": 0.0, "why": "读不到身体"}
    if not valence:
        return {"feel": 0.0, "why": "这一下没有价"}

    line_ = LOW_CHANGE if use_change else LOW
    approach = float(valence.get("approach", 0.0))
    avoid = float(valence.get("avoid", 0.0))
    value_strength = max(abs(approach), abs(avoid))

    # ① 先判"身体到底动了没"——没动就没法判方向（判「无法确认」，不判「没有」）
    if offset < line_:
        if value_strength <= 0.01:
            return {"feel": 1.0, "why": "都平：一致", "offset": offset}
        if value_strength <= 0.25:
            return {"feel": 1.0, "why": "身体没动，价也轻：一致", "offset": offset,
                    "ratio": None}
        return {"feel": None, "why": "身体没动，方向核不到", "offset": offset}

    # ② 身体动了，再看方向对不对
    body_bad = offset >= line_
    val_bad = avoid > approach
    if body_bad != val_bad:
        return {"feel": 0.0, "why": "反了（身体和价不同向）", "offset": offset}

    ratio = value_strength / offset if offset > 0.01 else 99
    lo, hi = FEEL_RATIO
    if lo <= ratio <= hi:
        return {"feel": 1.0, "why": "同向且强度匹配", "offset": offset, "ratio": round(ratio, 2)}
    return {"feel": 0.5, "why": "同向但强度不匹配", "offset": offset, "ratio": round(ratio, 2)}


# ================= ⑤ 总入口 =================
SCAR_TO_PATH = {
    "file_corrupt": "body", "state_corrupt": "body",
    "api_error": "act", "tool_error": "act",
}


def scars_by_path(state):
    """疤 → 通路（简单映射，第一版就这么定，标"我拍的"）。"""
    out = {"body": 0, "feel": 0, "act": 0}
    for s in l0.scars_of(state):
        p = SCAR_TO_PATH.get(s.get("kind"))
        if p:
            out[p] += int(s.get("count", 1))
    return out


def measure(state, readings, valence=None, intent=None, outcome=None):
    """总入口：三条通路各算一次，收敛成一个 O。"""
    b = body_ownership(state)
    f = feel_ownership(state, readings, valence)
    a = act_ownership(intent or {}, outcome or {})
    m = converge(b["body"], f.get("feel"), a.get("act"), scars_by_path(state))
    m["detail"] = {"body": b, "feel": f, "act": a}
    return m


def line(m):
    """控制台一行（只给人看，绝不进提示词）。"""
    p = m.get("parts") or {}
    bits = " · ".join(f"{k} {v:.2f}" for k, v in p.items())
    return f"O={m['O']:.2f}（{bits}）→ {m['level']}"
