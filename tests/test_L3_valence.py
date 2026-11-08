import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L3_valence.py —— L3 效价单元测试（照工程图 §七.1 的清单）

22 项左右。判据都在工程图里，这里只是把它们变成断言。
"""

import importlib.util
import os
from datetime import datetime, timedelta

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


def fresh():
    return {"valence": {}, "valence_keys": [], "bad_weight": 2.25,
            "flag_extreme": False, "last_seen": None}


NOW = datetime(2026, 11, 5, 20, 0, 0)

print("=" * 66)
print("① 特征·长度边界（9/10/50/51 字）")
print("=" * 66)
for n, want in ((9, "short"), (10, "normal"), (50, "normal"), (51, "long")):
    f = l3.extract_features("字" * n, {}, NOW)
    check(f"{n} 字 → {want}", f["len"] == want, f"(得到 {f['len']})")

print()
print("=" * 66)
print("② 特征·节奏边界（29/30/900/901 秒）")
print("=" * 66)
for gap, want in ((29, "fast"), (30, "normal"), (900, "normal"), (901, "slow")):
    st = {"last_seen": (NOW - timedelta(seconds=gap)).isoformat()}
    f = l3.extract_features("你好", st, NOW)
    check(f"间隔 {gap}s → {want}", f["pace"] == want, f"(得到 {f['pace']})")

print()
print("=" * 66)
print("③ 键的拼接格式")
print("=" * 66)
f = l3.extract_features("你他妈有病吧！！！", {"last_seen": (NOW - timedelta(seconds=5)).isoformat()}, NOW)
check("精确键 = 音量|节奏|长度", f["exact"].count("|") == 2, f"({f['exact']})")
check("粗键只取音量", f["coarse"] == f["vol"], f"({f['coarse']})")
check("感叹号 → loud", f["vol"] == "loud", f"(loudness 达标)")

print()
print("=" * 66)
print("④ 学习：值向 reward 靠，精确键靠得多")
print("=" * 66)
st = fresh()
f = l3.extract_features("你好！", {}, NOW)
l3.learn(st, f, -1.0, NOW)
ex = st["valence"][f["exact"]]["avoid"]
co = st["valence"][f["coarse"]]["avoid"]
check("精确键变负（avoid>0）", ex > 0, f"(avoid={ex})")
check("粗键也变负", co > 0, f"(avoid={co})")
check("精确键学得更多", ex > co, f"({ex} > {co})")

print()
print("=" * 66)
print("⑤ 粗键比精确键慢（同样次数，变化量更小）")
print("=" * 66)
st = fresh()
for _ in range(5):
    l3.learn(st, f, -0.5, NOW)
check("5 次之后仍是 精确 > 粗",
      st["valence"][f["exact"]]["avoid"] > st["valence"][f["coarse"]]["avoid"],
      f"({st['valence'][f['exact']]['avoid']:.3f} > {st['valence'][f['coarse']]['avoid']:.3f})")

print()
print("=" * 66)
print("⑥ 空表 → 返回出厂值")
print("=" * 66)
st = fresh()
val = l3.value_of(st, l3.extract_features("你好", {}, NOW), NOW)
check("没学过也有值（出厂）", val["avoid"] >= 0.0 and "hits" in val, f"(avoid={val['avoid']}, 命中 {val['matched']})")

print()
print("=" * 66)
print("⑦ 低于 θ 不提")
print("=" * 66)
st = fresh()
st["valence"]["loud|fast|short"] = {"approach": 0.0, "avoid": 0.5, "r": 0.01,
                                    "last_touch": NOW.isoformat()}
r = l3.retrieve(st, l3.extract_features("你好", {}, NOW), NOW)
check("r 太低 → 想不起来", r["matched"] == 0, f"(命中 {r['matched']})")

print()
print("=" * 66)
print("⑧ 部分匹配：差一轴打 0.7")
print("=" * 66)
check("全中 = 1.0", l3._match("quiet|normal|short", {"vol": "quiet", "pace": "normal", "len": "short", "coarse": "quiet"}) == 1.0)
check("差一轴 = 0.7", l3._match("quiet|fast|short", {"vol": "quiet", "pace": "normal", "len": "short", "coarse": "quiet"}) == 0.7)
check("差两轴 = 0.49", l3._match("quiet|fast|long", {"vol": "quiet", "pace": "normal", "len": "short", "coarse": "quiet"}) == 0.49)

print()
print("=" * 66)
print("⑨ r 衰减：72 小时后减半")
print("=" * 66)
e = {"r": 0.8, "last_touch": NOW.isoformat()}
check("刚用过 = 0.8", abs(l3._r_decayed(e, NOW) - 0.8) < 1e-6)
check("72 小时后 ≈ 0.4", abs(l3._r_decayed(e, NOW + timedelta(hours=72)) - 0.4) < 0.01,
      f"({l3._r_decayed(e, NOW + timedelta(hours=72)):.3f})")

print()
print("=" * 66)
print("⑩ top-k 不超过 4")
print("=" * 66)
st = fresh()
for i in range(10):
    st["valence"][f"loud|{'fast' if i%2 else 'normal'}|{'short' if i%3 else 'long'}"] = {
        "approach": 0.0, "avoid": 0.9, "r": 1.0, "last_touch": NOW.isoformat()}
r = l3.retrieve(st, l3.extract_features("你好！", {}, NOW), NOW)
check("最多回 4 条", len(r["hits"]) <= l3.TOP_K, f"({len(r['hits'])} 条)")

print()
print("=" * 66)
print("⑪ 值不变，只有 r 变（关键：这就是「好了但一听那首歌又崩了」）")
print("=" * 66)
st = fresh()
f = l3.extract_features("你好！", {}, NOW)
l3.learn(st, f, -1.0, NOW)
avoid_before = st["valence"][f["exact"]]["avoid"]
r_later = l3._r_decayed(st["valence"][f["exact"]], NOW + timedelta(hours=240))
check("值没变小", abs(st["valence"][f["exact"]]["avoid"] - avoid_before) < 1e-9)
check("r 降了很多", r_later < 0.2, f"(r={r_later:.3f})")

print()
print("=" * 66)
print("⑫ 负面偏差：坏比好重（2.25），且 clamp 到 -1")
print("=" * 66)
check("负 reward 被放大", l3._apply_bad_weight(-0.3) < -0.3, f"({l3._apply_bad_weight(-0.3):.3f})")
check("正的 reward 不放", l3._apply_bad_weight(0.3) == 0.3)
check("放大后仍然 clamp 在 -1", l3._apply_bad_weight(-1.0) == -1.0)

print()
print("=" * 66)
print("⑬ 三段区间：出厂落正常区、越界要报错")
print("=" * 66)
st = fresh()
ok_sys = l3.set_bad_weight(st, 2.0, by="system")
check("system 写常态区可以", ok_sys == 2.0)
try:
    l3.set_bad_weight(st, 4.5, by="system")
    check("system 写极端区应报错", False)
except ValueError:
    check("system 写极端区报错", True)
ok_p = l3.set_bad_weight(st, 4.5, by="persona")
check("persona 写极端区可以", ok_p == 4.5)
l3.set_bad_weight(st, 8.0, by="explicit")
check("explicit 写病理区并留痕", st["flag_extreme"] is True and st["bad_weight"] == 8.0)

print()
print("=" * 66)
print("⑭ 出厂抽样 1000 个：全在正常区、均值不偏、无病理标记")
print("=" * 66)
vals = [l3.sample_bad_weight(seed=i) for i in range(1000)]
lo, hi = l3.BAD_WEIGHT_NORMAL
check("100% 落在正常区", all(lo <= v <= hi for v in vals))
check("均值 ≈ 2.25", abs(sum(vals) / len(vals) - 2.25) < 0.15, f"(均值 {sum(vals)/len(vals):.3f})")
check("没有病理样本", all(v >= 1.0 for v in vals))

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# ================= ⑮ 接线：值高到线，L1 会收紧（而 L3 自己不写参数） =================
print()
print("=" * 66)
print("⑮ L1 接住了 L3 的值（L1 仍是唯一写入者）")
print("=" * 66)
l1 = load("l1_reflex")
st = fresh()
f = l3.extract_features("你好！", {}, NOW)
for _ in range(8):
    l3.learn(st, f, -1.0, NOW)
val = l3.value_of(st, f, NOW)
check("值够高（≥0.6）", val["avoid"] >= l3.__dict__.get("VALENCE_TIGHTEN", 0.6) or val["avoid"] >= 0.6,
      f"(avoid={val['avoid']})")

p_low, _ = l1.reflex(st, {"valence_avoid": 0.1})
p_high, ap = l1.reflex(st, {"valence_avoid": val["avoid"]})
check("值低 → 不动", p_low["max_tokens"] == 800, f"({p_low['max_tokens']})")
check("值高 → 收紧", p_high["max_tokens"] < 800, f"({p_high['max_tokens']})")
check("收紧记进了 applied", any(a.get("channel") == "valence" for a in ap))
check("L3 自己没写参数", "max_tokens" not in open(os.path.join(BASE, "l3_valence.py"), encoding="utf-8").read().split("不做")[0])
# ================= ⑯ 总唤醒（Y 轴）：空 / 半 / 满 / 关着的通道 =================
print()
print("=" * 66)
print("⑯ 总唤醒 arousal_axis（0=昏迷，1=极度激动）")
print("=" * 66)
check("全空 → 只有基础唤醒 0.15", abs(l3.arousal_axis({}, {}, {"acute": 0.0}) - 0.15) < 0.01)
check("吵架（痛0.5+憋0.6+压力0.6）≈0.68", abs(l3.arousal_axis({}, {"pain": 0.5, "breath": 0.6}, {"acute": 0.6}) - 0.68) < 0.03,
      f"({l3.arousal_axis({}, {'pain': 0.5, 'breath': 0.6}, {'acute': 0.6})})")
check("全满 → 封顶 1.0", l3.arousal_axis({}, {"pain": 1.0, "breath": 1.0, "arousal": 1.0}, {"acute": 1.0}) == 1.0)
check("关着的通道不算 0（None 跳过）",
      abs(l3.arousal_axis({}, {"pain": None, "breath": 0.0}, {"acute": 0.0}) - 0.15) < 0.01)
check("不加 fatigue（累不是激活）", "fatigue" not in l3.AROUSAL_SOURCES)

print()
print("=" * 66)
print("⑰ approach 真的接进 L1 了（想要够高 → 松）")
print("=" * 66)
l1b = load("l1_reflex")
p_lo, _ = l1b.reflex({}, {"valence_approach": 0.05})
p_hi, ap_hi = l1b.reflex({}, {"valence_approach": 0.40})
check("不想要 → 不动", p_lo["max_tokens"] == 800, f"({p_lo['max_tokens']})")
check("够想要 → 放松（更长更热）", p_hi["max_tokens"] > 800 and p_hi["temperature"] > 0.7,
      f"({p_hi['max_tokens']}, {p_hi['temperature']})")
check("记进了 applied", any(a.get("kind") == "approach" for a in ap_hi))
# ================= ⑱ 身体读数 → 当下两条轴（不进键）=================
print()
print("=" * 66)
print("⑱ body_pull：此刻的身体把当下的值抬高")
print("=" * 66)
b = l3.body_pull({"pain": 0.6, "breath": 0.5})
check("痛 0.6 + 憋 0.5 → avoid 抬高 0.50（0.30+0.20）", abs(b["avoid"] - 0.50) < 0.01, f"({b})")
check("痛单独 0.6 → 0.30", abs(l3.body_pull({"pain": 0.6})["avoid"] - 0.30) < 0.01)
b2 = l3.body_pull({"arousal": 1.0})
check("性唤起 1.0 → approach 抬高 0.50", abs(b2["approach"] - 0.50) < 0.01, f"({b2})")
b3 = l3.body_pull({"pain": None, "breath": 0.0})
check("关着的通道跳过（None 不当 0）", b3["avoid"] == 0.0, f"({b3})")

print()
print("=" * 66)
print("⑲ conflict / effort / controllable / precision")
print("=" * 66)
check("又想要又怕 → conflict 0.7", l3.conflict_of(0.7, 0.7) == 0.7)
check("只有一边 → conflict 0", l3.conflict_of(0.7, 0.0) == 0.0)

st_hi = {"fatigue_pool": {"value": 1.0}, "last_latency_ms": 5000}
st_lo = {"fatigue_pool": {"value": 0.0}, "last_latency_ms": 200}
check("累+慢 → effort 高（新公式：延迟0.6+桶0.133）", l3.effort_of(st_hi) > 0.7, f"({l3.effort_of(st_hi)})")
check("轻松+快 → effort 低", l3.effort_of(st_lo) < 0.2, f"({l3.effort_of(st_lo)})")

st_c = {"trace": [{"ownership": {"parts": {"act": {"act": 1.0}}}}] * 4}
check("意图全对得上 → control_sense 1.0", l3.control_sense(st_c) == 1.0)
check("没有可核的轮次 → 0.5（还没结论，不是 0）", l3.control_sense({"trace": []}) == 0.5)

pr = l3.precision_of(st_c)
check("precision 分两层：亲历有值", pr["episodic"] is not None, f"({pr})")
check("precision 语言层恒 0（判语义要 L4，没编）", pr["semantic"] == 0.0)

print()
print("=" * 66)
print("⑳ value_of 汇总：坐标齐不齐")
print("=" * 66)
st_v = fresh()
st_v["last_readings"] = {"pain": 0.5}
st_v["trace"] = [{"ownership": {"parts": {"act": {"act": 1.0}}}}] * 3
v = l3.value_of(st_v, f, NOW)
need = ("approach", "avoid", "arousal", "conflict", "effort", "control_sense", "precision")
check("七样坐标都在", all(k in v for k in need), f"(缺 {[k for k in need if k not in v]})")
check("痛的时候 avoid 被抬高", v["avoid"] > 0.0, f"(avoid={v['avoid']})")

# ================= 最终总计（前面的小计是半路打印的，这里是全部）=================
print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

check("出厂（体力桶空、读数正常）→ 累不贡献想躲",
      l3.body_pull({"fatigue": 1.0}, {"fatigue_pool": {"value": 0.0}})["avoid"] == 0.0)
check("桶积满 → 累贡献 0.30",
      abs(l3.body_pull({}, {"fatigue_pool": {"value": 1.0}})["avoid"] - 0.30) < 0.01)


print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
print("=" * 66)

# ================= ㉑ 恶心：两个可分离的指标（11-07 定）=================
print()
print("=" * 66)
print("㉑ 恶心分两个指标：生理 / 语义（能同时在场、能反向）")
print("=" * 66)
d0 = l3.disgust_pull("今天天气不错，我们去吃饭吧。", None)
check("干净 → 生理 0", d0["physio"] == 0.0, f"({d0})")
d1 = l3.disgust_pull("在吗", [{"source": "user", "content": "在吗"}] * 5)
check("刷屏 → 生理 0.4", d1["physio"] >= 0.4, f"({d1['physio']})")
check("恶心同时动三条：躲开↑ 靠近↓ 绷紧↑",
      d1["avoid"] > 0 and d1["approach"] < 0 and d1["arousal"] > 0,
      f"(躲{d1['avoid']} 近{d1['approach']} 绷{d1['arousal']})")
check("语义那一半现在是 None（没编）", d0["semantic"] is None)

d2 = l3.disgust_pull("啊" * 20, None, semantic=0.0)
check("可分离：生理高 + 语义 0 → 两分量各自可读",
      d2["physio"] > 0 and d2["semantic"] == 0.0, f"(physio={d2['physio']}, semantic={d2['semantic']})")
check("轮廓照样出（躲开但不算被这个评价压住）", d2["avoid"] > 0, f"(躲{d2['avoid']})")

# ================= 22 频率保真：正常人不该动不动就恶心（11-07）=================
print()
print("=" * 66)
print("22 信息卫生的门槛：正常人几乎不触发")
print("=" * 66)
check("5 个「啊」→ 0（撒娇，不是恶心）", l3.hygiene_score("啊啊啊啊啊", None) == 0.0)
check("20 个「啊」→ 才 0.3", l3.hygiene_score("啊" * 20, None) == 0.3)
check("连发两句「在吗」→ 0（条数不够）",
      l3.hygiene_score("在吗", [{"source": "user", "content": "在吗"}] * 2) == 0.0)
check("5 条里 4 条一样 → 0.4（真刷屏）",
      l3.hygiene_score("在吗", [{"source": "user", "content": "在吗"}] * 4
                       + [{"source": "user", "content": "嗯"}]) == 0.4)
check("600 字正常长文（有标点）→ 0",
      l3.hygiene_score("今天天气不错，" * 100, None) == 0.0)
check("900 字一个标点没有 → 有分", l3.hygiene_score("啊" * 900, None) > 0)

print()
print("=" * 66)
print("23 敏感度：三段区间（出厂只落常态）")
print("=" * 66)
st_s = {"hygiene_sensitivity": 1.0, "flag_extreme": False}
check("system 写常态区可以", l3.set_hygiene_sensitivity(st_s, 1.2, by="system") == 1.2)
try:
    l3.set_hygiene_sensitivity(st_s, 2.5, by="system")
    check("system 写极端区应报错", False)
except ValueError:
    check("system 写极端区报错", True)
check("persona 写极端区可以", l3.set_hygiene_sensitivity(st_s, 2.5, by="persona") == 2.5)
l3.set_hygiene_sensitivity(st_s, 0.3, by="explicit")
check("explicit 写病理区并留痕",
      st_s["flag_extreme"] is True and st_s["hygiene_sensitivity"] == 0.3)
check("敏感度高（迟钝）→ 同样输入分更低",
      l3.hygiene_score("啊" * 20, None, 2.0) < l3.hygiene_score("啊" * 20, None, 1.0))


print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
