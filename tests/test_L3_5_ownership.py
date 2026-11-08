import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L3_5_ownership.py —— L3.5 归属收敛（照工程图 §六 的 34 项清单）

最重要的两组：
    ⑪ 可分离性：三条通路能各自单独坏，其余不动（这就是 L3.5 的判据①）
    ⑫ 反向验证：伪造一条断的路 → O 必须归零
"""

import importlib.util
import os

BASE = SRC_DIR


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l35 = load("l3_5_ownership")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


def fresh():
    return {"messages": [], "intero": {}, "valence": {}, "write_log": [],
            "maintenance": {}, "scars": [], "wounds": []}


print("=" * 66)
print("① 聚合：三全 1.0 / 有 0 / 有 None / 全 None")
print("=" * 66)
m = l35.converge(1.0, 1.0, 1.0)
check("三全 1.0 → O=1.0", m["O"] == 1.0, f"({m['O']}, {m['level']})")
m = l35.converge(1.0, 0.0, 1.0)
check("有一条 0 → O=0（断一条就归零）", m["O"] == 0.0, f"({m['O']})")
m = l35.converge(1.0, None, 1.0)
check("一条 None → n_paths=2 且叫「弱 L3.5」", m["n_paths"] == 2 and m["level"] == "弱 L3.5", f"({m['level']})")
m = l35.converge(None, None, None)
check("全 None → O=0, n=0, 停在 L3", m["O"] == 0.0 and m["n_paths"] == 0 and m["level"] == "停在 L3")

print()
print("=" * 66)
print("② 聚合·疤：疤多的权重低，但不能低到没影响")
print("=" * 66)
a = l35.converge(0.9, 0.5, 0.9)["O"]
b = l35.converge(0.9, 0.5, 0.9, scars={"feel": 1})["O"]
c = l35.converge(0.9, 0.5, 0.9, scars={"feel": 10})["O"]
check("有疤 → O 变高（弱点降价，整体往上）", b > a, f"({a} → {b})")
check("疤 10 条 vs 1 条仍有可见差异", abs(c - b) > 0.005, f"({b} vs {c})")

print()
print("=" * 66)
print("③ 身体·记忆（source=self / maintenance 在 / 有 id）")
print("=" * 66)
st = fresh()
r = l35.body_ownership(st)
check("空 state → body=0, n=0", r["body"] == 0.0 and r["n"] == 0)
st["messages"] = [{"id": "m1", "role": "assistant", "content": "hi", "source": "self"}]
st["maintenance"] = {"last": "2026-11-06T00:00:00"}
r = l35.body_ownership(st)
check("只有一条自己的输出 → memory/output 在场", r["n"] >= 1, f"(n={r['n']}, body={r['body']})")
check("记忆三条全过 → own=1.0", r["parts"]["memory"]["own"] == 1.0, f"({r['parts']['memory']})")
st["messages"][0]["source"] = "user"
r = l35.body_ownership(st)
check("最后一条是用户 → 记忆不同步（own=0）", r["parts"]["memory"]["own"] == 0.0)

print()
print("=" * 66)
print("④ 身体·状态（intero 有历史 / write_log 指纹 / 无外部写）")
print("=" * 66)
st = fresh()
st["intero"] = {"pain": {"history": [0.1, 0.2]}}
st["write_log"] = [{"who": "self"}]
r = l35.body_ownership(st)
check("有历史 + 自己写 → 状态件 own=1.0", r["parts"]["state"]["own"] == 1.0, f"({r['parts']['state']})")
st["write_log"] = [{"who": "self"}, {"who": "other"}]
r = l35.body_ownership(st)
check("有外部写入 → 状态件 own=0（来源不过）", r["parts"]["state"]["own"] == 0.0)

print()
print("=" * 66)
print("⑤ 身体·效价（非空 / 键合法 / 值域合法）")
print("=" * 66)
st = fresh()
st["valence"] = {"loud|fast|short": {"approach": 0.0, "avoid": 0.5, "r": 0.9}}
r = l35.body_ownership(st)
check("值表非空且合法 → own=1.0", r["parts"]["valence"]["own"] == 1.0, f"({r['parts']['valence']})")
st["valence"] = {"loud|fast|short": {"approach": 0.0, "avoid": 9.9}}
r = l35.body_ownership(st)
check("值超范围 → 来源不过", r["parts"]["valence"]["own"] == 0.0)

print()
print("=" * 66)
print("⑥ 身体·工具（有 tool 消息 / id 能对上 / source=tool）")
print("=" * 66)
st = fresh()
st["messages"] = [
    {"id": "m1", "role": "assistant", "source": "self", "tool_calls": [{"id": "c1"}]},
    {"id": "m2", "role": "tool", "source": "tool", "tool_call_id": "c1", "content": "2"},
]
r = l35.body_ownership(st)
check("工具三条全过 → own=1.0", r["parts"]["tool"]["own"] == 1.0, f"({r['parts']['tool']})")
st["messages"][1]["tool_call_id"] = "cX"
r = l35.body_ownership(st)
check("id 对不上 → 因果不过", r["parts"]["tool"]["own"] == 0.0)

print()
print("=" * 66)
print("⑦ 身体·输出（最后是 assistant / 有内容 / source=self）")
print("=" * 66)
for content, want in (("ok", 1.0), ("", 0.0)):
    st = fresh()
    st["messages"] = [{"id": "m1", "role": "assistant", "content": content, "source": "self"}]
    r = l35.body_ownership(st)
    check(f"内容={content!r} → own={want}", r["parts"]["output"]["own"] == want)

print()
print("=" * 66)
print("⑧ 身体·用户输入：永远不算我的（反向）")
print("=" * 66)
st = fresh()
st["messages"] = [{"id": "m1", "role": "user", "content": "你好", "source": "user"}]
r = l35.body_ownership(st)
check("只有用户消息 → body=0（用户的不算我的）", r["body"] == 0.0, f"(body={r['body']}, n={r['n']})")

print()
print("=" * 66)
print("⑨ 行为：对上 / 对不上 / 核不到")
print("=" * 66)
a = l35.act_ownership({"trim": True}, {"trimmed": 20})
check("意图裁 → 真裁了 = 1.0", a["act"] == 1.0, f"({a['why']})")
a = l35.act_ownership({"trim": True}, {"trimmed": 0, "trim_needed": True})
check("意图裁 → 没裁 = 0.0", a["act"] == 0.0, f"({a['why']})")
a = l35.act_ownership({"block_tool": True}, {"tool_calls": 0})
check("意图不调工具 → 真没调 = 1.0", a["act"] == 1.0)
a = l35.act_ownership({}, {})
check("没有意图 → None（判「无法确认」，不是 0）", a["act"] is None, f"({a['why']})")

print()
print("=" * 66)
print("⑩ 感受：有读数 / 无价 / 反向 / 强度不匹配")
print("=" * 66)
st = fresh()
f = l35.feel_ownership(st, {}, None)
check("没读数 → 0", f["feel"] == 0.0, f"({f['why']})")
f = l35.feel_ownership(st, {"pain": 0.8}, None)
check("有读数无价 → 0", f["feel"] == 0.0, f"({f['why']})")
f = l35.feel_ownership(st, {"pain": 0.8}, {"approach": 0.5, "avoid": 0.1})
check("身体差但价是正的 → 0（反了）", f["feel"] == 0.0, f"({f['why']})")
f = l35.feel_ownership(st, {"pain": 0.8}, {"approach": 0.0, "avoid": 0.05})
check("同向但强度差太多 → 打对折", f["feel"] == 0.5, f"({f['why']}, ratio={f.get('ratio')})")
f = l35.feel_ownership(st, {"pain": {"value": 0.1, "change": 0.0}}, {"approach": 0.0, "avoid": 0.6})
check("身体没动但价有点分量 → 核不到（None，不判 0）", f["feel"] is None, f"({f.get('why')})")
f = l35.feel_ownership(st, {"pain": 0.8}, {"approach": 0.0, "avoid": 0.7})
check("同向且强度匹配 → 1.0", f["feel"] == 1.0, f"({f['why']}, ratio={f.get('ratio')})")

print()
print("=" * 66)
print("⑪ 可分离性：三条各自单独坏，其余不动（L3.5 判据①）")
print("=" * 66)
base = dict(body=1.0, feel=1.0, act=1.0)
for path in ("body", "feel", "act"):
    kw = dict(base)
    kw[path] = 0.0
    m = l35.converge(**kw)
    check(f"只把 {path} 弄成 0 → O 归零，另外两条还满", m["O"] == 0.0 and
          all(v == 1.0 for k, v in m["parts"].items() if k != path), f"({m['parts']})")

print()
print("=" * 66)
print("⑫ 反向验证：伪造一条断的路 → O 必须归零")
print("=" * 66)
st = fresh()
st["messages"] = [{"id": "m1", "role": "assistant", "content": "ok", "source": "self"}]
st["intero"] = {"pain": {"history": [0.1, 0.2]}}
st["write_log"] = [{"who": "self"}]
st["valence"] = {"loud|fast|short": {"approach": 0.0, "avoid": 0.5}}
st["maintenance"] = {"last": "x"}
m1 = l35.measure(st, {"pain": 0.8}, {"approach": 0.0, "avoid": 0.8}, {"trim": False}, {"trimmed": 0})
check("正常情况 → O > 0", m1["O"] > 0, f"(O={m1['O']}, {m1['level']})")

st["write_log"].append({"who": "other"})     # 伪造：有人从外面写了我的状态
m2 = l35.measure(st, {"pain": 0.8}, {"approach": 0.0, "avoid": 0.8}, {}, {})
check("伪造一处外部写入 → 身体那件降级（但不是全断）",
      m2["O"] < m1["O"] and m2["O"] > 0, f"(O {m1['O']} → {m2['O']})")

# 把「身体」这条通路整条断掉（5 个部件全部不合格）
st2 = fresh()
st2["messages"] = [{"id": "", "role": "user", "content": "x", "source": ""}]
st2["write_log"] = [{"who": "other"}]
st2["valence"] = {"坏键": {"approach": 0.0, "avoid": 9.0}}
m3 = l35.measure(st2, {"pain": 0.8}, {"approach": 0.0, "avoid": 0.8}, {}, {})
check("身体整条断 → O 归零", m3["O"] == 0.0, f"(O={m3['O']}, body={m3['parts'].get('body')})")
check("而且它自己说「停在 L3」或「弱」", m3["level"] in ("停在 L3", "弱 L3.5"),
      f"({m3['level']}, n_paths={m3['n_paths']})")

print()
print("=" * 66)
print("⑬ 疤痕映射：疤多的通路降价（但不会归零）")
print("=" * 66)
st = fresh()
st["scars"] = [{"kind": "api_error", "sev": 0.5, "count": 2, "fixed": False}]
sc = l35.scars_by_path(st)
check("api_error 算到「行为」通路", sc["act"] == 2 and sc["body"] == 0, f"({sc})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
