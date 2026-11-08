import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_precision_seen.py —— 施工单 3 / 第 2 条：亲历按"见过"算，不按"学过"算

要证明四件事：
    ① 同一条消息连发 5 次，只有第 1 次会 confirm
    ② 20 条普通消息，confirm 触发 ≤ 6（30%）
    ③ learn() 不改变 seen；note_seen() 不改变 approach/avoid
    ④ seen 能存能读（persist）
"""

import importlib.util
import json
import os
import tempfile

BASE = SRC_DIR


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l3 = load("l3_valence")
l1 = load("l1_reflex")
ag = load("agent")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


R0 = {"pain": 0.0, "fatigue": 1.0, "breath": 0.0, "hunger": 0.0}
INTERO = {k: {"value": 0.0, "rate": 0.0} for k in R0}


def turn(st, q):
    """走一遍真实的这半条链路：特征 → 值 → 读数 → reflex（并记 seen）"""
    f = l3.extract_features(q, st)
    val = l3.value_of(st, f, text=q, msgs=st.get("messages"))
    rl = ag.build_readings_l1(st, R0, INTERO, f, val)
    p, _ = l1.reflex(st, rl)
    l3.note_seen(st, f)
    st.setdefault("messages", []).append({"role": "user", "content": q, "source": "user"})
    return p, rl


print("=" * 66)
print("① 同一条消息连发 5 次：只有第 1 次 confirm")
print("=" * 66)
st = ag.default_state()
st["messages"] = []
hits = []
LONG = "我想问一下这个方案到底行不行"          # ≥6 字：够长才判"新不新"
for i in range(5):
    p, rl = turn(st, LONG)
    hits.append("confirm" in p["style"])
print(f"   5 次结果：{hits}   precision={rl['valence_precision_epi']}")
check("只有第 1 次 confirm（后面见过这些字了）",
      hits == [True, False, False, False, False], f"({hits})")

print()
print("=" * 66)
print("② 20 条普通消息：confirm ≤ 6 次（30%）")
print("=" * 66)
MSGS = ["你好", "在吗", "今天天气不错", "我想问个事", "帮我看看这段代码", "嗯", "好的",
        "你叫什么名字", "随便聊聊", "最近有点忙", "你觉得这个方案行吗", "我想吃火锅",
        "哈哈哈", "再讲细一点", "为什么", "我有点累了", "帮我想个名字", "谢谢", "晚安", "明天见"]
st2 = ag.default_state()
st2["messages"] = []
n = 0
for q in MSGS:
    p, _ = turn(st2, q)
    if "confirm" in p["style"]:
        n += 1
print(f"   confirm 触发：{n}/20")
check("触发率 ≤ 30%", n <= 6, f"({n}/20 = {n/20:.0%})")

print()
print("=" * 66)
print("③ learn 不动 seen；note_seen 不动 approach/avoid")
print("=" * 66)
st3 = ag.default_state()
f = l3.extract_features("你好", st3)
seen0 = 0
l3.learn(st3, f, -1.0)
st3.setdefault("valence", {})
e = st3["valence"].get(f["exact"]) or {}
check("learn 不新增 seen（或新建时 seen=0）", int(e.get("seen", 0) or 0) == seen0,
      f"(seen={e.get('seen')})")

st4 = ag.default_state()
f4 = l3.extract_features(LONG, st4)
val0 = l3.value_of(st4, f4, text=LONG)
l3.note_seen(st4, f4)          # 见过一次，这些字就都认识了
val1 = l3.value_of(st4, f4, text=LONG)
check("note_seen 不改 approach/avoid",
      abs(val0["approach"] - val1["approach"]) < 1e-9 and abs(val0["avoid"] - val1["avoid"]) < 1e-9,
      f"(away {val0['avoid']:.4f} → {val1['avoid']:.4f})")
check("但是 precision 变了（0.0 → 1.0，按字形覆盖率）",
      (val0["precision"]["episodic"], val1["precision"]["episodic"]) == (0.0, 1.0),
      f"({val0['precision']['episodic']} → {val1['precision']['episodic']})")

print()
print("=" * 66)
print("④ seen 能存能读")
print("=" * 66)
tmp = tempfile.mkdtemp()
try:
    path = os.path.join(tmp, "st.json")
    st5 = ag.default_state()
    f5 = l3.extract_features("你好", st5)
    l3.note_seen(st5, f5)
    l3.note_seen(st5, f5)
    io_open = open
    with io_open(path, "w", encoding="utf-8") as fh:
        json.dump(st5, fh, ensure_ascii=False)
    with io_open(path, encoding="utf-8") as fh:
        back = json.load(fh)
    check("存盘再读回，seen 还在",
          int(back["valence"][f5["exact"]]["seen"]) == 2,
          f"(seen={back['valence'][f5['exact']].get('seen')})")
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

if FAIL:
    raise SystemExit(1)
