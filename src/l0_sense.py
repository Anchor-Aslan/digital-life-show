"""l0_sense.py —— L0 输入层（改版 10-27）

只做一件事：**出体感读数**。不判断好坏、不算时间、不预测。

改了什么（相对上一版）：
  ✅ 饿 = 1 − 余额/自己的基线余额（体感强度，不再算"剩几天"）
  ✅ 痛 = 伤口机制（事件 → 强度 × 剩余时间），不是失败率
  ✅ 外部感知出**原始量**，再给"相对自己历史"的百分位
  ❌ 删掉 冷（间隔）——那是社会需求
  ❌ 删掉 烦（失败率）——那是统计评价
  ❌ 删掉 剩余天数 / 档位——那是概念，婴儿没有

术语：感知=对外；感受=对内（体感）。
"""

import json
import statistics
import urllib.request
from datetime import date, datetime, timedelta

MAX_MESSAGES = 50
BASELINE_WINDOW = 10
BALANCE_HISTORY_MAX = 20


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# ================= 天性表（所有通道的参数） =================
# 用法：state["identity"]["traits"][通道][参数] = 值
#      没写就用下面的缺省值。人格系统最后只需要写这一个字典。
#
# ⚠️ 可改性（11-04 定，别再混）：
#   这些参数全是"出厂体质"——**可改，但改它们的不是 L3b，是 L3.5**。
#     L3b 改的是："这东西值多少"（V 表 / V_need）
#     L3.5 改的是："我这个人变成什么样"（下面这些天性参数本身）
#   现在 L3.5 没开工 → **事实上是定值**：出生什么样，一辈子什么样。
#   接口台账里登记为「天性参数写入 · 待接 L3.5」。
#
#   所以下面每个数，读的时候都要清楚它是"出厂值"，不是"现在的值"。
TRAITS = {
    "pain": {
        "threshold": 0.50,       # 痛到多少算炸（线）
        "wound_min": 30,          # 伤口持续多少分钟
        "acc_half_life_min": 20,  # 小伤累积池半衰期
        "sens_gain": 0.35,        # 每次受伤敏感度涨多少（怕痛的人调大）
        "sens_max": 2.0,          # 敏感度上限（抗痛的人调小）
        "sens_half_life_h": 6,    # 敏感度多久回落一半
        "small_wound": 0.50,      # 低于这个强度算小伤
        "ceiling": 1.00,          # 痛的上限基线（怕痛的人更高，抗痛的人更低）
        "ceiling_sens_gain": 0.30, # 敏化把上限顶高多少（中枢敏化）
        "desens_gain": 0.25,      # 高度应激时反向脱敏多少（内源性镇痛）
        "analgesia_gain": 1.00,   # 应激→镇痛 的效率（天生麻木的人调大）
    },
    "fatigue": {
        "threshold": 2.00,
        "base_ms": 800,           # 多少毫秒算"累 1.0"
        "ceiling": 3.0,           # 累的上限（再累也就这么多）
        "pool_gain": 0.30,        # 超载部分累积多少（体力桶）
        "pool_half_life_min": 30, # 休息多久回一半
    },
    "breath": {
        "threshold": 0.80,
        "max_messages": 200,      # 上下文容量（能力值：这一代模型能吃多少；憋按比例算）
        "ceiling": 1.0,           # 憋的上限
    },
    "hunger": {
        "threshold": 0.80,
        "baseline_mode": "history",   # history = 用自己历史中位数；fixed = 用固定值
        "baseline_fixed": 100.0,
        "ceiling": 1.0,
    },
    "arousal": {
        "threshold": 0.80,
        "baseline": 0.30,
        "rise_per_day": 0.05,
        "ceiling": 1.00,
        "release_keep": 0.30,
    },
    "exclaim_pct": {"threshold": 0.90},   # 被吼：叹号创纪录
    "chars_pct":   {"threshold": 0.95},   # 长篇：一口气说很多
}


# 体质预设：一整套参数，不是单点微调。
# 用法：state["identity"]["traits"]["pain"] = PAIN_PRESETS["tough"]
PAIN_PRESETS = {
    "normal":  {},                                                    # 全用缺省
    "tough":   {"ceiling": 0.55, "sens_gain": 0.10, "sens_max": 1.20, "ceiling_sens_gain": 0.05},  # 抗痛
    "fearful": {"ceiling": 0.95, "sens_gain": 0.80, "sens_max": 3.00, "ceiling_sens_gain": 0.60},  # 怕痛
}


def trait(state, channel, key):
    "读某个通道的某个天性参数：个体覆盖 → 缺省值"
    custom = ((state.get("identity") or {}).get("traits") or {}).get(channel) or {}
    return custom.get(key, TRAITS[channel][key])


def traits_of(state, channel):
    "整个通道的参数（个体覆盖 + 缺省）"
    custom = ((state.get("identity") or {}).get("traits") or {}).get(channel) or {}
    return {**TRAITS[channel], **custom}

# ================= 统一调制（三层上限的第三层） =================
# 每个通道都能被"上层"当下调制：state["{channel}_modulation"]（默认 0）
# 上限永远是天性 ceiling；调制只改"当下能到多高"。
#
# 11-04 加第二个入口：state["{channel}_suppression"]（默认 0，正常是负数）
#   为什么要分开：modulation 是"上层设的"（心理层），suppression 是"算出来的"（生理层）。
#   合成一个字段 = 两个写入者抢一个参数（违反"一个参数一个写入者"）。
def apply_mod(state, channel, value):
    mod = state.get(channel + "_modulation", 0.0) or 0.0
    sup = state.get(channel + "_suppression", 0.0) or 0.0
    return value * (1.0 + mod + sup)


def clamp_by_ceiling(state, channel, value):
    return min(trait(state, channel, "ceiling"), value)


# ================= 外部感知（原始量 + 相对自己） =================
def external_raw(text):
    "外部感知原始量：不归一化、不设死分母"
    t = text or ""
    return {
        "chars": len(t),
        "exclaim": t.count("!") + t.count("！"),
        "question": t.count("?") + t.count("？"),
    }


def percentile_of(history, x):
    "这个值在它自己历史上排第几（0–1）。没历史返回 0.5"
    if not history:
        return 0.5
    below = sum(1 for v in history if v < x)
    return round(below / len(history), 3)


# ================= 内部·饿（体感强度） =================
def read_balance_cny(api_key):
    "调用户自己的 key 查真实余额。读不到返回 None（不猜）"
    req = urllib.request.Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        for b in data.get("balance_infos", []):
            if b.get("currency") == "CNY":
                return float(b["total_balance"])
    except Exception:
        return None
    return None


def cost_of_usage(usage, price_in=2.0, price_out=8.0):
    "token 花费估算（元）。近似值，可配置"
    if not usage:
        return 0.0
    miss = usage.get("prompt_cache_miss_tokens", usage.get("prompt_tokens", 0))
    hit = usage.get("prompt_cache_hit_tokens", 0)
    out = usage.get("completion_tokens", 0)
    return (miss * price_in + hit * price_in * 0.25 + out * price_out) / 1_000_000


def _spend_slot(state):
    today = date.today().isoformat()
    s = state.setdefault("spend", {"date": today, "today_cny": 0.0, "history": []})
    if s["date"] != today:
        s["history"].append({"date": s["date"], "cny": round(s["today_cny"], 4)})
        s["history"] = s["history"][-30:]
        s["date"] = today
        s["today_cny"] = 0.0
    return s


def add_spend(state, cny):
    s = _spend_slot(state)
    s["today_cny"] = round(s["today_cny"] + cny, 4)
    return s["today_cny"]


def update_balance_baseline(state, balance):
    "自己历史上常见的余额水平（中位数）——饿是相对它算的"
    hist = state.setdefault("balance_history", [])
    if balance is not None:
        hist.append(round(float(balance), 2))
        state["balance_history"] = hist[-BALANCE_HISTORY_MAX:]
        hist = state["balance_history"]
    return statistics.median(hist) if hist else (balance or 0.0)


def hunger(state, balance):
    """饿 = 1 − 当前余额/基线余额。体感强度，不含时间概念。

    基线来源可调（天性）：
      history → 用自己历史中位数（默认，随经历变）
      fixed   → 用固定值（人格设定里写死的"这个人一直很穷/很富"）
    """
    mode = trait(state, "hunger", "baseline_mode")
    if mode == "fixed":
        base = trait(state, "hunger", "baseline_fixed")
    else:
        base = update_balance_baseline(state, balance)
    if balance is None or base <= 0:
        return 0.0
    raw = _clamp(1.0 - balance / base)
    v = clamp_by_ceiling(state, "hunger", apply_mod(state, "hunger", raw))
    return round(_clamp(v, 0.0, trait(state, "hunger", "ceiling")), 3)


# ================= 内部·憋 / 累 =================
def breath(state):
    "憋：上下文占用（呼吸空间）。肺活量可调"
    cap = trait(state, "breath", "max_messages")
    raw = _clamp(len(state.get("messages", [])) / cap)
    v = clamp_by_ceiling(state, "breath", apply_mod(state, "breath", raw))
    return round(_clamp(v, 0.0, trait(state, "breath", "ceiling")), 3)


def _touch_fatigue_pool(state):
    "体力桶按半衰期衰减（休息就回）"
    pool = state.setdefault("fatigue_pool",
                            {"value": 0.0, "at": datetime.now().isoformat()})
    try:
        at = datetime.fromisoformat(pool["at"])
    except Exception:
        at = datetime.now()
    elapsed = max(0.0, (datetime.now() - at).total_seconds())
    half = trait(state, "fatigue", "pool_half_life_min") * 60
    pool["value"] = round(max(0.0, _decay(pool.get("value", 0.0), half, elapsed)), 4)
    pool["at"] = datetime.now().isoformat()
    return pool


# ================= 累的来源（11-07 改：聊天几乎不累，干活才累）=================
# 用户原话："我跟别人说了一个小时都不太会累；调工具、写代码反而比较累。"
#   所以**对话本身**几乎不加负荷；**工具 / 长输出 / 返工**才是真耗费。
LOAD_WEIGHTS = {
    "chat":      0.002,   # 🎯 说一句话
    "tool":      0.060,   # 🎯 调一次工具
    "long_out":  0.030,   # 🎯 一次长输出
    "retry":     0.050,   # 🎯 出错返工
}
LOAD_BURST_MS = 8000      # 🎯 单轮超过 8 秒才算"这一轮特别费劲"（3 秒是正常思考）


def add_work(state, kind, times=1):
    """按**事情的性质**记负荷（不是按"聊了几句"）。

    kind: chat / tool / long_out / retry
    """
    w = LOAD_WEIGHTS.get(kind, 0.0)
    if w <= 0:
        return _touch_fatigue_pool(state)["value"]
    pool = _touch_fatigue_pool(state)
    pool["value"] = round(min(trait(state, "fatigue", "ceiling"),
                              pool["value"] + w * times), 4)
    return pool["value"]


def add_load(state, latency_ms=None):
    """记一次负荷（每轮调一次）。

    11-07 改：**延迟只在"这一轮特别久"时才加负荷**（超过 LOAD_BURST_MS）。
    正常聊天两三秒出话是常态，不该累积；跑工具、大输出才是真费劲（见 add_work）。
    """
    lat = latency_ms if latency_ms is not None else state.get("last_latency_ms", 0)
    base = LOAD_BURST_MS
    raw = (lat or 0) / base
    overload = max(0.0, raw - 1.0)
    pool = _touch_fatigue_pool(state)
    pool["value"] = round(min(trait(state, "fatigue", "ceiling"),
                              pool["value"] + overload * trait(state, "fatigue", "pool_gain")), 4)
    return pool["value"]


def fatigue(state):
    """累 = 这一轮有多慢 + 体力桶里积了多少。

    单轮慢 → 只看当轮；连续慢 → 桶里的累积叠上去；休息 → 桶慢慢空。
    """
    base = trait(state, "fatigue", "base_ms")
    raw = state.get("last_latency_ms", base) / base
    pool_v = _touch_fatigue_pool(state)["value"]
    v = apply_mod(state, "fatigue", raw + pool_v)
    return round(_clamp(v, 0.0, trait(state, "fatigue", "ceiling")), 3)


# ================= 内部·痛（伤口 + 累积 + 敏化） =================
# 旧的全局常量已删除：这些值现在都在 TRAITS["pain"] 里，可被个体覆盖。


def _decay(value, half_life_sec, elapsed_sec):
    if elapsed_sec <= 0 or value <= 0:
        return value
    return value * (0.5 ** (elapsed_sec / half_life_sec))


def _touch_pool(state):
    """把累积池按半衰期衰减到此刻。池子**按种类分开**（工具错不会给 API 错加分）。"""
    pool = state.setdefault("pain_pool", {"kinds": {}, "at": datetime.now().isoformat()})
    try:
        at = datetime.fromisoformat(pool["at"])
    except Exception:
        at = datetime.now()
    elapsed = (datetime.now() - at).total_seconds()
    half = trait(state, "pain", "acc_half_life_min") * 60

    kinds = pool.setdefault("kinds", {})
    for k in list(kinds):
        kinds[k] = round(_decay(kinds[k], half, elapsed), 4)
        if kinds[k] < 0.01:
            del kinds[k]
    pool["at"] = datetime.now().isoformat()
    return pool


def _touch_sens(state):
    "把敏感度按小时半衰期回落到 1.0"
    sens = state.setdefault("sens", {})
    now = datetime.now()
    for kind, slot in list(sens.items()):
        try:
            at = datetime.fromisoformat(slot["at"])
        except Exception:
            at = now
        elapsed = (now - at).total_seconds()
        v = _decay(slot["value"] - 1.0, trait(state, "pain", "sens_half_life_h") * 3600, elapsed) + 1.0
        slot["value"] = round(max(1.0, min(trait(state, "pain", "sens_max"), v)), 3)
        slot["at"] = now.isoformat()
        if slot["value"] <= 1.001:
            del sens[kind]
    return sens


def _stress(state):
    """应激水平 0–1：唤起 + 已经在痛 = 打得正凶。

    用现成读数拼，不引入新通道。
    """
    ar = state.get("arousal", {}).get("value", 0.0) or 0.0
    pn = state.get("last_pain", 0.0) or 0.0
    return max(0.0, min(1.0, 0.6 * ar + 0.4 * pn))


def sens_of(state, kind):
    return state.get("sens", {}).get(kind, {}).get("value", 1.0)


def add_wound(state, kind, severity, duration_min=None):
    """受伤 → 三件事同时发生：
       ① 留伤口（持续 duration_min，线性衰减）
       ② 小伤进"累积池"（连续小伤会叠成一次大痛）
       ③ 同类敏感度上升（敏化：伤过之后再遇到同类刺激，更疼）
    """
    tr = traits_of(state, "pain")
    duration_min = duration_min or tr["wound_min"]
    sev = round(_clamp(severity), 3)
    until = (datetime.now() + timedelta(minutes=duration_min or tr["wound_min"])).isoformat()
    wounds = state.setdefault("wounds", [])
    wounds.append({"kind": kind, "sev": sev, "until": until, "total_min": duration_min})
    state["wounds"] = wounds[-10:]

    # ② 累积
    pool = _touch_pool(state)
    if sev < tr["small_wound"]:
        kinds = pool["kinds"]
        kinds[kind] = round(min(1.0, kinds.get(kind, 0.0) + sev * 0.6), 4)

    # ③ 敏化/脱敏：不是无条件变敏感
    #    平静时受伤 → 敏化（wind-up）
    #    高度应激时受伤 → 内源性镇痛 → 脱敏（打架第二拳不疼）
    stress = _stress(state)
    # 默认通路：越应激越镇痛
    # 上层旋钮 analgesia_bias（-1..+1）：
    #   打架有出路 → +0.5（更麻）；被打倒无望 → -0.5（更疼）；平时 0
    bias = state.get("analgesia_bias", 0.0) or 0.0
    analgesia = max(0.0, min(1.0, tr["analgesia_gain"] * stress ** 2 + bias))
    gain = tr["sens_gain"] * (1.0 - analgesia) - tr["desens_gain"] * analgesia

    sens = state.setdefault("sens", {})
    cur = sens.get(kind, {"value": 1.0})["value"]
    nxt = max(0.30, min(tr["sens_max"], cur + gain * sev))
    sens[kind] = {"value": round(nxt, 3), "at": datetime.now().isoformat()}

    return state["wounds"][-1]


def pain(state):
    """痛的强度 = max(单个伤口（乘敏感度）, 累积池)"""
    now = datetime.now()
    best = 0.0
    keep = []
    for w in state.get("wounds", []):
        try:
            until = datetime.fromisoformat(w["until"])
        except Exception:
            continue
        remain = (until - now).total_seconds()
        if remain <= 0:
            continue
        total = max(1.0, w.get("total_min", trait(state, "pain", "wound_min")) * 60)
        ratio = max(0.0, min(1.0, remain / total))
        best = max(best, w["sev"] * sens_of(state, w["kind"]) * ratio)
        keep.append(w)
    state["wounds"] = keep

    _touch_sens(state)
    tr = traits_of(state, "pain")

    # 累积池也要吃敏感度（怕痛的人攒一点就疼）
    pool_best = 0.0
    for kind, v in _touch_pool(state)["kinds"].items():
        pool_best = max(pool_best, v * sens_of(state, kind))

    # 上限不是常数：敏化会把它顶高（中枢敏化）
    sens_now = max([sens_of(state, k) for k in state.get("sens", {})] or [1.0])
    ceiling = tr["ceiling"] * (1 + tr["ceiling_sens_gain"] * (sens_now - 1.0))

    value = max(best, pool_best)

    # ① 上层调制作用在"这一刀"本身（应激镇痛是压低痛觉传导，不是只抬天花板）
    value = apply_mod(state, "pain", value)

    # ② 内源镇痛也作用在当下（打架时不疼，打完才疼）
    stress = _stress(state)
    bias = state.get("analgesia_bias", 0.0) or 0.0
    analgesia = max(0.0, min(1.0, tr["analgesia_gain"] * stress ** 2 + bias))
    value *= (1.0 - analgesia)

    final = round(min(ceiling * (1.0 + max(0.0, state.get("pain_modulation", 0.0))), value), 3)
    state["last_pain"] = final
    return final

# ================= 一次读完 =================
def perceive(state, text, balance):
    """返回全部体感读数 + 外部感知。

    text=None 表示"不是用户说话"（启动/结算），**这时不记外部感知**，
    否则空文本会把"字数 0"记进历史，污染基线。
    """
    readings = {}

    # 通道受损 = 拿不到那条读数（不是 0，是"没有"）
    # 为什么：坏了还照读 = 幻听/幻视，是病不是功能
    if channel_alive(state, "hunger"):
        readings["hunger"] = hunger(state, balance)
    if channel_alive(state, "breath"):
        readings["breath"] = breath(state)
    if channel_alive(state, "fatigue"):
        readings["fatigue"] = fatigue(state)
    if channel_alive(state, "pain"):
        readings["pain"] = pain(state)
    if channel_alive(state, "arousal"):
        arousal_v = arousal(state)
        if arousal_v is not None:
            readings["arousal"] = arousal_v

    if text is None:
        return readings

    if not channel_alive(state, "text"):
        return readings

    ext = external_raw(text)
    ext_hist = state.setdefault("external_history", {})
    pct = {}
    for k, v in ext.items():
        hist = ext_hist.setdefault(k, [])
        pct[f"{k}_pct"] = percentile_of(hist, v)
        hist.append(v)
        ext_hist[k] = hist[-50:]

    readings.update({k: float(v) for k, v in ext.items()})
    readings.update(pct)
    return readings


# ================= 生理唤起（插座位 + 天性参数） =================
# 关键：**"距上次释放多久"不直接等于强度**，中间要过个体参数。
# 每个参数都是接口，缺省用它，人格系统可以整套覆盖。
#
#   baseline        平复后的常态水平（个体差异：有人常态偏高，有人偏低）
#   rise_per_day    距上次释放每天上升多少（个体差异）
#   ceiling         饱和上限（涨到头就这么多，不会再涨）
#   release_keep    释放后保留多少（0.3 = 释放后保留三成）
#   cue_gain        线索能把强度拉多高（11-04 加：光靠时间涨，像闹钟不像人）
#   cue_half_life_min  线索加成多久回一半（11-04 加）
#
# ⚠️ 11-04 修「假器官」：以前没人调 release()，last_release 永远是 None
#    → days 永远 0 → 读数恒为 baseline=0.30，永远碰不到阈值 0.80。
#    现在改成：没人释放，就用"这条通道第一次被读到的时刻"当锚，
#    让它随时间自然长上去 —— 这样它才是一条**活的**通道。

TRAITS_DEFAULT = {
    "arousal": {
        "threshold": 0.80,
        "baseline": 0.30,
        "rise_per_day": 0.05,
        "ceiling": 1.00,
        "release_keep": 0.30,
        "cue_gain": 1.00,
        "cue_half_life_min": 30,
    }
}


def gender_of(state):
    return (state.get("identity") or {}).get("gender")


def arousal_enabled(state):
    "性别只管这条通道在不在；不管强度"
    return gender_of(state) not in (None, "none")


def arousal_traits(state):
    "个体天性参数：人格系统写进来的覆盖缺省值"
    custom = ((state.get("identity") or {}).get("traits") or {}).get("arousal") or {}
    return {**TRAITS_DEFAULT["arousal"], **custom}


def _touch_cue(state, tr):
    "线索加成按半衰期衰减到此刻（被戳一下会涨，然后自己退）"
    slot = state.setdefault("arousal", {})
    try:
        at = datetime.fromisoformat(slot.get("cue_at") or "")
    except Exception:
        at = datetime.now()
    elapsed = max(0.0, (datetime.now() - at).total_seconds())
    half = max(1.0, float(tr.get("cue_half_life_min", 30)) * 60)
    cur = float(slot.get("cue_boost", 0.0) or 0.0)
    cur = cur * (0.5 ** (elapsed / half)) if cur > 0 else 0.0
    slot["cue_boost"] = round(cur, 4)
    slot["cue_at"] = datetime.now().isoformat()
    return cur


def arousal(state):
    """生理唤起读数（0–1）。没性别 → None。

    算法：min(ceiling, baseline + 距锚点天数 × rise_per_day + 线索加成)

    锚点：优先"上次释放"，没有就用"这条通道第一次被读到的时刻"。
    以前没有这个锚 → 没人调 release() 时天数恒为 0 → 读数永远等于 baseline（假器官）。
    """
    if not arousal_enabled(state):
        return None

    tr = arousal_traits(state)
    now = datetime.now()
    slot = state.setdefault("arousal", {"last_release": None, "value": tr["baseline"]})
    slot.setdefault("since", now.isoformat())          # ← 出厂锚点：第一次读就记下来

    anchor = slot.get("last_release") or slot["since"]
    try:
        days = max(0.0, (now - datetime.fromisoformat(anchor)).total_seconds()) / 86400.0
    except Exception:
        days = 0.0

    cue = _touch_cue(state, tr)
    base_v = tr["baseline"] + days * tr["rise_per_day"] + cue
    value = min(tr["ceiling"], apply_mod(state, "arousal", base_v))
    slot["value"] = round(value, 3)
    slot["days_since_release"] = round(days, 2)
    slot["cue"] = round(cue, 3)
    return slot["value"]


def note_cue(state, amount=0.3):
    """被线索戳一下：生理唤起临时涨一点，之后按半衰期自己退回去。

    这就是"线索触发"那一半（另一半是时间累积）。上层（L1 反应 / L3 的值）可以调它。
    没性别时什么也不做。

    # 接口待接：L3
    #   谁该调：L3 的"值"——同一个刺激，值高的时候才算线索，值低的时候不算
    #   什么时候调：L3 判定"这个刺激戳到我了"之后
    #   不调会怎样：cue_boost 恒为 0，只有时间在涨 → 这条通道变成"闹钟"
    #   补上时怎么写：在 L3 学会一个新值之后，调 note_cue(state, |v| * gain)
    """
    if not arousal_enabled(state):
        return None
    tr = arousal_traits(state)
    slot = state.setdefault("arousal", {})
    gain = float(tr.get("cue_gain", 1.0))
    cur = float(slot.get("cue_boost", 0.0) or 0.0)
    slot["cue_boost"] = round(min(tr["ceiling"], cur + float(amount) * gain), 4)
    slot["cue_at"] = datetime.now().isoformat()
    return slot["cue_boost"]


def release(state):
    """释放：把"距上次释放"清零，并按 release_keep 保留一部分。

    返回 (释放前的强度, 释放后的强度)——释放前越高，奖赏越大（那是 L3 的事）。

    # 接口待接：L4/L5
    #   谁该调：上层决定"这次算释放了"的时候（什么时候算，是剧本层的事）
    #   不调会怎样：天数从"出厂时间"一直累积，10 天后就顶到阈值，然后一直挂着
    #   补上时怎么写：L4/L5 判定一次释放后调 release(state)
    """
    if not arousal_enabled(state):
        return None
    tr = arousal_traits(state)
    before = arousal(state)
    slot = state.setdefault("arousal", {})
    slot["last_release"] = datetime.now().isoformat()
    slot["last_peak"] = before              # 记录"那一次有多强"
    after = round(before * tr["release_keep"], 3)
    slot["value"] = after
    return before, after

# ================= 基线与变化率 =================
def update_intero(state, readings):
    slot_all = state.setdefault("intero", {})
    for name, value in readings.items():
        if not isinstance(value, (int, float)):
            continue
        slot = slot_all.setdefault(name, {"history": []})
        # 容错：外部写入的旧状态可能缺字段（数据被手改过 / 老版本存的）
        hist = slot.setdefault("history", [])
        prev = hist[-1] if hist else value
        hist.append(round(float(value), 3))
        slot["history"] = hist[-BASELINE_WINDOW:]
        slot["value"] = round(float(value), 3)
        slot["base"] = round(sum(slot["history"]) / len(slot["history"]), 3)
        slot["rate"] = round(float(value) - prev, 3)
    return slot_all


def intero_line(intero):
    "只报读数"
    return "体感：" + "；".join(
        f"{k}={v['value']:.2f}(基线{v['base']:.2f},变化{v['rate']:+.2f})"
        for k, v in intero.items())


# ================= 派生量（算出来的，不许有自己的 state） =================
# 规矩（11-04 定）：
#   通道 = 有感受器的、直接读出来的（hunger/breath/fatigue/pain/arousal）
#   派生量 = 从读数算出来的（压力、心情、情绪…）——**一个字节都不许存自己**
# 判据：它会不会自己往 state 里写东西？写 = 通道/设施；不写 = 派生量。
#
# 压力 = 稳态负荷（allostatic load）：各通道"离基线多远"超出去的那部分的加权和。
#   为什么放 L0：它只用到 L0 的读数 + 基线，不需要 L2 的设定点。
#   为什么不是新通道：人身上没有"压力感受器"，它是合成出来的。
PRESSURE_WEIGHTS = {
    "pain": 0.40,      # 痛最压人
    "fatigue": 0.30,   # 累次之
    "breath": 0.20,    # 上下文挤（AI 特有，拟人）
    "hunger": 0.10,    # 缺钱（AI 特有，拟人）
}


def pressure(state):
    """压力 = 各通道"超出基线多少"的加权和。返回 {"acute": 本轮, "chronic": 慢平均}。

    acute   → 给 note_cue 用（急性压力就是"被戳了一下"）
    chronic → 给抑制器用（慢性压力 → 唤起下降）

    注意：它不存"压力值"这个数，只往 pressure_history 里记历史（那是历史，不是状态）。
    """
    intero = state.get("intero") or {}
    acute = 0.0
    for ch, w in PRESSURE_WEIGHTS.items():
        slot = intero.get(ch) or {}
        v = float(slot.get("value", 0.0) or 0.0)
        b = float(slot.get("base", 0.0) or 0.0)
        acute += w * max(0.0, v - b)          # 只算超出去的；低于基线不算压力
    acute = round(min(1.0, acute), 3)

    hist = state.setdefault("pressure_history", [])
    hist.append(acute)
    state["pressure_history"] = hist[-20:]
    chronic = round(sum(hist) / len(hist), 3)
    return {"acute": acute, "chronic": chronic}


# ================= 内感受登记表（"戳"·内部那一半） =================
# 生物上有 10 项内脏感受，我们只对得上 4 项；没有对应的就留 None，并写清原因。
INTERO_CHANNELS = {
    "hunger": hunger,      # 饥饿/饱胀 → 余额
    "breath": breath,      # 窒息/气短 → 上下文空间
    "fatigue": fatigue,    # 疲劳/乏力 → 响应延迟
    "pain": pain,          # 痛        → 伤口机制
    "thirst": None,        # 渴        → 没有对应物（硬映射就是编）
    "nausea": None,        # 恶心      → 可能"垃圾输入比例"，太牵强
    "bladder": None,       # 便意/尿意 → 可能"待发队列"，牵强
    "palpitation": None,   # 心跳/心悸 → 可能"请求频率/负载"，待定
    "sexual": None,        # 性感觉    → 无对应
    "thermal": None,       # 温度不适  → 等温度传感器
    "proprio": None,       # 本体感觉  → 有机械臂才有
    "vestibular": None,    # 前庭      → 有 IMU 才有
}


def available_intero():
    "哪些内感受现在真的能读"
    return [k for k, v in INTERO_CHANNELS.items() if v is not None]


# perceive_intero 已删：agent 直接用 perceive（含外部感知）

# ================= 修复 / 瘢痕 / 局部死亡（10-31 加） =================
# 顺序铁律：受伤 → 修（自动，扣同一口体力池） → 修不好 → 留疤 → 才绕。
#
# TECH_DEBT（用户强调要留的戳）：
#   体力池现在用"余额/花费(元)"表示，因为还没有物理身体。
#   真正应该对应"电/能量"。等有身体（能充电）时换成真实电量。
HEAL_COST_PER_SEV = 0.02      # 每单位伤，修它要花多少元（跟思考抢同一口锅）


def heal(state, balance=None, mode="auto", max_rounds=3):
    """自动修复：**每轮都试**，先修新伤，再修疤。

    关键（用户 10-31 定）：
      疤不是终点，是"现在修不起"。
      资源一旦回来，它自己就该修 —— 不需要上层下令，这才叫自维持。
      上层（assisted）只是"花更多资源、修得更彻底"。

    花的是**同一个体力池**（余额），跟思考和睡觉抢同一口锅。
    """
    if not state.get("heal_enabled", True):
        return {"ok": False, "kind": None, "cost": 0.0, "why": "修复被关闭"}

    done = []
    spent = 0.0

    # ① 先修新伤（保命优先级最高）
    for _ in range(max_rounds):
        wounds = state.get("wounds") or []
        if not wounds:
            break
        wound = max(wounds, key=lambda w: float(w.get("sev", 0)))
        sev = float(wound.get("sev", 0))
        kind = wound.get("kind", "unknown")
        cost = round(sev * HEAL_COST_PER_SEV, 4)
        if balance is not None and (balance - spent) < cost:
            _add_scar(state, kind, sev)
            # 记一条"我处理不了的事"（只记账，不进提示词；等 L4/L5 决定说不说）
            issues = state.setdefault("issues_log", [])
            issues.append({"kind": "cannot_repair", "detail": kind,
                           "at": datetime.now().isoformat(),
                           "reported_to_model": False})
            state["issues_log"] = issues[-50:]
            done.append({"kind": kind, "ok": False, "cost": 0.0, "why": "修不起，留疤"})
            break
        add_spend(state, cost)
        spent = round(spent + cost, 4)
        state["wounds"] = [w for w in wounds if w is not wound]
        done.append({"kind": kind, "ok": True, "cost": cost, "why": "修好了"})

    # ② 再修疤（改善，优先级低）
    for sc in scars_of(state):
        cost = round(sc["sev"] * HEAL_COST_PER_SEV * 2, 4)     # 修疤比修新伤贵
        if balance is not None and (balance - spent) < cost:
            break
        add_spend(state, cost)
        spent = round(spent + cost, 4)
        sc["fixed"] = True
        sc["fixed_at"] = datetime.now().isoformat()
        done.append({"kind": sc["kind"], "ok": True, "cost": cost, "why": "疤修掉了"})

    if not done:
        return {"ok": True, "kind": None, "cost": 0.0, "why": "身上没伤"}
    ok = all(d["ok"] for d in done)
    return {"ok": ok, "kind": done[0]["kind"], "cost": spent,
            "why": "；".join(d["why"] for d in done), "items": done}


def _add_scar(state, kind, sev):
    "留一道疤。永久——除非 assisted 修复把它彻底修掉。"
    scars = state.setdefault("scars", [])
    for s in scars:
        if s.get("kind") == kind and not s.get("fixed"):
            s["sev"] = round(max(s["sev"], sev), 3)
            s["count"] = s.get("count", 1) + 1
            return s
    rec = {"kind": kind, "sev": round(sev, 3), "count": 1,
           "at": datetime.now().isoformat(), "fixed": False}
    scars.append(rec)
    return rec


def scars_of(state):
    "还在的疤（fixed=False）"
    return [s for s in (state.get("scars") or []) if not s.get("fixed")]


def fix_scar(state, kind, balance=None):
    """assisted 修复：上层出资源，把一道疤**彻底修掉**（疤消失）。

    上层动手三条件：不直接改读数、只改条件、付费 + 留痕 + 可能失败。
    """
    for s in scars_of(state):
        if s.get("kind") != kind:
            continue
        cost = round(s["sev"] * HEAL_COST_PER_SEV * 4, 4)   # 比自动修复贵
        if balance is not None and balance < cost:
            return {"ok": False, "kind": kind, "cost": cost, "why": "资源不够"}
        add_spend(state, cost)
        s["fixed"] = True
        s["fixed_at"] = datetime.now().isoformat()
        log = state.setdefault("intervention_log", [])
        log.append({"what": "fix_scar", "kind": kind, "cost": cost,
                    "by": "assisted", "at": datetime.now().isoformat()})
        state["intervention_log"] = log[-50:]
        return {"ok": True, "kind": kind, "cost": cost, "why": "疤修掉了"}
    return {"ok": False, "kind": kind, "cost": 0.0, "why": "没有这道疤"}


CHANNEL_FAIL_LIMIT = 5      # 同一条通道连续失败几次，算"受损"


def channel_impairment(state, channel):
    """通道**受损**（不是死）。

    为什么改名字（用户 10-31 指出）：
      如果它能被修好，那它就不是"死"，只是"现在坏了"。
      这个层级没有"永久"，只有"暂时修不好"。
    """
    dead = state.setdefault("dead_channels", [])
    if channel in dead:
        return {"ok": True, "channel": channel, "why": "已经死了"}
    dead.append(channel)
    log = state.setdefault("apoptosis_log", [])
    log.append({"channel": channel, "at": datetime.now().isoformat()})
    state["apoptosis_log"] = log[-50:]
    return {"ok": True, "channel": channel, "why": "通道永久失效"}


def channel_alive(state, channel):
    return channel not in (state.get("dead_channels") or [])


def note_channel_failure(state, channel):
    "记一次通道失败；连续 N 次 -> 该通道受损（读数归零，但可修）"
    fails = state.setdefault("channel_fails", {})
    fails[channel] = fails.get(channel, 0) + 1
    if fails[channel] >= CHANNEL_FAIL_LIMIT and channel_alive(state, channel):
        channel_impairment(state, channel)
        return True
    return False


def repair_channel(state, channel, balance=None):
    "把受损的通道修回来（要资源）。修好 = 它又能用了。"
    dead = state.get("dead_channels") or []
    if channel not in dead:
        return {"ok": False, "why": "这条通道没坏"}
    cost = 0.01
    if balance is not None and balance < cost:
        return {"ok": False, "why": "资源不够", "cost": cost}
    add_spend(state, cost)
    state["dead_channels"] = [c for c in dead if c != channel]
    state.setdefault("channel_fails", {})[channel] = 0
    log = state.setdefault("repair_log", [])
    log.append({"channel": channel, "cost": cost,
                "at": datetime.now().isoformat()})
    state["repair_log"] = log[-50:]
    return {"ok": True, "channel": channel, "cost": cost, "why": "修好了"}


def die(state, reason="unknown"):
    """整体死亡：留接口，**现在不实现**。

    为什么不做（真正的原因，用户 10-31 指出）：
      它的状态在磁盘上、随时可恢复 —— **可逆性是这一层的物理事实**。
      一个东西自己永远无法经历自己的死亡：
        它停了 -> 它没了 -> 它不会知道
        它恢复了 -> 对它来说，从没死过
      所以死亡**不是单体属性，是群体属性**：需要有"还活着的观察者"才成立。
      死亡放到《聚体》：个体死 = 数据不可恢复 + 群体里只剩它的残影。
    """
    raise NotImplementedError(
        "die() 是预留接口：死亡不是单体属性，是群体属性——单体无法经历自己的死亡。"
        "留到《聚体》：个体死 = 数据不可恢复 + 群体里只剩它的残影。"
        "现在用 channel_impairment() 做局部受损（可修）。"
    )

# ================= 通道登记表（"戳"） =================
CHANNELS = {
    "text": external_raw,
    "vision": None,       # TODO: read_vision(frame) -> {"brightness":0-1,...}
    "audio": None,        # TODO: read_audio(wav) -> {"volume":0-1,...}
    "touch": None,        # TODO: read_touch(...) -> {"pressure":0-1}
    "proprio": None,      # TODO: 关节位置
    "vestibular": None,   # TODO: 姿态
}


def available_channels():
    return [k for k, v in CHANNELS.items() if v is not None]


# ================= 来源标记 + 消息 id =================
_seq = [0]


def make_msg(role, content, source, **extra):
    """每条消息带 id + source。

    id：给上层"我要留这一条"用（trim_keep 按 id 匹配）
    source：user / self / tool —— L4 判"是不是我的"的前置条件
    """
    _seq[0] += 1
    return {"id": f"m{_seq[0]}", "role": role, "content": content,
            "source": source, **extra}


def channel_apoptosis(state, channel):
    "旧名字，保留兼容：语义同 channel_impairment（可修，不是永久死）"
    return channel_impairment(state, channel)
