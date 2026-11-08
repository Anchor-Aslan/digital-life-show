import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_channels_reachable.py —— 假器官检测（11-04 加）

**判据**：**每条通道都必须能被推到阈值以上。**
推不上去 = 墙上有开关、连着灯，但电线没接——你按它，什么都不会发生。

**允许的例外**：`l1_reflex.SIGNAL_ONLY` 里登记过的通道（只出信号，动作留给上层）。
但例外也要能"过线"——只是不要求它有动作。

**为什么要有这个测试**：
生理唤起那条通道，曾经有一个完整模型、有阈值、有动作，但没人调 release()，
读数恒为 baseline=0.30，永远碰不到阈值 0.80 —— **摆了一个星期，审计一次都没提过。**

反向验证：伪造一条永远到不了阈值的通道，检查器必须报红。
"""

import importlib.util
import os
from datetime import datetime, timedelta

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


def mk(**over):
    "一份能跑读数的最小状态"
    now = datetime.now().isoformat()
    st = {
        "messages": [],
        "intero": {},
        "wounds": [],
        "sens": {},
        "scars": [],
        "fatigue_pool": {"value": 0.0, "at": now},
        "pain_pool": {"kinds": {}, "at": now},
        "identity": {"gender": "male", "traits": {}},
        "arousal": {"since": now, "last_release": None},
        "external_history": {},
        "balance_history": [],
    }
    st.update(over)
    return st


# ============ 每条通道："把它推到极限，看能不能过线" ============
# 结构：(构造 state, 余额参数, 输入文本, 说明)
CASES = {
    "hunger": (lambda: mk(balance_history=[100.0]), 0.0, None, "余额 0，历史 100 → 饿 1.0"),
    "breath": (lambda: mk(messages=[{"id": f"m{i}", "role": "user", "content": "x",
                                     "source": "user"} for i in range(int(l0.TRAITS["breath"]["max_messages"] * 0.9))]), None, None,
               "90% 容量的消息 → 憋过线"),
    "fatigue": (lambda: mk(last_latency_ms=4000), None, None, "延迟 4000ms（基准 800）→ 累 5 倍"),
    "pain": (lambda: (lambda s: (l0.add_wound(s, "probe", 1.0), s)[1])(mk()), None, None,
             "留一道满强度的伤"),
    "arousal": (lambda: mk(arousal={"since": (datetime.now() - timedelta(days=30)).isoformat(),
                                    "last_release": None}), None, None, "锚点 30 天前 → 涨过线"),
    # 外部感知两条：读数来自"在它自己历史里的百分位"，所以要先喂一段低值历史
    "exclaim_pct": (lambda: mk(external_history={"exclaim": [0] * 20}), None, "!!!!!!!!",
                    "历史 20 个 0，这次 8 个叹号 → 百分位 1.0"),
    "chars_pct": (lambda: mk(external_history={"chars": [1] * 20}), None, "x" * 500,
                  "历史 20 个 1 字，这次 500 字 → 百分位 1.0"),
}


def can_cross(channel):
    "这条通道能不能被推到阈值以上"
    builder, balance, text, why = CASES[channel]
    st = builder()
    readings = l0.perceive(st, text, balance)
    val = readings.get(channel)
    th = l1.THRESHOLDS[channel]
    return (val is not None and val >= th), val, th, why


print("=" * 62)
print("① 每条通道都得能过线（过不了 = 假器官）")
print("=" * 62)
for ch in l1.THRESHOLDS:
    if ch not in CASES:
        check(f"{ch} 有构造器", False, "没写极值构造器，这条通道没被验过")
        continue
    ok, val, th, why = can_cross(ch)
    check(f"{ch} 能过线", ok, f"读数={val} 阈值={th}（{why}）")

print()
print("=" * 62)
print("② 有动作的通道，动作必须真能落到参数上")
print("=" * 62)
for ch in l1.THRESHOLDS:
    if ch in l1.SIGNAL_ONLY:
        continue
    react = l1.REACTIONS.get(ch) or {}
    has_effect = bool(react)
    check(f"{ch} 有预设动作", has_effect, f"{react}")
    if has_effect:
        # 动作里的 key 必须是 reflex_base 认得的
        base = l1.reflex_base()
        unknown = [k for k in react if k not in base]
        check(f"{ch} 的动作键合法", not unknown, f"不认识的键={unknown}")

print()
print("=" * 62)
print("③ 只出信号的通道，必须在 SIGNAL_ONLY 里登记（否则就是漏动作）")
print("=" * 62)
unregistered = [ch for ch in l1.THRESHOLDS
                if not (l1.REACTIONS.get(ch) or {}) and ch not in l1.SIGNAL_ONLY]
check("没有'既没动作又没登记'的通道", not unregistered, f"{unregistered}")
check("SIGNAL_ONLY 里的通道都还在 THRESHOLDS 里",
      all(ch in l1.THRESHOLDS for ch in l1.SIGNAL_ONLY), f"{sorted(l1.SIGNAL_ONLY)}")

print()
print("=" * 62)
print("④ 反向验证：伪造一条到不了阈值的通道 → 必须被判定为假器官")
print("=" * 62)


def fake_can_cross(channel, state, balance=None):
    "原本的判定逻辑，抽出来好做反向验证"
    readings = l0.perceive(state, None, balance)
    val = readings.get(channel)
    th = l1.THRESHOLDS[channel]
    return (val is not None and val >= th), val, th


# 伪造：把 arousal 的锚点设成"刚刚"，且不许线索加成 → 应该永远到不了 0.80
fake_st = mk(arousal={"since": datetime.now().isoformat(), "last_release": None})
ok_fake, val_fake, th_fake = fake_can_cross("arousal", fake_st)
check("刚出厂的 arousal 到不了阈值（这就是原来的假器官）", not ok_fake,
      f"读数={val_fake} 阈值={th_fake}")

# 反向验证 2：线索加成能把刚出厂的通道推过线（证明 note_cue 真的有用）
l0.note_cue(fake_st, 0.6)
ok_cue, val_cue, _ = fake_can_cross("arousal", fake_st)
check("戳一下线索就能过线（证明 cue 通了）", ok_cue, f"读数={val_cue}")

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
