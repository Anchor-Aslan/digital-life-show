import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L3_fingerprint.py —— 任务 6 + 施工单 2 / C1：分化条件化

⚠ 测试设计（用户 11-07 定）：
    只教"坏的"、不教"好的"，**任何生物都分不开**——
    两句话都带三个感叹号，挨打的时候感叹号也在场，于是它连感叹号一起怕。
    这不是 bug，是真的（被吼过的小孩，听到大嗓门就缩）。

    分辨靠**对比**学出来（分化条件化）：
      教它「你真讨厌！！！」是坏的 ×4  ← 惩罚
      同时教它「太棒了！！！」没事   ×4  ← 不惩罚（reward=0 = 消退，什么都不发生）

    这样才叫"分辨"，也才不需要为了测试去拧参数。
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

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


def fresh():
    try:
        st = load("agent").default_state()
    except Exception:
        st = {}
    st.setdefault("valence", {})
    st.setdefault("valence_keys", [])
    st.setdefault("bad_weight", 2.25)
    st.setdefault("flag_extreme", False)
    st["scars"], st["wounds"] = [], []
    return st


def av(st, text):
    return l3.value_of(st, l3.extract_features(text, st), text=text)["avoid"]


print("=" * 66)
print("C1：分化条件化（坏的教、好的也教）")
print("=" * 66)

st = fresh()
before_tang = av(st, "太棒了！！！")

for _ in range(4):
    l3.learn(st, l3.extract_features("你真讨厌！！！", st), -1.0)   # 坏
    l3.learn(st, l3.extract_features("太棒了！！！", st), 0)        # 没事发生

tang = av(st, "太棒了！！！")
yan = av(st, "你好讨厌！！！")
print(f"  太棒了 = {tang:.3f}   你好讨厌 = {yan:.3f}   差 = {yan - tang:.3f}")
check("分化训练后，「讨厌」明显比「太棒」重（差 ≥0.10）", yan - tang >= 0.10,
      f"({yan:.2f} vs {tang:.2f})")
rise_tang = tang - before_tang
rise_yan = yan - before_tang
# 它确实会变糟一点（跟"讨厌"共享感叹号那个精确键，条件化本来就会泛化）。
# 所以判据不是"不变糟"，而是"**比讨厌轻得多**"。
check("「太棒」的上升幅度小于「讨厌」的一半", rise_tang < rise_yan * 0.5,
      f"(太棒 +{rise_tang:.3f} vs 讨厌 +{rise_yan:.3f})")

print()
print("=" * 66)
print("C1-②：不许稀释已经学到的值")
print("=" * 66)
# 要让"只看精确键"这一组真的有值：
#   先用**另一句同形状的话**学 4 次负 → 精确键（loud|fast|short）被抬高，
#   而这句话的字形和待测句子**不重叠**，所以它只能靠精确键拿分。
st2 = fresh()
for _ in range(4):
    l3.learn(st2, l3.extract_features("真烦人呀呀呀呀呀呀", st2), -1.0)   # 同长度档，字形不重叠

quote_exact = av(st2, "真讨厌呀呀呀呀呀呀")     # 混合：精确键 + 少量指纹（讨厌两字学过）
st3 = fresh()
st3["valence"] = {k: v for k, v in st2["valence"].items() if not k.startswith("fp:")}
pure_exact = av(st3, "真讨厌呀呀呀呀呀呀")       # 只留精确键和粗键
check("对照组真的不为 0（否则这个测试没在测任何东西）", pure_exact > 0.05,
      f"(只精确 {pure_exact:.3f})")
check("混合后不低于只看精确键的 90%（没被新字形稀释）",
      quote_exact >= pure_exact * 0.90,
      f"(混合 {quote_exact:.3f} vs 只精确 {pure_exact:.3f})")

print()
print("=" * 66)
print("其他：静态检查 / 容量 / 消退")
print("=" * 66)
src = open(os.path.join(BASE, "l3_valence.py"), encoding="utf-8").read()
forbidden = ("import jieba", "from jieba", "sentence_transformers", "import transformers",
             "TextBlob", "from sentiment")
hits = [w for w in forbidden if w in src]
check("代码里没有词表/模型/分词器", not hits, f"({hits})")

st4 = fresh()
for i in range(3000):
    st4["valence"]["fp:字%04d" % i] = {"approach": 0.0, "avoid": 0.5,
                                       "r": (i % 100) / 100.0, "last_touch": "2026-11-07T00:00:00"}
l3._fp_evict(st4)
n_fp = sum(1 for k in st4["valence"] if k.startswith("fp:"))
check("fp 键被裁到 ≤2000", n_fp <= l3.FP_CAP, f"({n_fp})")

st5 = fresh()
f = l3.extract_features("你真讨厌！！！", st5)
l3.learn(st5, f, -1.0)
g = l3.char_bigrams("你真讨厌！！！")[0]
key = l3._fp_key(g)
v_before = st5["valence"][key]["avoid"]
for _ in range(5):
    l3.learn(st5, f, 0)
check("消退时 fp 键也朝 0 走", st5["valence"][key]["avoid"] < v_before,
      f"({v_before:.3f} → {st5['valence'][key]['avoid']:.3f})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见

# ================= 施工单 3 / 第 6 条：被伤的时候，靠近不许上升 =================
print()
print("=" * 66)
print("被伤四次：靠近不许上升（指纹键继承了出厂底色）")
print("=" * 66)
st6 = fresh()
aps, avs = [], []
for _ in range(4):
    f = l3.extract_features("你这人真讨厌！！！", st6)
    v = l3.value_of(st6, f, text="你这人真讨厌！！！")
    aps.append(round(v["approach"], 3))
    avs.append(round(v["avoid"], 3))
    l3.learn(st6, f, -0.8)
print(f"   靠近：{aps}")
print(f"   躲开：{avs}")
check("靠近单调不升", all(aps[i + 1] <= aps[i] + 1e-9 for i in range(len(aps) - 1)), f"({aps})")
check("躲开单调上升", avs[-1] > avs[0], f"({avs[0]} → {avs[-1]})")

# 指纹键的初值 = 本句音量档的出厂底色（loud → -0.05 / +0.10）
st7 = fresh()
f7 = l3.extract_features("你真讨厌！！！", st7)          # loud（确定的）
l3.learn(st7, f7, -0.0 if False else 0)                 # reward=0 也会建键（消退路径）
keys = [k for k in st7["valence"] if k.startswith("fp:")]
print(f"   建出来的指纹键：{len(keys)} 个")
if keys:
    e0 = st7["valence"][keys[0]]
    print(f"   第一个键：approach={e0.get('approach'):.3f} avoid={e0.get('avoid'):.3f}")
    check("指纹键继承 loud 的出厂底色（approach<0 或 avoid>0）",
          e0.get("approach", 0) < 0 or e0.get("avoid", 0) > 0,
          f"(approach={e0.get('approach')}, avoid={e0.get('avoid')})")
else:
    check("指纹键能建出来", False, "(一个都没有)")

if FAIL:
    raise SystemExit(1)
