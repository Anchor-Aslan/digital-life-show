"""l1_reflex.py —— L1：反射 + 反应 + 合成（10-28 重写）

原则（用户定的）：
  **反射不能被覆盖。** 决策层不许伸手进反射里。
  人的行为 = 反射（身体自己动的）+ 反应（我愿意怎么动）**合成**。

  ❌ 错：上层把反射替换掉（reaction_overrides 那套已废）
  ✅ 对：反射一定发生，反应同时发生，两边合成出一个最终行为

膝跳的例子：
  反射：腿弹了（抹不掉）
  反应：我要继续往前走
  合成：弹一下就弹一下，脚落地继续走

机器版：
  反射：憋 0.9 → 要裁（无条件）
  反应：其中第 5 条是我要留的
  合成：照裁，但跳过第 5 条
"""

import importlib.util
import os
from datetime import datetime

_spec = importlib.util.spec_from_file_location(
    "l0_sense", os.path.join(os.path.dirname(__file__), "l0_sense.py"))
l0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l0)


def threshold_of(state, channel):
    "线也是天性：个体可覆盖，缺省用天性表"
    return l0.trait(state, channel, "threshold")


# ================= 信号层 =================
THRESHOLDS = {
    "breath": 0.80,
    "pain": 0.50,
    "fatigue": 2.00,
    "hunger": 0.80,
    "arousal": 0.80,
    "exclaim_pct": 0.90,
    "chars_pct": 0.95,
}

RATE_TRIGGERS = {"breath": 0.25, "pain": 0.30, "hunger": 0.25}

MIN_EFFECTIVE = 0.05
INHIBIT = 0.60          # 强压弱


def detect(state, readings):
    "水平触发：过线就冒信号"
    fired = []
    for ch in THRESHOLDS:
        v = readings.get(ch)
        if v is None:
            continue
        th = threshold_of(state, ch)
        if v >= th:
            span = max(1e-6, 1.0 - th)
            fired.append({"channel": ch, "value": round(v, 3),
                          "threshold": th,
                          "severity": round(min(1.0, (v - th) / span), 3),
                          "kind": "level"})
    return fired


def detect_rate(readings):
    "速率触发：涨得太快（预警，强度打七折）"
    fired = []
    for ch, th in RATE_TRIGGERS.items():
        r = readings.get(ch + "_rate")
        if r is None or r < th:
            continue
        fired.append({"channel": ch, "value": round(r, 3), "threshold": th,
                      "severity": round(min(1.0, r / max(1e-6, th * 2)) * 0.7, 3),
                      "kind": "rate"})
    return fired


def inhibit(fired):
    "互相抑制：最强的那条压其他（剧痛时听不见别人说话）"
    for f in fired:
        f.setdefault("severity_eff", f["severity"])
    if len(fired) < 2:
        return fired, []
    top = max(fired, key=lambda x: x["severity"])
    factor = max(0.0, 1.0 - INHIBIT * top["severity"])
    kept, suppressed = [top], []
    for f in fired:
        if f is top:
            continue
        eff = round(f["severity"] * factor, 3)
        f["severity_eff"] = eff
        (kept if eff >= MIN_EFFECTIVE else suppressed).append(f)
    top["severity_eff"] = top["severity"]
    return kept, suppressed


# ================= 反射层：无条件执行 =================
# 只出信号、暂时没有预设动作的通道（11-04 加）。
# 为什么允许空着：有些通道的动作根本不该由 L1 定——比如生理唤起改的是"主动性/语气"，
# 那是 L4/L5 的事。**空着但登记在这儿，就不会被当成"假器官"**（审计第 13 步会查）。
SIGNAL_ONLY = {"arousal"}

# L3 的值只以"读数"的形式喂进来，由 L1 决定怎么动——
# 这样"参数唯一写入者是 L1"这条规矩不破。
VALENCE_TIGHTEN = 0.60      # 🎯 躲开到这条线才收（低于它不插手）
VALENCE_LOOSE = 0.25        # 🎯 想要到这条线才松

REACTIONS = {
    "breath": {"trim": True},
    "pain": {"temperature": 0.3},
    "fatigue": {"max_tokens": 400},
    "hunger": {"max_tokens": 400},
    "arousal": {},        # 只出信号；动作等 L4/L5。（以前挂的 max_tokens 500 很牵强，删了）
    "exclaim_pct": {"max_tokens": 400, "temperature": 0.5},
    "chars_pct": {"max_tokens": 700},
}


# ================= 行为风格（任务 3，11-07）=================
# 这是什么：**行为参数**，不是读数。
#   它告诉模型"这一轮怎么说"，不告诉它"为什么"（不说"你累了"，只说"说短点"）。
#   词表是**封闭**的：只能从下面选，不许自由生成文本（防读数泄漏、防跑偏）。
STYLE_VOCAB = {
    "brief":      "这一轮回答尽量短，只说要点。",
    "hedge":      "如果有不同可能，两种都列出来，不要只给一个结论。",
    "confirm":    "先用一句话复述你理解的问题，再回答。",
    "no_extend":  "不要主动展开、不要举例。",
    "no_suggest": "不要主动给建议，只回答被问到的。",
}
STYLE_PRIORITY = ["brief", "no_extend", "confirm", "hedge", "no_suggest"]   # 冲突时前面的优先
STYLE_MAX = 2          # 🎯 一轮最多两条，防止提示词被堆满
# 施工单 5 / 第 2 条（用户选 B）：confirm 冷却。
#   "刚确认过就别再确认"是礼貌，不是把感知弄钝。
#   实测（20 条话题各异）：无冷却 15/20（75%）→ 冷却 5 轮 3/20（15%）。
CONFIRM_COOLDOWN = 5
# 🎯 冷却按**时间**衰减：距上次确认超过 **4 小时**就归 0。
#   理由（用户 11-07 定的数）："我刚问过"本质是**刚刚**，不是"第几轮"；
#   **离开 4 小时以内回来的，还算同一段对话**（去忙一阵/吃个饭不算断）。
#   半天以上再打开 = 新的一段，重新可以问一次。
CONFIRM_DECAY_MIN = 240

# B1（11-07）：风格词表**不许报告内部状态**。
#   "说明你不确定" 这种话等于让模型宣称一个它查不到的账 —— 那是 L4 的事，
#   而且 L4 说之前要先去账上查依据。这张表只管行为。
STYLE_FORBIDDEN = ("确定", "不确定", "把握", "没把握", "犹豫", "纠结")


# ================= 轴 → 行为出口（任务 4，11-07）=================
# 按总纲 Q1b：一根轴要能改变行为才算数。
# 这些阈值都是 🎯 拍的；跑 20 轮真实对话后按触发率调（正常聊天不该超过 30%）。
AXIS_REACTIONS = {
    # ⚠ 11-07：生理恶心以前"只能加 avoid"，而 avoid 的收紧线是 0.60，
    #   恶心最多加 0.50 → **永远推不动行为**（假器官的变种：线太细，电流过不去）。
    #   恶心在人身上的行为倾向是"拒绝接触 + 简短回避"，所以给它自己的出口。
    #   🎯 阈值 0.70：日常聊天基本到不了（实测 20 轮全是 0.00），
    #      只有"长串重复/极端刷屏"这种才够——**稳态正态分布，不许常常恶心**。
    "disgust_physio": {"op": ">=", "th": 0.70,
                       "do": {"max_tokens": 600, "style": ["brief", "no_extend"]}},

    "valence_conflict":      {"op": ">=", "th": 0.35,
                              "do": {"style": ["hedge"]}},          # 又想要又怕 → 不肯说死
    "arousal_axis":          {"op": ">=", "th": 0.70,
                              "do": {"max_tokens": 500, "style": ["brief"]}},   # 绷紧 → 话短
    "valence_control":       {"op": "<=", "th": 0.30,
                              "do": {"tool_choice": "none", "style": ["no_suggest"]}},  # 搞不定 → 不试
    # A3（11-07 修）：以前是"≤0.2 且新键"——但新键 episodic 是 None（被 isinstance 跳过），
    # 旧键又被 only_new_key 挡住，两条永远不能同时成立 → 规则死了。
    # 现在改成"没经历过（None）或 没见过几次（≤0.2）"，频率靠 20 轮实测兜（实测 0/20）。
    # 只在**第一次**见到这类消息时先确认（seen < 1 次 ⇒ episodic < 0.2）
    "valence_precision_epi": {"op": "<", "th": 0.20,
                              "do": {"style": ["confirm"]}},   # 没见过 → 先确认
    "valence_effort":        {"op": ">=", "th": 0.60,
                              "do": {"max_tokens": 600, "style": ["no_extend"]}},       # 费劲 → 不展开
}


def reflex_base():
    return {"max_tokens": 800, "trim": False, "temperature": 0.7,
            "urgent": False, "trim_keep": [],
            "style": [], "tool_choice": "auto"}


def reflex(state, readings):
    """反射：身体自己动。**不看上层脸色，不可覆盖。**

    返回 (params, applied)
    """
    params = reflex_base()
    tightened = False          # A2：只要有任何一处把参数往下压，就不许再"放开"
    fired = detect(state, readings) + detect_rate(readings)

    by_ch = {}
    for f in fired:
        cur = by_ch.get(f["channel"])
        if cur is None or f["severity"] > cur["severity"]:
            by_ch[f["channel"]] = f
    fired = list(by_ch.values())

    kept, suppressed = inhibit(fired)
    applied = []

    for sig in kept:
        ch = sig["channel"]
        for k, v in (REACTIONS.get(ch) or {}).items():
            if k in params:
                if k in ("max_tokens", "temperature") and v < params.get(k, v + 1):
                    tightened = True
                params[k] = v
        applied.append({"channel": ch, "severity": sig["severity_eff"],
                        "kind": sig["kind"], "reaction": REACTIONS.get(ch) or {}})

    # L3 的值：躲得厉害 → 收；想得厉害 → 松。都只是"改参数"，不写值。
    va = readings.get("valence_avoid")
    if isinstance(va, (int, float)) and va >= VALENCE_TIGHTEN:
        tightened = True
        params["max_tokens"] = min(params["max_tokens"], 500)
        params["temperature"] = min(params["temperature"], 0.5)
        applied.append({"channel": "valence", "severity": round(float(va), 3),
                        "kind": "avoid", "reaction": {"max_tokens": 500, "temperature": 0.5}})

    # ---- 轴出口（任务 4）：五根轴各有一个行为后果 ----
    _new_key = not bool(readings.get("_key_seen"))
    _cd = int((state or {}).get("confirm_cooldown", 0) or 0)   # 还剩几轮不许再确认
    _fired_confirm = False
    for _k, _rule in AXIS_REACTIONS.items():
        # 冷却期内：precision 那条直接跳过（已经问过了，别再啰嗦）
        if _k == "valence_precision_epi" and _cd > 0:
            continue
        _v = readings.get(_k)
        # 没有这个读数 ≠ 没经历过：直接跳过这条规则（施工单 3 / 第 2 条）
        if not isinstance(_v, (int, float)):
            continue
        # ⚠ 11-07 施工单 3：以前只认 ">="，其余一律按 "<=" 处理
        #   → 规则写 "<" 也被当成 "<=" 执行（0.2 < 0.2 本该是 False，却算成了 True）。
        if _rule["op"] == ">=":
            _hit = _v >= _rule["th"]
        elif _rule["op"] == "<":
            _hit = _v < _rule["th"]
        else:
            _hit = _v <= _rule["th"]
        if not _hit:
            continue
        _do = _rule["do"]
        # 施工单 4 / 第 1 条：冲突（又想要又怕）时**不许放开**——
        #   它自己不压参数，只挡住"想要"那段。以前 avoid 在 0.35~0.60 之间时，
        #   冲突成立但 avoid 没收紧，于是照样被放开成 900/0.8，行为自相矛盾。
        if _k == "valence_conflict":
            tightened = True
        if "max_tokens" in _do:
            if _do["max_tokens"] < params["max_tokens"]:
                tightened = True
            params["max_tokens"] = min(params["max_tokens"], _do["max_tokens"])
        if "tool_choice" in _do and _do["tool_choice"] == "none":
            params["tool_choice"] = "none"
        for _s in _do.get("style", []):
            if _s in STYLE_VOCAB and _s not in params["style"]:
                params["style"].append(_s)
        if _k == "valence_precision_epi":
            _fired_confirm = True
        applied.append({"channel": "axis:" + _k, "severity": round(float(_v), 3),
                        "kind": "axis", "reaction": _do})
    # 风格按优先级排序，最多两条
    params["style"] = sorted(params["style"],
                             key=lambda s: STYLE_PRIORITY.index(s)
                             if s in STYLE_PRIORITY else 99)[:STYLE_MAX]

    # 想要的另一侧：够想要才"松"——但**只有在没有任何收紧时才允许放开**
    #   A2（11-07 修）：以前这段在最后用 max() 顶掉一切，连"痛→温度 0.3"都会被抬回 0.8，
    #   直接违反"反射不可覆盖、朝保守合"。
    vap = readings.get("valence_approach")
    if isinstance(vap, (int, float)) and vap >= VALENCE_LOOSE:
        if not tightened:
            params["max_tokens"] = max(params["max_tokens"], 900)
            params["temperature"] = max(params["temperature"], 0.8)
            applied.append({"channel": "valence", "severity": round(float(vap), 3),
                            "kind": "approach",
                            "reaction": {"max_tokens": 900, "temperature": 0.8}})
        else:
            applied.append({"channel": "valence", "severity": round(float(vap), 3),
                            "kind": "approach",
                            "reaction": {"suppressed": True, "why": "已有收紧，放开让位"}})

    applied.sort(key=lambda x: -x["severity"])
    for s in suppressed:
        applied.append({"channel": s["channel"], "severity": s["severity_eff"],
                        "kind": s["kind"], "reaction": {"suppressed": True}})

    return params, applied


# ================= 反应层：上层的意思（现在空着） =================
def response(state, readings):
    """上层想干什么。现在返回 None —— 等 L4 来填。

    以后的形状：
      {"params": {"max_tokens": 600},   # 我想输出多长
       "keep_ids": [...],               # 这些消息我要留住
       "reason": "..."}
    """
    return state.get("pending_response") or None


# ================= 合成器 =================
def combine(reflex_params, resp):
    """把反射和反应合成最终行为。

    规则（都朝"更保守"合——反射是保命的，不能被乐观覆盖）：
      max_tokens  取更小
      temperature 取更小
      trim        任一方要裁就裁
      urgent      任一方要就叫
      trim_keep   反应要留的消息，裁的时候跳过
    """
    final = dict(reflex_params)

    if not resp:
        return final

    rp = resp.get("params") or {}
    if "max_tokens" in rp:
        final["max_tokens"] = min(final.get("max_tokens", 800), rp["max_tokens"])
    if "temperature" in rp:
        final["temperature"] = min(final.get("temperature", 0.7), rp["temperature"])
    if rp.get("trim"):
        final["trim"] = True
    if rp.get("urgent"):
        final["urgent"] = True

    # 风格：取并集，按优先级排，截到 STYLE_MAX（11-07 任务 3）
    rs = list(rp.get("style") or [])
    if rs:
        merged = list(dict.fromkeys(list(final.get("style") or []) + rs))
        merged = [s for s in merged if s in STYLE_VOCAB]
        merged.sort(key=lambda s: STYLE_PRIORITY.index(s) if s in STYLE_PRIORITY else 99)
        final["style"] = merged[:STYLE_MAX]

    # 工具：任一方说"别调"就别调（朝保守合）
    if rp.get("tool_choice") == "none":
        final["tool_choice"] = "none"

    keep = resp.get("keep_ids") or []
    if keep:
        final["trim_keep"] = list(dict.fromkeys(final.get("trim_keep", []) + keep))

    return final


def describe(applied):
    if not applied:
        return "没有信号"
    parts = []
    for a in applied:
        tag = "·被压" if a["reaction"].get("suppressed") else ""
        kind = "·速率" if a.get("kind") == "rate" else ""
        parts.append(f"{a['channel']}({a['severity']:.2f}{kind}{tag})")
    return "；".join(parts)


# ================= 抑制器（SIS：性抑制系统，11-04 加） =================
# 医学依据：Bancroft & Janssen 的 dual control model——
#   兴奋（SES）和抑制（SIS）是**两套独立系统**，不是一根轴的两端。
#   证据：急性压力会推高兴奋（越急越想要），慢性压力推高抑制（长期压着就没了）。
#
# 这里只做 SIS：**只作用于 arousal**，不许通吃别的通道。
#   为什么：压力对痛是反向的（压力大 → 痛觉更敏感），一个系数通吃就错了。
SUPPRESSION_MAX = 0.7      # 最多压到三成；**零欲望是 release() 的事，不是系数压出来的**


def suppression(state, p=None):
    """算 arousal 的抑制系数 [-0.7, 0]，由 agent 写进 state["arousal_suppression"]。

    输入全在 L0（同层读取，不越界）：
      疲劳、痛   ← 直接读数（按各自上限归一化）
      慢性压力   ← l0.pressure(state)["chronic"]

    p 可以由调用方传进来，避免重复计算（pressure 每调一次都会记一条历史）。
    """
    if p is None:
        p = l0.pressure(state)
    intero = state.get("intero") or {}
    fat = float((intero.get("fatigue") or {}).get("value", 0.0) or 0.0)
    pain = float((intero.get("pain") or {}).get("value", 0.0) or 0.0)
    chronic = float(p.get("chronic", 0.0) or 0.0)

    load = (0.50 * min(1.0, fat / 3.0)      # 疲劳（上限 3.0）
            + 0.30 * min(1.0, pain / 1.0)   # 痛（上限 1.0）
            + 0.20 * min(1.0, chronic))     # 慢性压力
    return round(-min(SUPPRESSION_MAX, load * SUPPRESSION_MAX), 3)

def decay_confirm_cooldown(state, now=None):
    """按时间衰减冷却（每轮 reflex **之前**调）。

    距上次确认超过 CONFIRM_DECAY_MIN 分钟 → 剩余归 0（当没问过）。
    这样"关掉 10 秒再打开"会继续冷静，"睡一觉再打开"就重新可以问。
    """
    if not isinstance(state, dict):
        return 0
    cd = int(state.get("confirm_cooldown", 0) or 0)
    if cd <= 0:
        return 0
    last = state.get("confirm_last_at")
    if not last:
        return cd
    try:
        dt = datetime.now() - datetime.fromisoformat(str(last))
        if dt.total_seconds() >= CONFIRM_DECAY_MIN * 60:
            state["confirm_cooldown"] = 0
            return 0
    except Exception:
        pass
    return cd


def note_confirm_cooldown(state, applied):
    """按这一轮的 applied 更新 confirm 冷却（**在 reflex 外面**，一轮只写一次）。

    ⚠ 施工单 6 / 第 1 条：reflex() 必须**只读**。
      以前它自己写 state，于是"预览一下参数"（启动打印、探针、调试）也会吃掉一格冷却。
      现在读还在 reflex 里（冷却期内跳过 precision 规则），写集中在这一个函数，
      由 agent 主循环每轮调一次。
    """
    if not isinstance(state, dict):
        return False
    fired = any(a.get("channel") == "axis:valence_precision_epi" for a in (applied or []))
    cd = int(state.get("confirm_cooldown", 0) or 0)
    if fired:
        state["confirm_cooldown"] = CONFIRM_COOLDOWN
        state["confirm_last_at"] = datetime.now().isoformat()
    else:
        state["confirm_cooldown"] = max(0, cd - 1)
    return fired
