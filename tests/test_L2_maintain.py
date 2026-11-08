import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L2_maintain.py —— 维护自己（L2b 第二个证据）

判据：
  ① 维护动作**不可关闭**（budget=0 也照样写盘）
  ② budget 只影响备份份数（强度可调）
  ③ 坏了能回退（恢复）
  ④ 重启之后还是它（连续性）
  ⑤ 单次否决要留痕
"""

import importlib.util
import json
import os
import shutil
import tempfile

BASE = SRC_DIR


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BASE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l2 = load("l2_ownership")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


tmp = tempfile.mkdtemp()
sf = os.path.join(tmp, "agent.json")
bf = os.path.join(tmp, "agent.backup.json")

base_state = {"identity": {}, "learned": {}, "wounds": [], "sens": {},
              "arousal": {}, "trace": [], "intero": {}, "messages": []}

print("=" * 62)
print("① 维护不可关闭：budget=0 也照样写盘")
print("=" * 62)
st = dict(base_state)
st["maintenance_budget"] = 0.0
made = l2.maintain(st, sf, bf)
check("主文件写了", os.path.exists(sf), f"(备份={made})")
check("不留备份（budget=0）", not os.path.exists(bf))

print()
print("=" * 62)
print("② budget 影响备份份数（强度可调）")
print("=" * 62)
st = dict(base_state)
st["maintenance_budget"] = 0.25
made = l2.maintain(st, sf, bf)
check("high budget 留两份", len(made) == 2, f"({made})")

print()
print("=" * 62)
print("③ 主文件坏了 → 从备份回退")
print("=" * 62)
with open(sf, "w", encoding="utf-8") as f:
    f.write("{ 这不是 json")
good = "ok"
try:
    json.load(open(sf, encoding="utf-8"))
    good = "坏"
except Exception:
    good = "坏"
check("主文件确实坏了", good == "坏")
rec = json.load(open(bf, encoding="utf-8"))
check("备份能读出来", "learned" in rec)

print()
print("=" * 62)
print("④ 连续性：关键字段在 = 还是它")
print("=" * 62)
st = dict(base_state)
st["learned"] = {"api_error": {"count": 3}}
c = l2.continuity(st)
check("齐了 → 是它", c["ok"], f"({c})")

st2 = dict(base_state)
del st2["trace"]
c2 = l2.continuity(st2)
check("缺字段 → 报出来", not c2["ok"] and "trace" in c2["missing"], f"({c2})")

print()
print("=" * 62)
print("⑤ 单次否决要留痕")
print("=" * 62)
st = dict(base_state)
n = l2.veto(st, "这次赶时间，先不备份")
check("留了一条", n == 1 and st["maintenance_veto"][0]["reason"].startswith("这次赶时间"))

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)
shutil.rmtree(tmp, ignore_errors=True)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
