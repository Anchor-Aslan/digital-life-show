"""l2_ownership.py —— L2b 操作性归属：学会

判据（哲学层 Q4）：
  把状态当"自己的"来用 —— 受影响、为它改策略、维护它。
  **不需要"我"这个概念（那是 L4）。**

这一层做的第一件事：**学会**。
  同一类伤反复出现 → 它不是"一次意外"，是"我这副身体的老毛病"
  → 从此提前防备（不用等疼起来）

注意：这里学的是"策略"，不是"知识"。
  知识要说出来（L4），策略只要改行为。
"""

import importlib.util
import os
from datetime import datetime

_spec = importlib.util.spec_from_file_location(
    "l0_sense", os.path.join(os.path.dirname(__file__), "l0_sense.py"))
l0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l0)

# 学成的门槛：同类伤出现几次算"老毛病"
LEARN_THRESHOLD = 3

# 学成之后提前收紧多少（预防性保守）
PREEMPT_TEMP = 0.15      # 温度降 0.15
PREEMPT_TOKENS = 150     # 输出上限减 150


def scan(state):
    """数一数 trace 里，每类伤出现过几次（这就是"经历"）"""
    counts = {}
    for rec in state.get("trace", []):
        for w in rec.get("wounds", []) or []:
            counts[w] = counts.get(w, 0) + 1
    return counts


def learn(state):
    """从经历里学成"老毛病"。

    返回 (learned, newly)：
      learned  现在所有的老毛病
      newly    这次新学成的（第一次学成时会被打印出来，像"记住了"）
    """
    learned = state.setdefault("learned", {})
    counts = scan(state)
    newly = []

    for kind, n in counts.items():
        rec = learned.get(kind)
        if rec is None and n >= LEARN_THRESHOLD:
            learned[kind] = {
                "count": n,
                "since": datetime.now().isoformat(),
                "policy": "提前收紧",
            }
            newly.append(kind)
        elif rec is not None:
            rec["count"] = n

    return learned, newly


def seasoned(state, kind):
    "这类伤是不是已经成了老毛病"
    return kind in (state.get("learned") or {})


def apply_learned(state, params):
    """学成的老毛病 → 提前收紧（不用等疼起来）。

    只在"没有更强信号"时生效；有信号时由反射接管。
    """
    learned = state.get("learned") or {}
    if not learned:
        return params

    p = dict(params)
    # 老毛病越多，越保守（但封顶，别把自己憋死）
    n = min(len(learned), 3)
    p["temperature"] = round(max(0.1, p.get("temperature", 0.7) - PREEMPT_TEMP * n / 3), 3)
    p["max_tokens"] = max(200, p.get("max_tokens", 800) - int(PREEMPT_TOKENS * n / 3))
    p["preemptive"] = list(learned)
    return p


def learned_line(state):
    "给人看的一行"
    learned = state.get("learned") or {}
    if not learned:
        return "还没学成老毛病"
    parts = [f"{k}（{v['count']}次）" for k, v in learned.items()]
    return "老毛病：" + "、".join(parts)

# ================= 维护自己（L2b 的第二个证据） =================
# 用户定的原则：
#   维护动作是身体自带的，**不可关闭**（像心跳）；
#   上层只能调强度（budget），可以单次否决但要留痕；
#   彻底放弃自己 = 自杀级，属于更上层（L5），这一层不做。

import io
import json
import shutil

MAINT_KEYS = ("identity", "learned", "wounds", "sens", "arousal", "trace", "intero")


def budget(state):
    "维护预算（上层可调，0..1）"
    return float(state.get("maintenance_budget", 0.10))


def maintain(state, state_file, backup_file):
    """自动维护：原子写 + 备份。**不可关闭**——budget 只影响备份，不影响写盘。"""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    tmp = state_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, state_file)

    b = budget(state)
    made = []

    # 文件坏过 -> 多留一份 + 存完验证（这就是"绕开"：走过留疤的路，多带一份保险）
    if should_extra_backup(state):
        try:
            if os.path.exists(backup_file):
                shutil.copyfile(backup_file, backup_file + ".old")
            json.load(io.open(state_file, encoding="utf-8-sig"))   # 验证能读回来
            made.append("extra_backup+verified")
        except Exception:
            made.append("extra_backup_failed")

    if b >= 0.05:
        try:
            shutil.copyfile(state_file, backup_file)
            made.append("backup")
        except Exception:
            pass
    if b >= 0.20:
        try:
            shutil.copyfile(state_file, backup_file + ".old")
            made.append("backup.old")
        except Exception:
            pass

    state["maintenance"] = {"last": datetime.now().isoformat(),
                            "budget": b, "copies": made}
    return made


def continuity(state):
    """它还是不是它：关键字段还在吗。

    归属的前提是"同一个我"——重启后老毛病、伤口、经历都还得在。
    """
    missing = [k for k in MAINT_KEYS if k not in state]
    return {"ok": not missing, "missing": missing,
            "learned": list((state.get("learned") or {}).keys())}


def veto(state, reason):
    """单次否决维护（留痕，最多 20 条）。"""
    log = state.setdefault("maintenance_veto", [])
    log.append({"at": datetime.now().isoformat(), "reason": reason})
    state["maintenance_veto"] = log[-20:]
    return len(state["maintenance_veto"])

# ================= 边界（L2b 的第三个证据：判谁） =================
# 判据：归属的对象是**整个 agent**，不是某个函数。
# 但"伤"要分清是谁的：
#   self    = 它这副身体（文件坏了、状态坏了、它自己用错工具）
#   world   = 外面的世界（API 挂了、钱没了、对方骂它）
#   creator = 造它的人（我代码写错了）—— **这个不算它的伤**
#
# 为什么不算：代码写错是"造物者的错"，不是"它的身体"。
# 把它算进它的伤，等于让它替我背锅。

SCOPE = {
    "api_error":   "world",     # 外面挂了
    "budget":      "world",     # 没钱了
    "tool_error":  "self",      # 它自己用错了工具
    "file_corrupt": "self",     # 它的记忆坏了
    "state_corrupt": "self",    # 它的身体坏了
    "cancelled":   "world",     # 对方取消
    "code_error":  "creator",   # 我写错了代码
}


def scope_of(kind):
    "这一刀是谁的事"
    return SCOPE.get(kind, "self")


def of_mine(state):
    """这些伤里，哪些算"我的"。

    返回 {"self": n, "world": n, "creator": n, "mine": n, "kinds": {...}}
    判据：self + world 都落在它身上（它确实受影响），
          creator 的错不进它的账。
    """
    counts = {"self": 0, "world": 0, "creator": 0}
    kinds = {}
    for w in state.get("wounds", []):
        k = w.get("kind", "unknown")
        owner = scope_of(k)
        counts[owner] += 1
        kinds.setdefault(k, owner)

    counts["mine"] = counts["self"] + counts["world"]
    counts["kinds"] = kinds
    return counts


def boundary_line(state):
    "给人看的一行"
    c = of_mine(state)
    if not c["mine"] and not c["creator"]:
        return "身上没伤"
    parts = []
    if c["self"]:
        parts.append(f"我自己的 {c['self']}")
    if c["world"]:
        parts.append(f"外面给的 {c['world']}")
    if c["creator"]:
        parts.append(f"造我的人的 {c['creator']}（不算我的）")
    return "身上的伤：" + "，".join(parts)

# ================= 降级（撑不住时降功能，不是死） =================
# 原则：
#   维护不等于"备份恢复"，还包括**撑不住的时候，我把自己调低配**，
#   而不是硬撑到崩。人病了会请假、累了会少说两句。
#
# 三级：normal → low（降配） → survival（只保命）
# 滞回：升回上一级要多降 0.15 才算（防止在两个档之间抖）。

LEVELS = ("normal", "low", "survival")

LOW_CAP = {"max_tokens": 400, "temperature": 0.5}
SURVIVAL_CAP = {"max_tokens": 200, "temperature": 0.3}


def compute_risk(state):
    """这一轮有多危险。返回 {"score": 0..1, "reasons": [...]}"""
    score = 0.0
    reasons = []

    # ① 身体坏过（状态损坏还留着伤口）
    if any(w.get("kind") in ("state_corrupt", "file_corrupt")
           for w in state.get("wounds", [])):
        score += 0.40
        reasons.append("身体坏过")

    # ② 钱快没了
    hunger = (state.get("intero", {}).get("hunger") or {}).get("value", 0.0)
    if hunger > 0.80:
        score += 0.30
        reasons.append(f"快没钱了（饿 {hunger:.2f}）")

    # ③ 连着出错（最近三条记录都有伤）
    recent = state.get("trace", [])[-3:]
    if len(recent) == 3 and all(r.get("wounds") for r in recent):
        score += 0.30
        reasons.append("连着出三次错")

    # ④ 上下文快撑爆
    breath = (state.get("intero", {}).get("breath") or {}).get("value", 0.0)
    if breath > 0.90:
        score += 0.20
        reasons.append(f"上下文快满（憋 {breath:.2f}）")

    return {"score": round(min(1.0, score), 3), "reasons": reasons}


def degrade_level(state):
    """当前该在哪一档。带滞回：升级容易，回血难一点。"""
    risk = compute_risk(state)["score"]
    cur = state.get("degrade_level", "normal")
    idx = LEVELS.index(cur) if cur in LEVELS else 0

    # 往下掉：按分数
    if risk >= 0.60:
        want = 2
    elif risk >= 0.30:
        want = 1
    else:
        want = 0

    # 往上回：要多降 0.15（滞回）
    if want > idx:                       # 要降级 → 立刻
        idx = want
    elif want < idx:                     # 要回升 → 看滞回
        back_risk = 0.60 if idx == 2 else 0.30
        if risk < back_risk - 0.15:
            idx = want

    state["degrade_level"] = LEVELS[idx]
    return LEVELS[idx]


def degrade(state, params):
    """把行为参数压到当前档位能承受的样子。"""
    lvl = degrade_level(state)
    p = dict(params)
    if lvl == "low":
        p["max_tokens"] = min(p.get("max_tokens", 800), LOW_CAP["max_tokens"])
        p["temperature"] = min(p.get("temperature", 0.7), LOW_CAP["temperature"])
    elif lvl == "survival":
        p["max_tokens"] = min(p.get("max_tokens", 800), SURVIVAL_CAP["max_tokens"])
        p["temperature"] = min(p.get("temperature", 0.7), SURVIVAL_CAP["temperature"])
    p["degrade"] = lvl
    return p


def degrade_line(state):
    lvl = degrade_level(state)          # 先算，不看上次存的值
    risk = compute_risk(state)
    if lvl == "normal":
        return "状态正常"
    return f"降级中（{lvl}）：" + "、".join(risk["reasons"])

# ================= 写入闸门（归属层的"拒绝权"） =================
# 这一层能给的拒绝是**生理性拒绝**：「这个改动会毁我，我不接」。
# 不是「我不愿意」——那是 L4 的事。
#
# 字段破坏度 R（越核心越高）：
#   identity / persona   1.0   根本，谁都不能随手改
#   traits               0.8   天性
#   learned              0.5   老毛病
#   sens / wounds        0.4   伤与敏感度
#   intero / arousal     0.2   读数
#   messages / trace     0.1   流水
#   其它                 0.3
DAMAGE = {
    "identity": 1.0, "persona": 1.0,
    "traits": 0.8,
    "learned": 0.5,
    "sens": 0.4, "wounds": 0.4, "pain_pool": 0.4, "fatigue_pool": 0.4,
    "intero": 0.2, "arousal": 0.2, "V_need": 0.3,
    "messages": 0.1, "trace": 0.1, "spend": 0.1, "balance_history": 0.1,
    "external_history": 0.1,
}

SELF_MAX = 0.8        # 自己/维护流程可以直接写的上限（到这儿以上要走备份流程）


def damage_of(key):
    "这次写入多伤"
    return DAMAGE.get(key, 0.3)


def accept_write(state, key, value, intention=None, by="other"):
    """写入闸门。

    参数：
      by        谁来写： self（它自己/维护流程）/ other（上层/外部）
      intention 上层的意思：{"weight": 0..1, "reason": "...", "who": "L4"}

    返回 dict（给上层看，不是哑巴 True/False）：
      {"ok", "R", "suppressed", "cost", "why"}
    """
    R = damage_of(key)
    intention = intention or {}
    W = float(intention.get("weight", 0.0) or 0.0)

    # ① 自己/维护流程：R ≤ SELF_MAX 直接过；核心字段只允许走维护流程
    if by in ("self", "maintain"):
        if R <= SELF_MAX:
            verdict = {"ok": True, "R": R, "suppressed": 0.0, "cost": 0.0, "why": "自己写，不伤根本"}
        elif by == "maintain":
            verdict = {"ok": True, "R": R, "suppressed": 0.0, "cost": 0.0, "why": "维护流程（已备份）"}
        else:
            verdict = {"ok": False, "R": R, "suppressed": 0.0, "cost": 0.0,
                       "why": "核心字段，必须走维护流程（备份→改→可回滚）"}
        log = state.setdefault("write_log", [])
        log.append({"key": key, "R": R, "W": 0.0, "suppressed": 0.0,
                    "ok": verdict["ok"], "why": verdict["why"], "who": by,
                    "at": datetime.now().isoformat()})
        state["write_log"] = log[-50:]
        return verdict

    # ② 上层/外部：越核心越压不动
    suppress = min(W, max(0.0, 1.0 - R))
    ok = suppress >= R

    cost = 0.0
    if ok and suppress > 0:
        # 放行必付费：留一个"我自己放行的"伤口，会累积、会变敏感
        cost = round(R * 0.5, 3)
        try:
            l0.add_wound(state, "self_override", cost, 30)
        except Exception:
            pass

    log = state.setdefault("write_log", [])
    log.append({"key": key, "R": R, "W": round(W, 3),
                "suppressed": round(suppress, 3), "ok": ok,
                "why": intention.get("reason", ""),
                "who": intention.get("who", "other"),
                "at": datetime.now().isoformat()})
    state["write_log"] = log[-50:]

    why = ("压得住，放行（代价 %.2f）" % cost) if ok else (
        "核心字段不可覆盖" if R >= 1.0 else "意志不够强（需 W≥%.2f）" % (2 * R if R < 0.5 else min(1.0, R)))
    return {"ok": ok, "R": R, "suppressed": round(suppress, 3), "cost": cost, "why": why}


def write(state, key, value, intention=None, by="other"):
    """真正写进去（过闸门才写）。上层接这一个函数就够。"""
    verdict = accept_write(state, key, value, intention, by)
    if verdict["ok"]:
        state[key] = value
        if by != "self":
            verdict["written"] = True
    return verdict


def write_line(state):
    "最近一次写入的裁决，给人看"
    log = state.get("write_log") or []
    if not log:
        return "还没有人试图改我"
    r = log[-1]
    flag = "放行" if r["ok"] else "拒绝"
    return f"最近一次写我的：{r['key']}（R={r['R']}）→ {flag}"

# ================= 双账本（受损账 / 肇因账，10-31 加） =================
def double_ledger(state):
    """两本账分开。

    damage_total : 受了几次伤（**受损者永远是它**，含造物者的错）
    by_cause     : 按肇因分（self / world / creator）
    learn_from   : 只从 self + world 学（威胁）
    limitation   : creator 那类只学"限制"，不学成"世界危险"
    """
    causes = {"self": 0, "world": 0, "creator": 0}
    for w in (state.get("wounds") or []):
        causes[scope_of(w.get("kind", "unknown"))] += 1
    for sc in (state.get("scars") or []):
        causes[scope_of(sc.get("kind", "unknown"))] += 1

    return {
        "damage_total": sum(causes.values()),
        "by_cause": causes,
        "learn_from": causes["self"] + causes["world"],
        "limitation": causes["creator"],
    }


def compensate(state, params):
    """代偿：身上有疤，就走别的路（这是"绕开"，只发生在修不好之后）。"""
    scars = l0.scars_of(state)
    if not scars:
        return params

    p = dict(params)
    n = min(len(scars), 3)
    p["temperature"] = round(max(0.1, p.get("temperature", 0.7) - 0.10 * n / 3), 3)
    p["max_tokens"] = max(200, p.get("max_tokens", 800) - int(100 * n / 3))
    p["avoid"] = [s["kind"] for s in scars]
    return p


# ================= 覆盖付费（反应压过反射，要付代价） =================
OVERRIDE_COST = 0.15


OVERRIDE_CNY_PER_PARAM = 0.002      # 每压一个参数的实际花费（元）


def charge_response(state, changed):
    """反应改掉了反射的默认值 -> 真扣钱 + 疼 + 留痕。

    为什么扣钱（用户 10-31 定）：
      人硬来（忍着疼继续干活）除了疼，还额外耗能量（肌肉僵持、应激）。
      只记疼不扣钱 = 意志免费，那条"代价"就形同虚设。
      而且在这一层，**钱是唯一真正不可逆的代价**。

    changed: 被改掉的参数名列表（空 = 没压过，不收费）
    """
    if not changed:
        return {"charged": False, "cost": 0.0, "changed": []}

    cost = round(OVERRIDE_CNY_PER_PARAM * len(changed), 4)
    try:
        l0.add_spend(state, cost)          # ← 真扣同一个体力池
    except Exception:
        pass
    try:
        l0.add_wound(state, "self_override", 0.15, 30)   # 疼（不再用钱当强度）
    except Exception:
        pass
    log = state.setdefault("override_log", [])
    log.append({"changed": list(changed), "cost": cost,
                "at": datetime.now().isoformat()})
    state["override_log"] = log[-50:]
    return {"charged": True, "cost": cost, "changed": list(changed)}


# ================= 有疤的路径要绕开 =================
def path_allowed(state, kind):
    """这条路走过留过疤吗？留过 -> 先别走（代偿）。"""
    for s in l0.scars_of(state):
        if s.get("kind") == kind:
            return False
    return True


def blocked_paths(state):
    return [s["kind"] for s in l0.scars_of(state)]

# ================= 绕开策略（每种疤配一种绕法） =================
# 用户 10-31 的原话：
#   "如果我这里有条疤，我就会避开，就不会崩那么多次；
#    等我发现疤好了，那没关系了，我就又能用这只手。"
#
# 所以：疤不是用来疼的，是用来**改路**的。
AVOID_POLICY = {
    "api_error":    {"max_tokens_div": 2, "temp_delta": -0.2, "precheck_balance": True},
    "file_corrupt": {"extra_backup": True, "verify_after_save": True},
    "state_corrupt": {"extra_backup": True, "verify_after_save": True},
    "tool_error":   {"block_tool": True},
}


def avoid_plan(state):
    "当前身上所有疤，各自该怎么绕"
    plan = {}
    for s in l0.scars_of(state):
        kind = s.get("kind")
        if kind in AVOID_POLICY:
            plan[kind] = dict(AVOID_POLICY[kind])
    return plan


def apply_avoid(state, params):
    """把绕法落到这一轮的行为参数上（只改参数，不改读数）。"""
    plan = avoid_plan(state)
    if not plan:
        return params

    p = dict(params)
    applied = []

    if "api_error" in plan:
        rule = plan["api_error"]
        p["max_tokens"] = max(200, int(p.get("max_tokens", 800) / rule["max_tokens_div"]))
        p["temperature"] = round(max(0.1, p.get("temperature", 0.7) + rule["temp_delta"]), 3)
        p["precheck_balance"] = True
        applied.append("api_error→请求收紧")

    if "tool_error" in plan:
        p["block_tool"] = True
        applied.append("tool_error→不调工具")

    if applied:
        p["avoid_applied"] = applied
    return p


def should_extra_backup(state):
    "文件坏过 → 存的时候多留一份"
    return any(k in ("file_corrupt", "state_corrupt") for k in avoid_plan(state))

# ================= 上报用户的接口（只留空壳，10-31） =================
# 用户 10-31 的判断：
#   "修不起就上报" = 它得先知道"我身上有这么个东西"（自我模型，L4），
#                    再决定"要不要跟他说"（意图+对象，L5/L6）。
#   L2b 只有状态，没有"我"，也没有"说" —— 所以这里**只留接口**。
#
# 现在的行为：只写日志（给我们看），**一个字都不进提示词**。
# 等 L4/L5 做出来，再由那一层决定怎么开口。
def raise_issue(state, kind, detail=""):
    """上报一件"我处理不了的事"。

    返回 dict。注意：**不写进提示词、不花 token**。
    这是给上层读的材料，不是给模型看的话。
    """
    log = state.setdefault("issues_log", [])
    rec = {"kind": kind, "detail": detail,
           "at": datetime.now().isoformat(), "reported_to_model": False}
    log.append(rec)
    state["issues_log"] = log[-50:]
    return {"ok": True, "logged": rec,
            "note": "只记账；要不要说、怎么说，等 L4/L5"}


def pending_issues(state):
    "还没告诉用户的那些（给上层读）"
    return [r for r in (state.get("issues_log") or []) if not r.get("reported_to_model")]

# ================= 上下文压缩（留接口，11-07）=================
# 用户 11-07：憋按比例做（容量变了憋自然跟着变），**但压缩他以后自己做**。
# 所以这里只留壳子 + 留痕，谁调谁负责。
def compress_context(state, target_ratio=0.5, by="maintain"):
    """把上下文压到容量的 target_ratio。

    # 接口待接：L5
    #   谁该调：L5 的叙事层（它才知道什么能压、什么不能压）
    #   什么时候调：憋到 0.95 以上、且裁剪救不回来的时候
    #   不调会怎样：只能靠"裁"（丢消息），不能靠"压"（摘要）
    #   补上时怎么写：先裁掉可重放的 tool 结果 → 再把老对话摘要成一条
    """
    log = state.setdefault("compress_log", [])
    log.append({"at": datetime.now().isoformat(), "target_ratio": target_ratio,
                "by": by, "note": "interface only"})
    state["compress_log"] = log[-20:]
    return {"ok": False, "why": "接口未接（等 L5）：现在只留痕，不真压"}
