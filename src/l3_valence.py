"""l3_valence.py —— L3 效价（值能迁移，才算到了 L3）

一句话：
    **L2 记的是"这条路有坑"（策略）；L3 记的是"这东西值多少"（价值）。**
    策略跟着动作走，价值跟着对象走。

这一版只做三件事（规格见 `工程/L3-工程图.md`）：
    ① extract_features()  把刺激变成键（3 轴，全用表面信号，绝不碰语义）
    ② learn()             学：精确键学得快、粗键学得慢（双键）
    ③ retrieve()/value_of() 取：按"部分匹配 × 值强度 × r"排序，取 top-k

**不做**（防错层）：
    不说"我觉得"（L4）· 不给情绪起名字（L4）· 不直接改行为参数（L1 是唯一写入者）
    **不把值写进提示词**（审计第 12 步）

**留给 L3.5 的两样**（不是不做，是换到"系数层"做，见 H10）：
    内感受进评价、controllable（可控性）—— 都是"值先算，系数后乘"里的系数。
"""

import importlib.util
import os
from datetime import datetime

_BASE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("l0_sense", os.path.join(_BASE, "l0_sense.py"))
l0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l0)

# ================= 参数（每个都标了来源） =================
ALPHA_EXACT = 0.30          # ✅ 08 已在用：具体的事记得清楚
ALPHA_COARSE = 0.08         # ✅ 08 已在用：类别判断要很多例
EXTINCT_RATIO = 1.0         # 🎯 消退用同一个学习率（reward=0 时朝 0 走）

R_HALF_LIFE_HOURS = 72      # 🎯 我拍的：3 天不碰，r 掉一半
TOP_K = 4                   # 🎯 工作记忆 4±1，取中
THETA = 0.15                # 🎯 低于这个不提（想不起来）
MATCH_DECAY = 0.70          # 🎯 部分匹配系数（差一轴 ×0.7）
SUMMARY_LEN = 20            # 🎯 摘要最多 20 字（只给控制台，不进提示词）

COARSE_W = 0.6              # 🎯 粗键优先（模糊痕迹理论：先要点，再细节）
EXACT_W = 0.4

LOUDNESS_THRESHOLD = 0.35   # ✅ 08 已在用
PACE_FAST = 30              # ✅ 08 已在用（秒）
PACE_SLOW = 900             # ✅ 08 已在用（秒）
LEN_SHORT = 10              # 🎯 我拍的：中文 10 字以内是一句话
LEN_LONG = 50               # 🎯 我拍的：50 字以上算长段

BAD_WEIGHT = 2.25           # ✅ Tversky & Kahneman 1992（损失厌恶中位约 2.25）
BAD_WEIGHT_NORMAL = (1.5, 3.5)     # 正常人范围：出厂只落这里
BAD_WEIGHT_EXTREME = (1.0, 6.0)    # 人能达到的极端；再外面是病理，必须点名

# ================= 出厂表（L3a：很小，只是起点） =================
VALENCE_INITIAL = {
    "loud":   {"approach": -0.05, "avoid": 0.10},   # 大声天生偏负
    "quiet":  {"approach":  0.00, "avoid": 0.00},
    "short":  {"approach":  0.00, "avoid": 0.00},
    "normal": {"approach":  0.00, "avoid": 0.00},
    "long":   {"approach":  0.00, "avoid": 0.00},
}


# ================= ① 特征抽取 =================
def loudness(text):
    """音量感：感叹号、问号、长度、全大写。**全是表面特征**（跟 08 同一套）。"""
    t = text or ""
    score = 0.0
    score += 0.35 * min(3, t.count("!") + t.count("！"))
    score += 0.15 * min(3, t.count("?") + t.count("？"))
    if len(t) > 60:
        score += 0.25
    if len(t) <= 2:
        score += 0.15          # 极短（"嗯""哦"）也算强刺激：冷
    return min(1.0, score)


def _gap_seconds(state, now):
    """距上次对话多久。没记录 → 当成正常间隔（900 秒以内）。"""
    last = (state or {}).get("last_seen")
    if not last:
        return 60.0
    try:
        return max(0.0, (now - datetime.fromisoformat(last)).total_seconds())
    except Exception:
        return 60.0


def extract_features(text, state=None, now=None):
    """把一条刺激变成键。

    三条轴全用**表面信号**——不碰语义。
    "被骂"需要知道"骂"是什么（L4 的事）；L3 只知道：响不响、快不快、长不长。

    返回 {"vol","pace","len","exact","coarse","chars","gap"}
    """
    now = now or datetime.now()
    raw = l0.external_raw(text)

    vol = "loud" if loudness(text) >= LOUDNESS_THRESHOLD else "quiet"

    gap = _gap_seconds(state, now)
    if gap < PACE_FAST:
        pace = "fast"
    elif gap <= PACE_SLOW:      # 工程图 §4.1：normal = 30–900 秒（含 900）
        pace = "normal"
    else:
        pace = "slow"

    n = raw["chars"]
    if n < LEN_SHORT:
        ln = "short"
    elif n <= LEN_LONG:
        ln = "normal"
    else:
        ln = "long"

    return {"vol": vol, "pace": pace, "len": ln,
            "fp": char_bigrams(text),
            "exact": f"{vol}|{pace}|{ln}",
            "coarse": vol,              # 粗键只取音量轴：它最稳
            "chars": n, "gap": round(gap, 1)}


# ================= ② 学习（双键 + 负面偏差） =================
def _clamp(x):
    return max(-1.0, min(1.0, x))


def _entry(state, key, now, init=None):
    tbl = state.setdefault("valence", {})
    e = tbl.get(key)
    if e is None:
        if init is None:
            init = (VALENCE_INITIAL.get(key)
                    or VALENCE_INITIAL.get(key.split("|")[0]) or {})
        else:
            init = init or {}
        e = {"approach": float(init.get("approach", 0.0)),
             "avoid": float(init.get("avoid", 0.0)),
             "r": 0.90 if key in VALENCE_INITIAL else 0.60,
             "last_touch": now.isoformat()}
        tbl[key] = e
    return e


def bad_weight_of(state):
    """这一轮用的负面偏差权重（出厂 2.25，可由人设/状态改）。"""
    return float((state or {}).get("bad_weight", BAD_WEIGHT))


def _apply_bad_weight(reward, w=None):
    """负 reward 乘权重（正的不乘），并 clamp —— 不然会越学越极端。"""
    if reward >= 0:
        return reward
    w = BAD_WEIGHT if w is None else w
    return _clamp(reward * w)


def _update(state, key, reward, alpha, now, init=None):
    """学一次。init = 这个键**刚建出来**时该用的初值（None = 用 VALENCE_INITIAL 的默认查找）。

    ⚠ 施工单 3 / 第 6 条：指纹键以前从 0 起，把出厂的"大声天生偏负"
      （loud → approach -0.05）在合成时稀释掉了，表现为"被伤之后反而更想靠近"。
      现在建指纹键时继承本句音量档的出厂底色。
    """
    e = _entry(state, key, now, init=init)
    if reward >= 0:
        e["approach"] = _clamp(e["approach"] + alpha * reward)
    else:
        e["avoid"] = _clamp(e["avoid"] + alpha * (-reward))
    e["r"] = min(1.0, float(e.get("r", 0.6)) + 0.10)   # 用过一次 → 更容易想起来
    e["hits"] = int(e.get("hits", 0)) + 1             # 学过几次（亲历精度要用）
    e["last_touch"] = now.isoformat()
    return e


def learn(state, features, reward, now=None):
    """学一次。reward > 0 好，< 0 坏，**= 0 消退（后果没了）**。

    精确键学得快（0.30）、粗键学得慢（0.08）——具体的事记得清楚，类别要靠很多例。
    reward=0 表示"这次没有后果"：值朝 0 消退（这是"结果贬值"实验 B 要求的），
    不是"什么都不知道"。想表达"这轮没有信息"，**别调这个函数**。
    """
    now = now or datetime.now()

    if reward == 0:
        r0 = 0.0
        out = {}
        _init_vol = VALENCE_INITIAL.get(features.get("vol")) or {}
        _pairs = [(features["exact"], ALPHA_EXACT * EXTINCT_RATIO, None),
                  (features["coarse"], ALPHA_COARSE * EXTINCT_RATIO, None)]
        for _g in (features.get("fp") or []):
            _pairs.append((_fp_key(_g),
                           ALPHA_FP * EXTINCT_RATIO / max(1, len(features["fp"])),
                           _init_vol))
        for key, alpha, _ini in _pairs:
            e = _entry(state, key, now, init=_ini)
            e["approach"] = round(e["approach"] * (1 - alpha), 4)
            e["avoid"] = round(e["avoid"] * (1 - alpha), 4)
            e["last_touch"] = now.isoformat()
            out[key] = e
        return out

    w = bad_weight_of(state)
    r = _apply_bad_weight(float(reward), w)

    out = {}
    out[features["exact"]] = _update(state, features["exact"], r, ALPHA_EXACT, now)
    out[features["coarse"]] = _update(state, features["coarse"], r, ALPHA_COARSE, now)

    # 感知指纹：每个二元组学一点，总量固定（句子越长每条分到的越少）
    grams = features.get("fp") or []
    if grams:
        per = ALPHA_FP / max(1, len(grams))
        for g in grams:
            _update(state, _fp_key(g), r, per, now,
                    init=VALENCE_INITIAL.get(features.get("vol")) or {})
        _fp_evict(state)

    keys = state.setdefault("valence_keys", [])
    for k in (features["exact"], features["coarse"]):
        if k not in keys:
            keys.append(k)
    state["valence_keys"] = keys[-200:]
    return out


# ================= ③ 检索 =================
def _r_decayed(e, now):
    hours = 0.0
    try:
        hours = max(0.0, (now - datetime.fromisoformat(e["last_touch"])).total_seconds() / 3600)
    except Exception:
        pass
    return float(e.get("r", 0.5)) * (0.5 ** (hours / R_HALF_LIFE_HOURS))


def _match(entry_key, features):
    """部分匹配：精确键全中 = 1.0；差一轴 ×0.7；差两轴 ×0.49；差三轴 = 0。"""
    if "|" not in entry_key:
        return 1.0 if entry_key == features["coarse"] else 0.0
    parts = entry_key.split("|")
    mine = [features["vol"], features["pace"], features["len"]]
    if len(parts) != 3:
        return 0.0
    diff = sum(1 for a, b in zip(parts, mine) if a != b)
    if diff >= 3:
        return 0.0
    return round(MATCH_DECAY ** diff, 4)


def _learned(tbl, key):
    """这个键**真的学过**吗？

    ⚠ 施工单 5 / 第 1 条：`note_seen()` 会给"见过的"精确键建一条记录（hits=0），
      它只是**记账**，不是值。以前 value_of 见到键存在就当证据，
      结果"见过一面"就把从粗键迁移过来的值冲淡三分之一。
      读值的地方必须区分「见过」和「学过」。
    """
    e = (tbl or {}).get(key)
    return isinstance(e, dict) and int(e.get("hits", 0) or 0) > 0


def retrieve(state, features, now=None):
    """取 top-k：激活 = 部分匹配 × 值强度 × r，低于 θ 丢掉。"""
    now = now or datetime.now()
    tbl = state.get("valence") or {}
    rows = []
    for key, e in tbl.items():
        if int((e or {}).get("hits", 0) or 0) <= 0:
            continue          # 只是"见过"的记账，不是值（施工单 5 / 第 1 条）
        m = _match(key, features)
        if m <= 0:
            continue
        strength = max(abs(float(e.get("approach", 0.0))), abs(float(e.get("avoid", 0.0))))
        act = m * strength * _r_decayed(e, now)
        if act < THETA:
            continue
        rows.append({"key": key, "avoid": round(float(e.get("avoid", 0.0)), 3),
                     "approach": round(float(e.get("approach", 0.0)), 3),
                     "r": round(_r_decayed(e, now), 3), "act": round(act, 3),
                     "src": "exact" if m >= 1.0 and "|" in key else "coarse"})

    rows.sort(key=lambda x: -x["act"])
    rows = rows[:TOP_K]
    return {"hits": rows, "matched": len(rows)}


def value_of(state, features, now=None, text=None, msgs=None):
    """给 L1 用的两个数：这一下有多想靠近 / 多想躲开。

    粗键优先：先看要点（gist），再被细节修正（FTT）。
    """
    now = now or datetime.now()
    tbl = state.get("valence") or {}

    def _get(key):
        e = tbl.get(key)
        if e is None:
            init = VALENCE_INITIAL.get(key) or VALENCE_INITIAL.get(key.split("|")[0]) or {}
            return float(init.get("approach", 0.0)), float(init.get("avoid", 0.0))
        return float(e.get("approach", 0.0)), float(e.get("avoid", 0.0))

    c_ap, c_av = _get(features["coarse"])
    e_ap, e_av = _get(features["exact"])

    # 只有**学过**的精确键才算证据；只是"见过"（note_seen 建的记账条目）不算。
    # 施工单 5 / 第 1 条：否则"见过一面"就会把从粗键迁移过来的值冲淡三分之一。
    _learned_exact = _learned(tbl, features["exact"])
    _learned_coarse = _learned(tbl, features["coarse"])
    if _learned_exact and _learned_coarse:
        approach = c_ap * COARSE_W + e_ap * EXACT_W
        avoid = c_av * COARSE_W + e_av * EXACT_W
    elif _learned_exact:
        approach, avoid = e_ap, e_av
    else:
        approach, avoid = c_ap, c_av

    r = retrieve(state, features, now)

    # 指纹那一半（任务 6）：字形层面的分辨
    #   权重 = 上限 × 覆盖率（11-07 修 C1）：
    #   一句话大部分字没学过时，不许用"0"去稀释已经学到的精确键和粗键。
    _fp_ap, _fp_av, _cov = fp_value_of(state, text or "")
    _w = FP_W_MAX * _cov
    if _w > 0:
        approach = (1 - _w) * approach + _w * _fp_ap
        avoid = (1 - _w) * avoid + _w * _fp_av

    # 学来的值 + 此刻身体的推力（不进键，见 BODY_PULL 那段注释）
    pull = body_pull(state.get("last_readings") or {}, state)
    dis = disgust_pull(text, msgs, sens=hygiene_sensitivity(state))
    pull["avoid"] = round(min(1.0, pull["avoid"] + dis["avoid"]), 3)
    pull["approach"] = round(pull["approach"] + dis["approach"], 3)
    approach = round(min(1.0, max(-1.0, approach + pull["approach"])), 3)
    avoid = round(min(1.0, max(-1.0, avoid + pull["avoid"])), 3)

    ar = arousal_axis(state, state.get("last_readings") or {}, None)
    ar = round(min(1.0, ar + dis["arousal"]), 3)     # 恶心会把唤醒往上抬

    return {"approach": approach, "avoid": avoid,
            "arousal": ar,
            "disgust_physio": dis["physio"],
            "disgust_semantic": dis["semantic"],
            "conflict": conflict_of(approach, avoid),
            "effort": effort_of(state),
            "control_sense": control_sense(state),
            "precision": precision_of(state, features),
            "hits": r["hits"], "matched": r["matched"]}


# ================= 负面偏差的三段区间（唯一写入入口） =================
def set_bad_weight(state, v, by="system"):
    """写 bad_weight 的**唯一入口**。

    by="system"   → 只能写常态区（出厂抽样走这里）
    by="persona"  → 能写极端区（人设卡）
    by="explicit" → 能写病理区，但必须留痕（flag_extreme）
    """
    v = float(v)
    lo, hi = BAD_WEIGHT_EXTREME
    if not (lo <= v <= hi):
        if by != "explicit":
            raise ValueError("病理区必须显式点名（by='explicit'）")
        state["flag_extreme"] = True
    elif by == "system":
        nlo, nhi = BAD_WEIGHT_NORMAL
        if not (nlo <= v <= nhi):
            raise ValueError("出厂只能写常态区 %.2f–%.2f" % (nlo, nhi))
    state["bad_weight"] = round(v, 3)
    return state["bad_weight"]


def sample_bad_weight(seed=None):
    """出厂抽样：落正常区，均值≈2.25（不偏）。

    用正态截断（中间多、两头少），不用均匀分布——人格特质是正态的。
    """
    import random
    rnd = random.Random(seed)
    lo, hi = BAD_WEIGHT_NORMAL
    while True:
        v = rnd.gauss(BAD_WEIGHT, 0.45)
        if lo <= v <= hi:
            return round(v, 3)


# ================= 控制台一行（只给人看） =================
def line(features, val):
    hits = val.get("hits") or []
    top = hits[0]["key"] if hits else "无"
    return (f"键={features['exact']} · 靠近 {val['approach']:+.2f} / 躲开 {val['avoid']:+.2f}"
            f" · 想起 {val['matched']} 条（最紧：{top}）")

# ================= 总唤醒（PAD 的 Y 轴）11-06 定 =================
# 为什么 0 不是"平静"：读数全 0 → 晕过去才算 0；人清醒时本来就有基础激活。
AROUSAL_SOURCES = {"pain": 0.40, "breath": 0.30, "arousal": 0.30}
AROUSAL_BASE = 0.15          # 🎯 清醒时的基础唤醒（睡着才是 0）
PRESSURE_W = 0.25            # 🎯 急性压力当激活
# **不加 fatigue**——累是"资源耗尽"，不是"激活"


def arousal_axis(state, readings, p=None):
    """总唤醒（0 = 昏迷，1 = 极度激动）。

    ⚠ 三个坑（写在规格里的）：
      ① 别跟 l0.arousal() 混——那个是"性唤起"，这个是"总唤醒"，所以函数名带 _axis
      ② pressure() 有副作用（每次调都记一条历史）→ 能从外面传 p 就传进来
      ③ 通道是 None（关着）时 continue，**不许当 0 算**——那会把"没这条通道"算成"很平静"
    """
    v = 0.0
    for ch, w in AROUSAL_SOURCES.items():
        x = (readings or {}).get(ch)
        if x is None:
            continue
        v += w * float(x)
    if p is None:
        p = l0.pressure(state)
    return round(max(0.0, min(1.0, AROUSAL_BASE + v + PRESSURE_W * float(p.get("acute", 0.0)))), 3)

# ================= 身体读数 → 当下两条轴（11-06 加）=================
# 全景表 §六 第 3 步："五条读数 → 两条轴"。
# 注意：**这不是进键**（进键会把"今天我很痛"焊进"loud"这个类别的值里，见踩坑 #31）。
# 它是"此刻的身体直接把当下的值抬高"——同一个值表，不同时刻读出来不一样。
BODY_PULL = {
    "pain":     ("avoid", 0.50),      # 🎯 痛 → 更想躲（0 = 不痛，方向天然对）
    "breath":   ("avoid", 0.40),      # 🎯 憋 → 更想躲（0 = 不憋）
    "hunger":   ("avoid", 0.30),      # 🎯 饿 → 想躲（0 = 不饿）
    "arousal":  ("approach", 0.50),   # 🎯 性唤起 → 更想靠近（L0 那个 arousal，不是总唤醒）
}
# ⚠ 累**不在这里**：L0 的 fatigue 读数在"正常速度"时就等于 1.0（>1 才是累），
#   直接乘 0.30 会让它出厂就背 0.30 的"想躲"。累要用**体力桶的累积值**（见下）。


def body_pull(readings, state=None):
    """此刻身体把两条轴抬高多少。关着的通道跳过（None 不当 0）。

    累（fatigue）单独处理：用体力桶里**真积累下来的量**，
    不用 fatigue 读数——那个读数 1.0 是"正常速度"，不是"累"。
    """
    out = {"approach": 0.0, "avoid": 0.0}
    for ch, (axis, w) in BODY_PULL.items():
        x = (readings or {}).get(ch)
        if x is None or isinstance(x, dict):
            continue
        out[axis] += w * float(x)

    if state is not None:
        pool = 0.0
        try:
            pool = float((state.get("fatigue_pool") or {}).get("value", 0.0))
        except Exception:
            pool = 0.0
        out["avoid"] += 0.30 * max(0.0, min(1.0, pool))     # 🎯 桶里积了多少才躲多少

    return {k: round(min(1.0, v), 3) for k, v in out.items()}


# ================= conflict：又想要又怕（11-06 加）=================
def conflict_of(approach, avoid):
    """两维的第三样东西：冲突。一维轴做不出"犹豫"，这个就是犹豫的那个数。"""
    return round(min(max(0.0, float(approach)), max(0.0, float(avoid))), 3)


# ================= effort：要花多少力气（11-06 加）=================
EFFORT_LATENCY_MS = 3000      # 🎯 超过 3 秒算"慢"，慢=费劲


def effort_of(state):
    """0 = 很轻松，1 = 很费劲（11-07 规格 §4.8.3）。

        0.6 × 延迟（>3 秒算满） + 0.4 × 体力桶（/3 打满） + 0.30 × 累（/3，各打对折别翻倍）
    """
    lat = float(state.get("last_latency_ms") or 0)
    pool = float((state.get("fatigue_pool") or {}).get("value", 0) or 0)
    fat = 0.0
    try:
        fat = float((state.get("intero") or {}).get("fatigue", {}).get("value", 0) or 0)
    except Exception:
        fat = 0.0
    v = 0.6 * min(1.0, lat / EFFORT_LATENCY_MS) + 0.4 * min(1.0, pool / 3.0) + 0.30 * (fat / 3.0)
    return round(max(0.0, min(1.0, v)), 3)


def effort_of_old(state):
    """旧版（留个参考，不调用）：0.6*pool + 0.4*lat"""
    pool = 0.0
    try:
        pool = float((state.get("fatigue_pool") or {}).get("value", 0.0))
    except Exception:
        pool = 0.0
    pool = max(0.0, min(1.0, pool))

    lat = 0.0
    try:
        lat = float(state.get("last_latency_ms") or 0)
    except Exception:
        lat = 0.0
    lat_n = max(0.0, min(1.0, lat / EFFORT_LATENCY_MS)) if EFFORT_LATENCY_MS else 0.0

    return round(max(0.0, min(1.0, 0.6 * pool + 0.4 * lat_n)), 3)


# ================= controllable：我能不能搞定（11-06 加）=================
CONTROL_WINDOW = 10           # 🎯 看最近 10 轮


def control_sense(state):
    """控制感（PAD 的 D 轴）：**我觉得**我能不能控制。

    ⚠ 11-07 改名：controllable → control_sense。
      因为它算的是"我觉得"，不是"客观上能不能"——后者要 L4 的推理（影子对照）。

    ⚠ 没数据给 0.5，不给 0：0 是"完全控制不了"（一个结论），没数据只是"还没结论"。
    """
    tr = (state.get("trace") or [])[-CONTROL_WINDOW:]
    pairs = []
    for row in tr:
        parts = (row.get("ownership") or {}).get("parts") or {}
        act = parts.get("act")
        # trace 里存的是 converge() 的 parts（已经是数字）；也兼容嵌套 dict 的写法
        if isinstance(act, dict):
            act = act.get("act")
        if act is not None:
            pairs.append(float(act))
    if not pairs:
        return 0.5                       # 没数据 = 还没结论（不是"控制不了"）
    return round(sum(pairs) / len(pairs), 3)


# 旧名保留兼容（文档里已统一用 control_sense）
def controllable_of(state):
    return control_sense(state)


# ================= precision：我猜得准吗（两层）=================
def precision_of(state, features=None):
    """precision 分两层（11-07 规格 §4.8.2）：

        episodic（亲历）：这个键我学过几次 → hits/5 封顶 1.0
        semantic（语言）：判"这是用户在陈述事实"要语义 → **第一版恒 0，不许编**

    这就是"我知道但我没经历过"现在做不出来的原因：不是不做，是缺 L4 的判断力。
    """
    epi = 0.0
    if features:
        # 施工单 4 / 第 6 条（B）：亲历度 = **这句的字形有多少是见过的**。
        #   以前按"形状（响×快×长，18 格）"算，聊几句就都见过 → confirm 成了死规则（1/20）。
        #   现在只看字形，仍然不碰语义。
        grams = features.get("fp") or []
        fp_seen = (state or {}).get("fp_seen") or {}
        # "太短的话不值得确认"：两三个字（你好/在吗/嗯）本来就没什么要复述的。
        # 没有这条，20 条普通消息会触发 15 次（75%），人会烦。
        _chars = int(features.get("chars", 0) or 0)
        if grams and _chars >= 6:
            known = sum(1 for g in grams if int(fp_seen.get(g, 0) or 0) > 0)
            epi = known / len(grams)
        elif grams:
            epi = 1.0        # 太短 → 当"没什么可确认的"，不给 confirm
        else:
            e = (state.get("valence") or {}).get(features.get("exact")) or {}
            seen = int(e.get("seen", e.get("hits", 0)) or 0)
            epi = min(1.0, seen / 5.0)
    else:
        epi = control_sense(state)
    return {"episodic": round(epi, 3), "semantic": 0.0,
            "why": "semantic 恒 0：判「陈述事实」要语义 → L4"}

# ================= 信息卫生（原 distaste）11-07 定 =================
# 用户砍了两刀：① 脏话/人身攻击是语义 → 不许 ② 连"臭"的字面也不许（否定词会骗人）
# 所以这里**只看形式**：刷屏 / 无意义重复 / 超长无标点。不判内容。
# ⚠ 11-07 改：这组阈值原来太敏感——连发两句"在吗"、打五个"啊"就判成刷屏。
#   根因是**没有样本量门槛**（2 条里 2 条一样 = 100% 重复）。
#   现在按"正常人"定：恶心在正常人身上是**罕见**的（频率保真）。
HYGIENE = {
    "repeat_min_msgs": 5,     # 🎯 至少 5 条用户消息才判刷屏
    "repeat_ratio": 0.8,      # 🎯 5 条里 4 条一模一样才算
    "single_min_len": 12,     # 🎯 少于 12 字不看单字占比（五个"啊"是撒娇，不是恶心）
    "single_ratio": 0.7,      # 🎯 12 字以上、单字占比 70%
    "long_len": 800,          # 🎯 800 字以上……
    "long_punct": 2,          # 🎯 ……而且标点少于 2 个
}

# 敏感度：出厂只落常态区；极端要人设卡；病理必须点名（跟 bad_weight 同一套规矩）
HYGIENE_SENS_NORMAL = (0.8, 1.5)
HYGIENE_SENS_EXTREME = (0.5, 3.0)
HYGIENE_SENS = 1.0            # 1.0 = 正常人；越小越容易恶心


def hygiene_sensitivity(state):
    return float((state or {}).get("hygiene_sensitivity", HYGIENE_SENS))


def set_hygiene_sensitivity(state, v, by="system"):
    """写敏感度的**唯一入口**。by=system 只能落常态区；病理必须显式点名。"""
    v = float(v)
    lo, hi = HYGIENE_SENS_EXTREME
    if not (lo <= v <= hi):
        if by != "explicit":
            raise ValueError("病理区必须显式点名（by='explicit'）")
        state["flag_extreme"] = True
    elif by == "system":
        nlo, nhi = HYGIENE_SENS_NORMAL
        if not (nlo <= v <= nhi):
            raise ValueError("出厂只能写常态区 %.2f–%.2f" % (nlo, nhi))
    state["hygiene_sensitivity"] = round(v, 3)
    return state["hygiene_sensitivity"]


def _repeat_ratio(msgs, min_msgs=5, window=6):
    """最近几条用户消息里，重复最多的那句占多少。**条数不够就返回 0**（防 2 条判 100%）。"""
    texts = [m.get("content") or "" for m in (msgs or [])
             if m.get("source") == "user"][-window:]
    if len(texts) < min_msgs:
        return 0.0
    counts = {}
    for t in texts:
        counts[t] = counts.get(t, 0) + 1
    return max(counts.values()) / len(texts)


def _single_char_ratio(text):
    t = text or ""
    if not t:
        return 0.0
    counts = {}
    for ch in t:
        counts[ch] = counts.get(ch, 0) + 1
    return max(counts.values()) / len(t)


def _punct_count(text):
    return sum(1 for ch in (text or "") if ch in "，。！？、；：,.!?;:~～…—-()（）")


def hygiene_score(text, msgs=None, sens=None):
    """0 = 干净，1 = 全是垃圾结构。**只看形式，不碰内容。**

    三道门槛都是为了"正常人不该动不动就恶心"（11-07 用户指出：连发两句、打五个"啊"就触发，太敏感）。
    """
    s = 0.0
    if _repeat_ratio(msgs, HYGIENE["repeat_min_msgs"]) >= HYGIENE["repeat_ratio"]:
        s += 0.4
    t = text or ""
    if len(t) >= HYGIENE["single_min_len"] and _single_char_ratio(t) > HYGIENE["single_ratio"]:
        s += 0.3
    if len(t) > HYGIENE["long_len"] and _punct_count(t) < HYGIENE["long_punct"]:
        s += 0.3
    if s:
        k = (1.0 / (sens if sens else 1.0))      # 敏感度只缩放最终分，不改阈值
        s = s * k
    return round(min(1.0, max(0.0, s)), 3)

# ================= 恶心：**两个可分离的指标**（11-07 定）=================
# 用户 11-07 的判断（对的，有文献支持）：
#   "生理上恶心" 和 "精神上觉得这人恶心" 是两个东西，能同时在场、能反向。
#   （岛叶损伤：核心厌恶没了、道德厌恶完好 → 两套硬件能单独坏）
#   还知道：闻着臭味的房间里，人对道德故事判得更严 → 生理那半会**单向抬高**语义那半。
#
# 所以我们不合成一个数，存两个分量：
#   physio   生理/结构层面的不适（L3 能做：形式卫生 + 内感受代理）
#   semantic 语义/道德层面的恶心（L4 才有资格判）
DISGUST_SOURCES = {
    "physio":   {"layer": "L3", "w": 0.6, "on": True},
    "semantic": {"layer": "L4", "w": 0.4, "on": False},   # ← L4 点亮这行即可
}
DISGUST_AVOID_W = 0.5         # 🎯 恶心 → 躲开
DISGUST_APPROACH_W = -0.2     # 🎯 恶心 → 不想靠近
DISGUST_AROUSAL_W = 0.2       # 🎯 恶心 → 绷紧


def disgust_pull(text, msgs=None, semantic=None, sens=None):
    """恶心的**轮廓**：躲开 + 不想靠近 + 绷紧。

    返回两个分量（physio / semantic）+ 合成后的三分量。
    **两个分量都留着**——不然"生理很恶心但精神上认可他"就表示不出来。
    """
    parts = {}

    if DISGUST_SOURCES["physio"]["on"]:
        parts["physio"] = hygiene_score(text, msgs, sens)

    # semantic 那半：L4 算好了就明确传进来（传了就用；on 只当"接线了没有"的标记）
    if semantic is not None:
        parts["semantic"] = max(0.0, min(1.0, float(semantic)))

    if not parts:
        return {"physio": 0.0, "semantic": None,
                "avoid": 0.0, "approach": 0.0, "arousal": 0.0, "parts": {}}

    wsum = sum(DISGUST_SOURCES[k]["w"] for k in parts)
    s = min(1.0, sum(DISGUST_SOURCES[k]["w"] * v for k, v in parts.items()) / wsum)
    return {"physio": parts.get("physio", 0.0),
            "semantic": parts.get("semantic"),
            "avoid": round(DISGUST_AVOID_W * s, 3),
            "approach": round(DISGUST_APPROACH_W * s, 3),
            "arousal": round(DISGUST_AROUSAL_W * s, 3),
            "parts": parts}

# ================= 感知指纹（任务 6，11-07）=================
# 问题：只有"响/快/长"三轴 → 18 个格子 →「太棒了！！！」和「你真讨厌！！！」
#       落进同一格，学一个另一个也跟着倒霉。
# 原则：不懂意思 ≠ 只能看感叹号。对纯文本生物，**字形就是它的感官表面**。
# 红线：只用原始字符；不许词表/情感词典/分词/embedding/任何模型。
import re as _re

FP_CAP = 2000        # 🎯 fp: 键最多这么多，超了淘汰 r 最低的
FP_W_MAX = 0.6       # 🎯 指纹权重**上限**；实际权重 = FP_W_MAX × 这句的覆盖率
# 学习率和 ALPHA_EXACT 同量级：一句话的**字形**和这句话的**精确键**一样具体。
# （不再是"为了让测试通过而拧"——测试改成分化条件化训练，不再靠参数凑）
ALPHA_FP = 0.30


def _norm_text(text):
    """去标点、空白、下划线——只留字。"""
    return _re.sub(r"[\s\W_]+", "", text or "")


def char_bigrams(text, cap=30):
    """字符二元组（有序、去重、最多 cap 个）。**纯字形，不涉及含义。**"""
    t = _norm_text(text)
    return list(dict.fromkeys(t[i:i + 2] for i in range(len(t) - 1)))[:cap]


def _fp_key(gram):
    return "fp:" + gram


def _fp_evict(state):
    """fp: 键超过上限时，淘汰 r 最低的那些。"""
    tbl = state.setdefault("valence", {})
    fps = [k for k in tbl if k.startswith("fp:")]
    if len(fps) <= FP_CAP:
        return
    fps.sort(key=lambda k: float((tbl[k] or {}).get("r", 0.0)))
    for k in fps[: len(fps) - FP_CAP]:
        tbl.pop(k, None)


def fp_value_of(state, text):
    """这句的指纹值：**全部**二元组的平均（没学过的按 0 算）。

    ⚠ 分母是"这句有几个二元组"，不是"学过几个"——
      否则没学过的句子会直接跳过指纹那一半，等于没做分辨。
    """
    grams = char_bigrams(text)
    if not grams:
        return 0.0, 0.0, 0.0
    tbl = state.get("valence") or {}
    known = [tbl[_fp_key(g)] for g in grams if _fp_key(g) in tbl]
    if not known:
        return 0.0, 0.0, 0.0
    ap = sum(float(e.get("approach", 0.0)) for e in known) / len(known)
    av = sum(float(e.get("avoid", 0.0)) for e in known) / len(known)
    # 覆盖率：这句里有多少二元组是学过的（0..1）——权重按它来，别拿没学过的稀释已学的
    return (ap, av, len(known) / len(grams))


# ================= 用户反应 → 延迟一轮的坏结果（任务 5，B 版三重锁）=================
REACTION_ESCALATE = -0.30     # 🎯 同一段对话里，它说完之后你变吼了
REACTION_REPEAT = -0.20       # 🎯 你把上一条几乎原样又发了一遍
REACTION_CAP = 3              # 锁②：一场会话最多学 3 次，防越聊越怕


def reaction_reward(prev_feat, prev_text_norm, feat, text, learned_count=0):
    """纯函数：只看**表面先后**，把后果记到上一轮那条刺激上。

    ⚠ 这是"猜的"，属于总纲里"表面近似"那一层：
       它不知道你生气了，只知道"这类消息之后气氛变紧了"。

    三重锁：
      ① 必须是**连续的同一段对话**（两次都是 fast，间隔 < 900 秒）
      ② 一场会话最多学 REACTION_CAP 次
      ③ 每次学都留痕（learn 那侧写 reaction_log，可回滚）

    返回 (reward 或 None, 理由)
    """
    if not prev_feat or not feat:
        return None, ""
    if learned_count >= REACTION_CAP:
        return None, ""

    # 锁①：连续对话（两轮都是 fast）才算"同一情境"
    if prev_feat.get("pace") != "fast" or feat.get("pace") != "fast":
        return None, ""

    # 升温：上一轮不是吼，这一轮是吼
    if prev_feat.get("vol") != "loud" and feat.get("vol") == "loud":
        return REACTION_ESCALATE, "同一段对话里，气氛变紧了"

    # 几乎原样重发（上一轮可能没接住）
    now_norm = _norm_text(text)
    if now_norm and prev_text_norm and now_norm == prev_text_norm:
        return REACTION_REPEAT, "几乎原样重发了一遍"

    return None, ""


def rollback_reaction(state, idx):
    """锁③：学错了能擦。

    ⚠ C2（11-07 修）：以前只还原**精确键**，粗键和指纹键学到的东西还留着
      → "擦掉了"其实没擦干净。现在按 learn() 实际动过的**所有键**逐键还原；
      学之前不存在的键，直接删掉。
    """
    log = state.get("reaction_log") or []
    if not (0 <= idx < len(log)):
        return {"ok": False, "why": "没有这条记录"}
    rec = log[idx]
    before = rec.get("before") or {}
    tbl = state.setdefault("valence", {})
    keys = rec.get("keys") or ([rec["key"]] if rec.get("key") else [])
    restored, deleted = [], []
    for k in keys:
        b = before.get(k)
        if b:                        # 学之前存在 → 还原字段
            e = tbl.get(k) or {}
            e["approach"] = b.get("approach", 0.0)
            e["avoid"] = b.get("avoid", 0.0)
            if "r" in b:
                e["r"] = b["r"]
            if "hits" in b:
                e["hits"] = b["hits"]
            tbl[k] = e
            restored.append(k)
        else:                        # 学之前不存在 → 删掉
            tbl.pop(k, None)
            deleted.append(k)
    rec["rolled_back"] = True
    return {"ok": True, "restored": restored, "deleted": deleted}


def keys_touched_by_learn(feat):
    """learn() 会动哪些键：精确键 + 粗键 + 每个指纹键。"""
    ks = [feat["exact"], feat["coarse"]]
    ks += [_fp_key(g) for g in (feat.get("fp") or [])]
    return ks


def log_reaction(state, keys, reward, before):
    """把这次"用户反应学习"记下来（可回滚）。keys = 实际动过的所有键。"""
    log = state.setdefault("reaction_log", [])
    log.append({"key": (keys[0] if keys else ""), "keys": list(keys),
                "reward": reward, "before": dict(before or {}),
                "at": datetime.now().isoformat(), "rolled_back": False})
    state["reaction_log"] = log[-20:]
    return log[-1]

# ================= seen：见过几次（施工单 3 / 第 2 条）=================
# 「亲历」应该按**见过**算，不是按**学过**算——
#   碰到过就是经历过，不需要有后果。
#   以前用 hits（学习次数）当精度，普通聊天几乎不学习 → 永远 0 → confirm 每句都触发。
def note_seen(state, feat):
    """这一轮见到了这个精确键：seen += 1。键不存在就建一条（值全 0）。"""
    tbl = state.setdefault("valence", {})
    key = feat["exact"]
    e = tbl.get(key)
    if not isinstance(e, dict):
        # ⚠ 建键时要用**出厂底色**（loud 天生偏负），不能写 0——
        #   写 0 等于"第一次见到就把出厂值抹掉了"。
        _init = (VALENCE_INITIAL.get(feat.get("vol"))
                 or VALENCE_INITIAL.get(key.split("|")[0]) or {})
        e = {"approach": float(_init.get("approach", 0.0)),
             "avoid": float(_init.get("avoid", 0.0)),
             "hits": 0,
             "r": 0.90 if key in VALENCE_INITIAL else 0.60,
             "last_touch": datetime.now().isoformat()}
        tbl[key] = e
    e["seen"] = int(e.get("seen", 0) or 0) + 1

    # 施工单 4 / 第 6 条（用户选 B）：新奇度按**字形**算，不按"形状"
    #   记下这句的二元组各见过几回；precision 用"见过多少比例"当亲历度。
    fp_seen = state.setdefault("fp_seen", {})
    for g in (feat.get("fp") or []):
        # 先 pop 再写回 → 挪到末尾，淘汰时才会先删"最久没用"的
        c = int(fp_seen.pop(g, 0) or 0)
        fp_seen[g] = c + 1
    if len(fp_seen) > 4000:                    # 防爆：只留最近用过的
        keep = dict(list(fp_seen.items())[-4000:])
        state["fp_seen"] = keep

    keys = state.setdefault("valence_keys", [])
    if key not in keys:
        keys.append(key)
    state["valence_keys"] = keys[-200:]
    return e["seen"]
