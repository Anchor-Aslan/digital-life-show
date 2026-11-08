import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_confirm_cooldown.py —— confirm 冷却（施工单 5 / 第 2 条，用户选 B）

判据：
    ① 不带冷却时，统一语料（话题各异）触发 15/20
    ② 带冷却 5 轮时，降到 ≤ 6/20（30%）
    ③ 冷却行为对：问过一次之后，接下来 5 轮不再问，第 6 轮才可能再问
    ④ 不用重复语料（那是施工单 4 的错误测法）
"""

import importlib.util
import os

BASE = SRC_DIR


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l3 = load("l3_valence")
l1 = load("l1_reflex")
ag = load("agent")
corpus = _load_helper("_corpus_varied")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


R0 = {"pain": 0.0, "fatigue": 1.0, "breath": 0.0, "hunger": 0.0}
IT = {k: {"value": 0.0, "rate": 0.0} for k in R0}


def run(cool):
    old = l1.CONFIRM_COOLDOWN
    l1.CONFIRM_COOLDOWN = cool
    st = ag.default_state()
    st["messages"] = []
    seq = []
    try:
        for q in corpus.VARIED:
            f = l3.extract_features(q, st)
            v = l3.value_of(st, f, text=q, msgs=st["messages"])
            rl = ag.build_readings_l1(st, R0, IT, f, v)
            l1.decay_confirm_cooldown(st)             # 和 agent 一样：轮前先按时间衰减
            p, applied = l1.reflex(st, rl)
            l1.note_confirm_cooldown(st, applied)     # 和 agent 一样：一轮写一次
            seq.append(1 if "confirm" in p["style"] else 0)
            l3.note_seen(st, f)
            st["messages"].append({"role": "user", "content": q, "source": "user"})
    finally:
        l1.CONFIRM_COOLDOWN = old
    return seq, sum(seq)


print("=" * 66)
print("① 不带冷却：确认它确实太高（15/20）")
print("=" * 66)
seq0, n0 = run(0)
print("  ", "".join(map(str, seq0)), "→", f"{n0}/20")
check("不带冷却时触发 >30%（证明这个坑真实存在）", n0 > 6, f"({n0}/20)")

print()
print("=" * 66)
print("② 带冷却 5 轮：降到 ≤30%")
print("=" * 66)
seq5, n5 = run(5)
print("  ", "".join(map(str, seq5)), "→", f"{n5}/20")
check("带冷却后 ≤ 30%", n5 <= int(len(corpus.VARIED) * corpus.MAX_RATE), f"({n5}/20)")

print()
print("=" * 66)
print("③ 冷却行为：问过一次，接下来 5 轮不再问")
print("=" * 66)
first = seq5.index(1) if 1 in seq5 else -1
gap = None
for i in range(first + 1, len(seq5)):
    if seq5[i] == 1:
        gap = i - first
        break
check("第一次触发后有间隔", first >= 0, f"(第一次在第 {first + 1} 句)")
check("两次触发之间至少隔 5 轮", gap is None or gap > l1.CONFIRM_COOLDOWN,
      f"(实际间隔 {gap})")

print()
print("=" * 66)
print("④ 用的是统一语料（话题各异），不是重复语料")
print("=" * 66)
check("语料 20 条且互不相同", len(corpus.VARIED) == 20 and len(set(corpus.VARIED)) == 20,
      f"(共 {len(corpus.VARIED)} 条，去重后 {len(set(corpus.VARIED))} 条)")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

print()
print("=" * 66)
print("⑤ reflex 必须只读：预览参数不许吃掉冷却")
print("=" * 66)
st_cd = {"confirm_cooldown": 3}
for _ in range(3):
    l1.reflex(st_cd, {})          # 三次什么都没有的调用
check("连调 3 次 reflex，冷却不变", st_cd["confirm_cooldown"] == 3,
      f"({st_cd['confirm_cooldown']})")

st_cd2 = {"confirm_cooldown": 3}
l1.note_confirm_cooldown(st_cd2, [])          # 一次"没触发"的记账
check("调一次 note_confirm_cooldown（没触发）→ 减 1", st_cd2["confirm_cooldown"] == 2,
      f"({st_cd2['confirm_cooldown']})")
l1.note_confirm_cooldown(st_cd2, [{"channel": "axis:valence_precision_epi"}])
check("触发一次 → 重置为 5", st_cd2["confirm_cooldown"] == l1.CONFIRM_COOLDOWN,
      f"({st_cd2['confirm_cooldown']})")

print()
print("=" * 66)
print("⑥ 静态：reflex() 的函数体里不许给 state[...] 赋值")
print("=" * 66)
import ast as _ast
_src = open(os.path.join(BASE, "l1_reflex.py"), encoding="utf-8").read()
_tree = _ast.parse(_src)
_bad = []
for node in _ast.walk(_tree):
    if isinstance(node, _ast.FunctionDef) and node.name == "reflex":
        for sub in _ast.walk(node):
            if isinstance(sub, _ast.Assign):
                for tg in sub.targets:
                    if isinstance(tg, _ast.Subscript) and isinstance(tg.value, _ast.Name) \
                            and tg.value.id == "state":
                        _bad.append(sub.lineno)
check("reflex 体内没有 state[...] 赋值", not _bad, f"(违规行 {_bad})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

print()
print("=" * 66)
print("⑦ 冷却按时间衰减（用户选 B：超过 4 小时归 0）")
print("=" * 66)
from datetime import datetime, timedelta

st_d = {"confirm_cooldown": 4, "confirm_last_at": (datetime.now() - timedelta(hours=5)).isoformat()}
got = l1.decay_confirm_cooldown(st_d)
check("距上次 5 小时（>4h）→ 冷却归 0", got == 0 and st_d["confirm_cooldown"] == 0,
      f"({got}, 存的是 {st_d['confirm_cooldown']})")

st_d2 = {"confirm_cooldown": 4, "confirm_last_at": (datetime.now() - timedelta(hours=3)).isoformat()}
got2 = l1.decay_confirm_cooldown(st_d2)
check("距上次 3 小时（<4h）→ 冷却保留（去忙一阵不算断）",
      got2 == 4 and st_d2["confirm_cooldown"] == 4, f"({got2})")

st_d2b = {"confirm_cooldown": 4, "confirm_last_at": (datetime.now() - timedelta(minutes=31)).isoformat()}
check("距上次 31 分钟 → 当然保留（30 分钟那个旧值不再是界）",
      l1.decay_confirm_cooldown(st_d2b) == 4, f"({st_d2b['confirm_cooldown']})")

st_d3 = {"confirm_cooldown": 4}
check("没有时间戳（老状态文件）→ 数值照旧，不炸", l1.decay_confirm_cooldown(st_d3) == 4,
      f"({l1.decay_confirm_cooldown(st_d3)})")

# 触发一次会记时间戳
st_d4 = {"confirm_cooldown": 0}
l1.note_confirm_cooldown(st_d4, [{"channel": "axis:valence_precision_epi"}])
check("触发后记下时间戳", bool(st_d4.get("confirm_last_at")),
      f"({st_d4.get('confirm_last_at')})")

print()
print("=" * 66)
print("⑧ 睡一觉再打开：冷却自动消失（跨会话口径 = 按时间，不是按会话）")
print("=" * 66)
st_sleep = {"confirm_cooldown": 5,
            "confirm_last_at": (datetime.now() - timedelta(hours=8)).isoformat()}
l1.decay_confirm_cooldown(st_sleep)
check("隔 8 小时重启（半天以上）→ 冷却 0（可以重新问）", st_sleep["confirm_cooldown"] == 0,
      f"({st_sleep['confirm_cooldown']})")

st_quick = {"confirm_cooldown": 5,
            "confirm_last_at": (datetime.now() - timedelta(seconds=10)).isoformat()}
l1.decay_confirm_cooldown(st_quick)
check("关掉 10 秒再打开 → 冷却还在（不会马上又问一遍）", st_quick["confirm_cooldown"] == 5,
      f"({st_quick['confirm_cooldown']})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

print()
print("=" * 66)
print("⑨ 启动预览不许消耗冷却、不许把基线记两遍（施工单 7）")
print("=" * 66)
from datetime import datetime as _dt

st_boot = ag.default_state()
st_boot["confirm_cooldown"] = 3
st_boot["confirm_last_at"] = _dt.now().isoformat()      # 刚确认过（没过 4 小时）
_h = {c: len((st_boot.get("intero") or {}).get(c, {}).get("history", []))
      for c in ("pain", "fatigue", "breath", "hunger")}

ag.startup_preview(st_boot, 0.0)                        # 就是启动时那一次

check("启动之后 confirm_cooldown 仍是 3（预览不吃冷却）",
      st_boot["confirm_cooldown"] == 3, f"({st_boot['confirm_cooldown']})")

_h2 = {c: len((st_boot.get("intero") or {}).get(c, {}).get("history", []))
       for c in ("pain", "fatigue", "breath", "hunger")}
delta = {c: _h2[c] - _h[c] for c in _h}
check("每个通道的 history 只多 1（同一次读数不许记两遍）",
      all(v == 1 for v in delta.values()), f"({delta})")

if FAIL:
    raise SystemExit(1)

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

if FAIL:
    raise SystemExit(1)
