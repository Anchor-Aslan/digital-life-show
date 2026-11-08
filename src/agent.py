"""agent.py —— 唯一主循环（10-27 改版）

分层：
  l0_sense.py  L0：只出体感读数（饿/憋/累/痛 + 外部感知原始量）
  l3_valence.py L3：效价（特征 → 一组坐标 + r；值能迁移才算 L3）

L0 的行为影响：憋太满 → 裁；痛 → 保守；太累 → 少说。
L3 的行为影响：饿到 hungry/starving → 压输出长度。
"""

import importlib.util
import json
import os
import shutil
import urllib.request
from datetime import datetime

HERE = os.path.dirname(__file__)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


l0 = _load("l0_sense")
l1 = _load("l1_reflex")
l2 = _load("l2_ownership")
l3 = _load("l3_valence")
l35 = _load("l3_5_ownership")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
# 小于半分钱不算"负后果"——不然每轮都学，越聊越怕（11-07 改）
SPEND_LEARN_MIN = 0.005
KEY_FILE = os.path.join(HERE, ".api_key")

STATE_DIR = os.path.join(HERE, "state")
STATE_FILE = os.path.join(STATE_DIR, "agent.json")
BACKUP_FILE = os.path.join(STATE_DIR, "agent.backup.json")

TRIM_KEEP_RATIO = 0.60      # 🎯 憋到线时，留容量的 60%（比例，不写死条数）


def trim_target(state):
    """裁到多少条：按当前容量算，不写死。"""
    cap = l0.trait(state, "breath", "max_messages")
    return max(4, int(cap * TRIM_KEEP_RATIO))
BASE_PROMPT = "你是一个简洁的助手。你记得你们之前聊过的事情。"

TOOL_SCHEMA = [{
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "计算四则运算表达式",
        "parameters": {"type": "object",
                       "properties": {"expr": {"type": "string"}},
                       "required": ["expr"]},
    },
}]


def tool_calculator(expr):
    allowed = set("0123456789+-*/(). ")
    if not set(expr) <= allowed:
        return "错误"
    try:
        return str(eval(expr, {"__builtins__": {}}, {}))
    except Exception as e:
        return "计算失败：" + str(e)


TOOLS = {"calculator": tool_calculator}


def load_key():
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    with open(KEY_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def default_state():
    return {
        "messages": [],
        "last_seen": None,
        "last_latency_ms": 800,
        "intero": {},
        "V_need": {},
        "wounds": [],            # 伤口列表
        "scars": [],             # 瘢痕（永久，assisted 可修掉）
        "dead_channels": [],     # 受损的通道（可修，不是死）
        "channel_fails": {},     # 各通道连续失败次数
        "override_log": [],      # 反应压过反射的留痕
        "intervention_log": [],  # 上层干预（如修疤）的留痕
        "confirm_cooldown": 0,
        "confirm_last_at": None,   # 上次确认的时间（冷却按时间衰减）    # confirm 冷却（施工单 5 第 2 条：问过就别再问）
        "fp_seen": {},           # 见过哪些字形（施工单 4 第 6 条：新奇度按字形算）
        "prev_feat": None,        # 上一轮的刺激特征（任务 5：延迟一轮记后果）
        "prev_text_norm": "",     # 上一轮原文（去标点，判"原样重发"）
        "reaction_log": [],       # 用户反应学习的留痕（可回滚）
        "reaction_count": 0,      # 本场学了几次（锁②：上限 3）
        "compress_log": [],      # 压缩的留痕（接口空壳，等 L5）
        "issues_log": [],        # "我处理不了的事"（只记账，不进提示词）
        "last_usage": {},
        "last_readings": {},        # 上一轮 API 的用量（行为归属要核"我说到没说到")
        "pain_pool": {"kinds": {}, "at": datetime.now().isoformat()},
        "fatigue_pool": {"value": 0.0, "at": datetime.now().isoformat()},  # 体力桶
        "sens": {},              # 各类伤害的敏感度
        "arousal": {},           # 生理唤起（没性别就空着）
        "identity": {"gender": None, "traits": {}},   # 天性：性别 + 各通道参数
        "pending_response": None,  # 上层这一轮的"反应"（反射不可覆盖）
        "balance_history": [],
        "external_history": {},
        "spend": {"date": datetime.now().date().isoformat(), "today_cny": 0.0, "history": []},
        "trace": [],          # ← L1：逐轮记录（读数 / 动作 / 结果 / 读数变化）
        "learned": {},
        "valence": {},          # L3 值表（键 → 坐标 + r）
        "valence_keys": [],     # 学过哪些键
        "bad_weight": 2.25,     # 坏比好重多少（出厂由正常区抽样）
        "flag_extreme": False,  # 是否被点名进过病理区（留痕）
        "hygiene_sensitivity": 1.0,  # 信息卫生敏感度（1.0=正常人；越小越容易恶心）        # ← L2：学成的老毛病（同一种伤 ≥3 次）

        # ↓↓↓ 11-02 补：这些键代码里会写、但以前没在这里登记，
        #     load_state 只搬 default_state 里有的键 → 它们**每次重启都清零**（踩坑 #32）。
        #     规矩：以后任何 state["x"] = ... 的写法，x 必须先登记在这里。
        "maintenance": {},          # 最近一次维护（落盘/备份）的记录
        "maintenance_budget": 0.10,  # 维护预算（决定留几份备份）
        "maintenance_veto": [],      # 否决维护的留痕
        "write_log": [],             # 谁写过我的状态（self/other）—— 归属的凭据
        "degrade_level": "normal",   # 降级档位（滞回需要它跨重启）
        "heal_enabled": True,        # 自动修复开关（上层可关）
        "last_pain": 0.0,            # 上一刻的痛（应激水平要用）
        "analgesia_bias": 0.0,       # 上层旋钮：-1 更疼 / +1 更麻
        "pain_modulation": 0.0,      # 上层调制：这一刀能到多高
        # 另外四条调制走的是动态键名（state.get(channel + "_modulation")），
        # 检查器扫不到 → 只能手动登记在这里，否则上层设了、重启就没了。
        "hunger_modulation": 0.0,
        "breath_modulation": 0.0,
        "fatigue_modulation": 0.0,
        "arousal_modulation": 0.0,
        "apoptosis_log": [],         # 通道受损的历史
        "repair_log": [],            # 通道修好的历史

        # ↓↓↓ 11-04 补：抑制器 + 压力派生量
        "arousal_suppression": 0.0,  # L1 每轮算（生理层：累/痛/慢性压力）→ 压低唤起
        "pressure_history": [],      # 压力的历史（近 20 轮）；慢平均就是 chronic
    }


def load_state():
    notes = []
    if not os.path.exists(STATE_FILE):
        return default_state(), notes
    try:
        with open(STATE_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        st = default_state()
        for k in st:
            if k in data:
                st[k] = data[k]
        return st, notes
    except Exception as e:
        notes.append(f"主文件坏了：{e}")
        st = default_state()
        l0.add_wound(st, "state_corrupt", 0.9, 60)   # 出事就留伤口（痛）
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            for k in st:
                if k in data and k != "wounds":
                    st[k] = data[k]
            notes.append("已从备份恢复（伤口保留）")
            return st, notes
        except Exception as e:
            notes.append(f"备份也坏：{e}")
    return st, notes


def build_prompt(state, params=None):
    """模型能看到的唯一东西。

    原则（用户 10-31 定）：**L0–L2 是下意识的，不许把读数报给它。**
      人的自主神经不会告诉你"血氧 98%"，
      所以这里**只给行为参数，不给数字、不给"体感"二字**。
      它话变短，但不知道为什么——这才是下意识。
    真正能说"我累了"是 L4 的事（有符号之后）。

    11-07 任务 3：允许拼**行为风格**（"这轮说短点"），
      但只能从 l1.STYLE_VOCAB 里取——不许写原因、不许写数字（审计第 12 步查）。
    """
    parts = [BASE_PROMPT]
    for k in (params or {}).get("style") or []:
        phrase = l1.STYLE_VOCAB.get(k)
        if phrase:
            parts.append(phrase)
    return "\n".join(parts)


def save_state(state):
    """保存 = 维护自己（L2 的事，不是 L1 的）。
    动作不可关闭；budget 只决定留几份备份。"""
    l2.maintain(state, STATE_FILE, BACKUP_FILE)


def to_api(msgs):
    out = []
    for m in msgs:
        d = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            d["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            d["tool_call_id"] = m["tool_call_id"]
        out.append(d)
    return out


def call_model(messages, system_prompt, params):
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "tools": TOOL_SCHEMA, "tool_choice": params.get("tool_choice", "auto"),
            "temperature": params["temperature"], "max_tokens": params["max_tokens"]}
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + load_key()},
        method="POST")
    t0 = datetime.now()
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode("utf-8"))
    # ⚠ finish_reason 在 choices[0] 上，**不在 message 里**（OpenAI 兼容格式都这样）。
    #   以前直接返回 message，run_turn 里 `msg.get("finish_reason")` 永远是 None
    #   → "输出被截断"的学习信号从来没触发过（11-07 审稿发现，第 0 号任务）。
    choice = data["choices"][0]
    msg = dict(choice.get("message") or {})
    msg["finish_reason"] = choice.get("finish_reason")
    return (msg, data.get("usage", {}),
            int((datetime.now() - t0).total_seconds() * 1000))


def build_readings_l1(state, readings, intero, feat, val):
    """把"这一轮要喂给 L1 的东西"拼好（主循环和探针共用）。

    ⚠ A3（11-07）：探针以前直接往 reflex() 里塞轴值，
      结果"探针能过、真实运行不走"（precision 那条就是这么死的）。
      现在两边都走这一个函数，不许再各拼各的。
    """
    out = {**readings,
           **{f"{k}_rate": v["rate"] for k, v in (intero or {}).items()},
           "valence_avoid": val["avoid"],
           "valence_approach": val["approach"],
           "valence_conflict": val.get("conflict", 0.0),
           "valence_effort": val.get("effort", 0.0),
           "valence_control": (val.get("control_sense")
                               if val.get("control_sense") is not None else 0.5),
           # 没经历过就是 None（核不到），不许变成 0
           "valence_precision_epi": ((val.get("precision") or {}).get("episodic")),
           # 生理恶心：自己的出口（≥0.70 才话变短、不展开）
           "disgust_physio": val.get("disgust_physio", 0.0),
           "arousal_axis": val.get("arousal", 0.0),
           "_key_seen": feat["exact"] in (state.get("valence") or {})}
    return out


def startup_preview(state, balance):
    """启动时打印 [行为] 用的**预览**。

    ⚠ 三条纪律（施工单 7）：
      ① **只读/只记一次**：reflex 只是预览，**不许消耗冷却**（不调 note_confirm_cooldown）。
      ② `update_intero()` 一轮只调一次：同一次读数记两遍会把基线窗口灌脏。
      ③ 不学、不写 trace。
    返回 (params, readings, intero)。
    """
    readings = l0.perceive(state, None, balance)
    intero = l0.update_intero(state, readings)        # ← 只调这一次
    readings_l1 = {**readings, **{f"{k}_rate": v["rate"] for k, v in intero.items()}}
    params, applied = l1.reflex(state, readings_l1)   # 只读，不写 state
    resp = l1.response(state, readings_l1)
    params = l1.combine(params, resp)
    params = l2.apply_learned(state, params)
    params = l2.degrade(state, params)
    params = l2.compensate(state, params)
    params = l2.apply_avoid(state, params)
    return params, readings, intero


def run_turn(state, user_text, system_prompt, params):
    state["messages"].append(l0.make_msg("user", user_text, "user"))
    history = to_api(state["messages"])
    signals = []

    for _ in range(8):
        try:
            msg, usage, latency = call_model(history, system_prompt, params)
            state["last_usage"] = usage
        except Exception:
            l0.add_wound(state, "api_error", 0.8, 30)   # 报错 = 受伤
            raise
        l0.add_spend(state, l0.cost_of_usage(usage))
        state["last_latency_ms"] = latency
        l0.add_load(state, latency)        # 只有"特别久"才加负荷
        l0.add_work(state, "chat")         # 说一句话：几乎不累

        content = msg.get("content") or ""
        state["messages"].append(l0.make_msg("assistant", content, "self",
                                             tool_calls=msg.get("tool_calls")))
        history.append({"role": "assistant", "content": content})

        if msg.get("finish_reason") == "length":
            signals.append("truncated_by_budget")
            l0.add_work(state, "long_out")

        calls = msg.get("tool_calls") or []
        if not calls:
            return content, signals

        for tc in calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            # 代偿：这条路上留过疤 -> 先绕开
            if not l2.path_allowed(state, "tool_error"):
                result = "这条路之前留过疤，先绕开（不调用工具）"
                state["messages"].append(l0.make_msg("tool", result, "tool",
                                                     tool_call_id=tc["id"]))
                history.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                continue
            result = TOOLS[name](**args) if name in TOOLS else "未知工具"
            if result.startswith("错误") or result.startswith("计算失败"):
                l0.add_wound(state, "tool_error", 0.3, 10)
                l0.add_work(state, "retry")       # 返工比干活还累
                if l0.note_channel_failure(state, "tool"):
                    print("[损伤] 工具通道连续失败，暂时受损（可修）")
            l0.add_work(state, "tool")     # 调工具才真费劲
            state["messages"].append(l0.make_msg("tool", result, "tool",
                                                 tool_call_id=tc["id"]))
            history.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
        history = to_api(state["messages"])

    return "（工具调用过多，停止）", signals


if __name__ == "__main__":
    state, notes = load_state()

    # ⚠ A4（11-07 修）：锁②是"一场会话最多 3 次"，不是"一辈子 3 次"。
    #   这三个键会存盘，不清就会永久累积。
    state["reaction_count"] = 0
    state["prev_feat"] = None
    state["prev_text_norm"] = ""
    for n in notes:
        print(f"[恢复] {n}")

    cont = l2.continuity(state)
    if cont["ok"]:
        old = "、".join(cont["learned"]) if cont["learned"] else "无"
        print(f"[L2] 还是它：老毛病 {old}")
    else:
        print(f"[L2] 缺了：{cont['missing']}")

    api_key = load_key()
    balance = l0.read_balance_cny(api_key)

    # 启动预览：只读（不消耗冷却）、基线只记一次
    params, readings, intero = startup_preview(state, balance)

    print(f"[L0] {l0.intero_line(intero)}")
    _f0 = l3.extract_features("", state)
    print(f"[L3] {l3.line(_f0, l3.value_of(state, _f0))}")
    print(f"[L2] {l2.boundary_line(state)}")
    print(f"[L2] {l2.degrade_line(state)}")
    print(f"[行为] {params}")
    print(f"余额 ¥{balance}  载入历史 {len(state['messages'])} 条\n")

    while True:
        try:
            q = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("q", "quit", "exit"):
            break
        if not q:
            continue

        # ⚠ A1（11-07 修）：**先算特征，再刷新 last_seen**。
        #   反过来的话，"距上一轮多久"永远≈0 → pace 永远 fast → 18 个格子只用到 6 个。
        _last_seen_before = state.get("last_seen")
        state["last_seen"] = now_iso()
        turn_t0 = datetime.now().isoformat()
        _spend_before = state.get("spend", {}).get("today_cny", 0.0)
        _prev_feat = state.get("prev_feat")
        _prev_norm = state.get("prev_text_norm")
        _tools_before = sum(1 for m in state["messages"] if m.get("source") == "tool")
        balance = l0.read_balance_cny(api_key)
        readings = l0.perceive(state, q, balance)
        # ① 受伤 → 先修（下意识，扣同一个体力池）
        healed = l0.heal(state, balance)
        if healed.get("kind"):
            print(f"[修复] {healed['why']}（花费 ¥{healed['cost']}）")
        intero = l0.update_intero(state, readings)

        # ② 派生量：压力（稳态负荷）—— 急性戳兴奋，慢性压抑制
        #    注意：这两个动作影响的是**下一轮**的 arousal 读数（本轮已经读过了）。
        pres = l0.pressure(state)
        if pres["acute"] > 0:
            l0.note_cue(state, pres["acute"] * 0.3)        # 急性压力当线索（急性压力推高兴奋）
        state["arousal_suppression"] = l1.suppression(state, pres)   # 慢性压力 + 累 + 痛 → 压低

        # ③ L3：把这一下变成键，再取出"多想要 / 多想躲"（值不进提示词，只喂 L1）
        _feat_state = dict(state)
        _feat_state["last_seen"] = _last_seen_before      # ← 用刷新前的值算间隔
        feat = l3.extract_features(q, _feat_state)
        state["last_readings"] = {k: v for k, v in readings.items()
                                  if isinstance(v, (int, float))}
        val = l3.value_of(state, feat, text=q, msgs=state["messages"])

        # —— 任务 5：把"上一轮说完之后你的表面反应"记到上一轮那条刺激上
        _rr, _rwhy = l3.reaction_reward(_prev_feat, _prev_norm, feat, q,
                                        state.get("reaction_count", 0))
        if _rr is not None and _prev_feat:
            _keys = l3.keys_touched_by_learn(_prev_feat)
            _before = {k: dict((state.get("valence") or {}).get(k) or {}) for k in _keys}
            l3.learn(state, _prev_feat, _rr)
            l3.log_reaction(state, _keys, _rr, _before)
            state["reaction_count"] = state.get("reaction_count", 0) + 1
            print(f"[L3 学·反应] {_rwhy} → 键 {_prev_feat['exact']} 记 {_rr:+.2f}"
                  f"（本场 {state['reaction_count']}/{l3.REACTION_CAP}）")
        val["arousal"] = l3.arousal_axis(state, readings, pres)
        readings_l1 = build_readings_l1(state, readings, intero, feat, val)
        # ⚠ 顺序：**先用这一轮之前的 seen 算 precision，再记"见过了"**
        #   反过来的话，第一次见面就已经是"见过 1 次"，confirm 永远不会触发。
        l3.note_seen(state, feat)
        l1.decay_confirm_cooldown(state)          # 先按时间衰减（睡久了冷却自然归零）
        params, applied = l1.reflex(state, readings_l1)
        l1.note_confirm_cooldown(state, applied)  # 冷却只在这里写（reflex 只读）
        resp = l1.response(state, readings_l1)
        _before = dict(params)
        params = l1.combine(params, resp)
        if resp:
            changed = [k for k in _before if _before[k] != params.get(k)]
            fee = l2.charge_response(state, changed)
            if fee["charged"]:
                print(f"[覆盖] 反应压过反射 {fee['changed']}，代价 ¥{fee['cost']}")
        params = l2.apply_learned(state, params)
        params = l2.degrade(state, params)
        params = l2.compensate(state, params)
        params = l2.apply_avoid(state, params)      # ④ 每种疤都有自己的绕法
        if params.get("avoid_applied"):
            print(f"[绕开] {params['avoid_applied']}")
        print(f"[L3] {l3.line(feat, val)}")
        before = {k: v["value"] for k, v in intero.items()}

        system_prompt = build_prompt(state, params)

        answer, signals = run_turn(state, q, system_prompt, params)

        # —— L3 学：只看**可测的后果**（工具成败 / 花钱），不看"用户是不是高兴"（那要 L4）
        spend_delta = round(state.get("spend", {}).get("today_cny", 0.0) - _spend_before, 4)
        reward = None
        why = ""
        if any("truncated_by_budget" in s for s in signals):
            reward, why = -0.6, "输出被预算截断（没说完）"
        elif any(w.get("kind") == "tool_error" for w in state.get("wounds", [])
                 if str(w.get("at", "")) >= turn_t0):
            reward, why = -1.0, "工具出错"
        elif spend_delta >= SPEND_LEARN_MIN:
            # 只有"明显贵"才算负后果。正常聊天每轮几分钱，学它 = 越聊越怕（频率保真）
            reward, why = -0.30, f"这一轮花了 ¥{spend_delta}"
        if reward is not None:
            e = l3.learn(state, feat, reward)
            got = e.get(feat["exact"], {})
            print(f"[L3 学] {why} → 键 {feat['exact']} "
                  f"靠近 {got.get('approach', 0):+.2f} / 躲开 {got.get('avoid', 0):+.2f}")

        _trimmed = 0
        _trim_to = trim_target(state)
        if params["trim"] and len(state["messages"]) > _trim_to:
            keep = set(params.get("trim_keep") or [])
            head = state["messages"][: len(state["messages"]) - _trim_to]
            saved = [m for m in head if m.get("id") in keep]
            tail = state["messages"][-_trim_to:]
            print(f"[维持] 憋得厉害，裁到 {_trim_to} 条（救回 {len(saved)} 条）")
            _trimmed = len(state["messages"]) - (_trim_to + len(saved))
            state["messages"] = tail + saved

        balance2 = l0.read_balance_cny(api_key)
        readings = l0.perceive(state, None, balance2)
        intero = l0.update_intero(state, readings)
        after = {k: v["value"] for k, v in intero.items()}

        # —— L3.5：三条通路收敛（只进 trace 和控制台，一个字都不进提示词）
        _tools_after = sum(1 for m in state["messages"] if m.get("source") == "tool")
        own = l35.measure(state, intero,
                          {"approach": val["approach"], "avoid": val["avoid"]},
                          params,
                          {"trimmed": _trimmed,
                           "trim_needed": bool(params.get("trim")),
                           "tool_calls": _tools_after - _tools_before,
                           "max_completion_tokens":
                               (state.get("last_usage") or {}).get("completion_tokens")})
        print(f"[L3.5] {l35.line(own)}")

        # —— L1：把这一轮记下来（读数前 / 动作 / 结果 / 读数后 / 差值）
        state["prev_feat"] = feat
        state["prev_text_norm"] = l3._norm_text(q)

        state["trace"] = (state.get("trace", []) + [{
            "t": now_iso(),
            "before": before,
            "action": {k: params.get(k) for k in ("max_tokens", "trim", "temperature", "urgent", "style", "tool_choice")},
            "applied": applied,
            "response": resp,
            "wounds": [w.get("kind") for w in state.get("wounds", [])
                       if str(w.get("at", "")) >= turn_t0],
            "signals": signals,
            "after": after,
            "delta": {k: round(after.get(k, 0) - before.get(k, 0), 3) for k in before},
            "ownership": {"O": own["O"], "n_paths": own["n_paths"],
                          "level": own["level"], "parts": own["parts"]},
        }])[-50:]

        learned, newly = l2.learn(state)
        for k in newly:
            print(f"[L2] 学成了：{k} 是我的老毛病（第 {learned[k]['count']} 次了）")

        save_state(state)
        print(f"[L0] {l0.intero_line(intero)}")
        print("AI > " + answer + "\n")

    save_state(state)
