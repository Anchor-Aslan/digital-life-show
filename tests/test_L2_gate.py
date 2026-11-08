import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L2_gate.py —— 写入闸门（拒绝权 + 意志加权）

判据：
  ① 自己写流水 → 直接过（R 低）
  ② 自己写核心（identity）→ 过不了，必须走维护流程
  ③ 上层想改 learned（R=0.5）但意志弱（W=0.3）→ 拒绝
  ④ 上层意志强（W=0.9）→ 放行，但付代价（记 wound + 留痕）
  ⑤ 上层想改 identity（R=1.0）→ 永远拒绝（越核心越压不动）
  ⑥ 反复覆盖 → 伤口累积 → 痛上升
  ⑦ 接口形状固定：上层只传一个 intention 就能接
"""

import importlib.util
import os

BASE = SRC_DIR


def load(n):
    spec = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l2 = load("l2_ownership")
l0 = load("l0_sense")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


def fresh():
    return {"trace": [], "messages": [], "wounds": [], "sens": {},
            "identity": {"gender": None, "traits": {}}, "learned": {}}


print("=" * 62)
print("① 自己写流水 → 直接过")
print("=" * 62)
st = fresh()
v = l2.accept_write(st, "trace", [1, 2, 3], by="self")
check("trace 放行", v["ok"], f"(R={v['R']}, {v['why']})")

print()
print("=" * 62)
print("② 自己写核心 → 必须走维护流程")
print("=" * 62)
v2 = l2.accept_write(st, "identity", {"gender": "male"}, by="self")
check("identity 被挡", not v2["ok"], f"({v2['why']})")
v2b = l2.accept_write(st, "identity", {"gender": "male"}, by="maintain")
check("维护流程可以写", v2b["ok"], f"({v2b['why']})")

print()
print("=" * 62)
print("③ 上层意志弱 → 改不动 learned")
print("=" * 62)
v3 = l2.accept_write(st, "learned", {}, intention={"weight": 0.30, "who": "L4", "reason": "想清空老毛病"})
check("拒绝", not v3["ok"], f"(R={v3['R']} W=0.30 → {v3['why']})")

print()
print("=" * 62)
print("④ 上层意志强 → 放行，但付费")
print("=" * 62)
before_wounds = len(st["wounds"])
v4 = l2.accept_write(st, "learned", {}, intention={"weight": 0.90, "who": "L4", "reason": "重要"})
check("放行", v4["ok"], f"(suppressed={v4['suppressed']}, {v4['why']})")
check("记了伤口（代价）", len(st["wounds"]) > before_wounds,
      f"(+{len(st['wounds']) - before_wounds} 个，代价 {v4['cost']})")
check("留了痕", any(r["key"] == "learned" for r in st["write_log"]))

print()
print("=" * 62)
print("⑤ 改 identity：给多大意志都不行")
print("=" * 62)
v5 = l2.accept_write(st, "identity", {}, intention={"weight": 1.0, "who": "L4"})
check("永远拒绝", not v5["ok"], f"(R=1.0, suppressed={v5['suppressed']})")

print()
print("=" * 62)
print("⑥ 反复覆盖 → 伤口累积 → 痛上升")
print("=" * 62)
st2 = fresh()
p0 = l0.pain(st2)
for _ in range(4):
    l2.accept_write(st2, "learned", {}, intention={"weight": 0.9, "who": "L4"})
    l0.pain(st2)
p1 = l0.pain(st2)
check("越覆盖越疼", p1 > p0, f"({p0:.2f} → {p1:.2f})")
check("敏感度升了", l0.sens_of(st2, "self_override") > 1.0,
      f"({l0.sens_of(st2,'self_override'):.2f})")

print()
print("=" * 62)
print("⑦ 上层接入只需要一行")
print("=" * 62)
st3 = fresh()
v7 = l2.write(st3, "learned", {"api_error": {"count": 9}},
              intention={"weight": 0.9, "who": "L4", "reason": "测试接口"})
check("write() 一个函数搞定", v7["ok"] and st3["learned"].get("api_error", {}).get("count") == 9,
      f"({v7['why']})")

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
