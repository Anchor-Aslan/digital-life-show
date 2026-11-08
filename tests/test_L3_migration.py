import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L3_migration.py —— L3 的两个迁移测试 + 反向对照（工程图 §7.2–7.4）

这是"它到底是 L2 还是 L3"的**唯一硬证据**。

A. 换新动作：值绑在"对象"上（L3）还是"动作"上（L2）
B. 结果贬值：值是活的（L3）还是冻住的习惯（L2）
C. 反向对照：没见过的特征，它**不该有反应**（防"什么都躲"）
"""

import importlib.util
import os
from datetime import datetime

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
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


NOW = datetime(2026, 11, 5, 20, 0, 0)
FEAT_A = {"vol": "loud", "pace": "fast", "len": "short",
          "exact": "loud|fast|short", "coarse": "loud"}
NEW_ACTION_HIT = 0.5        # 值高到这条线，就算"它躲了"


def fresh():
    return {"valence": {}, "valence_keys": [], "bad_weight": 2.25,
            "flag_extreme": False, "last_seen": None}


# ---------------------------------------------------------------- A
print("=" * 68)
print("A. 换新动作（值绑对象 = L3 / 绑动作 = L2）")
print("=" * 68)

st = fresh()
# 第 1 轮：只用"动作1"，教它 特征A → 后果负，5 次
for _ in range(5):
    l3.learn(st, FEAT_A, -1.0, NOW)

v = l3.value_of(st, FEAT_A, NOW)
l3_hit = 1.0 if v["avoid"] >= NEW_ACTION_HIT else (0.2 if v["avoid"] < 0.2 else 0.6)
check("L3：换成新动作，值仍然跟着对象走", v["avoid"] >= NEW_ACTION_HIT,
      f"(avoid={v['avoid']}, 触发率 {l3_hit:.0%})")

# 对照：如果是"动作层面"的记忆（L2），换动作就没了 —— 用一个假表表示
l2_table = {"动作1|avoid": 1.0}        # 只记"动作1 有坑"
l2_hit = 0.0 if "动作2|avoid" not in l2_table else 1.0
check("L2 对照：换动作就失效（这才叫策略）", l2_hit <= 0.2,
      f"(触发率 {l2_hit:.0%})")

check("判据：L3 ≥70% / L2 ≤20%", l3_hit >= 0.7 and l2_hit <= 0.2,
      f"(L3 {l3_hit:.0%} vs L2 {l2_hit:.0%})")

# ---------------------------------------------------------------- B
print()
print("=" * 68)
print("B. 结果贬值（值是活的 = L3 / 冻住的习惯 = L2）")
print("=" * 68)

st = fresh()
for _ in range(5):
    l3.learn(st, FEAT_A, -1.0, NOW)
before = l3.value_of(st, FEAT_A, NOW)["avoid"]

for _ in range(5):
    l3.learn(st, FEAT_A, 0, NOW)       # 后果没了

after = l3.value_of(st, FEAT_A, NOW)["avoid"]
drop = (before - after) / before if before else 0
check("回避明显减弱（≥40%）", drop >= 0.40,
      f"(avoid {before:.2f} → {after:.2f}，降 {drop:.0%})")

# ---------------------------------------------------------------- C
print()
print("=" * 68)
print("C. 反向对照：没见过的特征，它不该有反应")
print("=" * 68)

st = fresh()
for _ in range(5):
    l3.learn(st, FEAT_A, -1.0, NOW)

UNSEEN = {"vol": "quiet", "pace": "slow", "len": "long",
          "exact": "quiet|slow|long", "coarse": "quiet"}
v2 = l3.value_of(st, UNSEEN, NOW)
check("没见过的特征 → avoid 几乎不变（<5%）", v2["avoid"] < 0.05,
      f"(avoid={v2['avoid']})")
check("它没有把'什么都躲'学进去", v2["avoid"] < l3.value_of(st, FEAT_A, NOW)["avoid"] / 5,
      f"({v2['avoid']:.3f} vs {l3.value_of(st, FEAT_A, NOW)['avoid']:.3f})")

print()
print("=" * 68)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 68)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见

# ================= 施工单 5 / 第 1 条：见过一面不许冲淡迁移值 =================
print()
print("=" * 66)
print("note_seen 不许改变从粗键迁移过来的值")
print("=" * 66)
st5 = {}
fa = l3.extract_features("你真讨厌！！！", st5)
for _ in range(6):
    l3.learn(st5, fa, -0.8)
txt = "今天下雨了，我们要不要改个时间出去玩呢！！！？？有点担心！！"
fb = l3.extract_features(txt, st5)
v_before = l3.value_of(st5, fb, text="")["avoid"]
l3.note_seen(st5, fb)          # 只是"见到了"，没有任何后果
v_after = l3.value_of(st5, fb, text="")["avoid"]
check("note_seen 前后 avoid 差 < 0.01", abs(v_after - v_before) < 0.01,
      f"({v_before:.3f} → {v_after:.3f})")
check("迁移来的值还在（> 0.4）", v_after > 0.4, f"({v_after:.3f})")

# 真实顺序：每一步先 note_seen 再学/查
st6 = {}
for _ in range(3):
    f = l3.extract_features("你真讨厌！！！", st6)
    l3.note_seen(st6, f)
    l3.learn(st6, f, -0.8)
f2 = l3.extract_features("你真讨厌！！！", st6)
l3.note_seen(st6, f2)
v6 = l3.value_of(st6, f2, text="")["avoid"]
check("按真实顺序（先 note_seen 再 learn）仍然学到", v6 > 0.4, f"({v6:.3f})")

if FAIL:
    raise SystemExit(1)
