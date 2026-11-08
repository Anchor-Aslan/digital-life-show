import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_issue.py —— 上报接口只留空壳（10-31）

用户判断：
  "修不起就上报" 需要 ① 知道"我身上有东西"(L4) ② 决定"要不要跟他说"(L5/L6)。
  L2b 只有状态，没有"我"，也没有"说" —— 所以只留接口：
  **只记账，一个字都不进提示词。**
"""

import importlib.util
import os

BASE = SRC_DIR


def load(n):
    spec = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l0 = load("l0_sense")
l2 = load("l2_ownership")
ag = load("agent")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


def fresh():
    return {"wounds": [], "scars": [], "sens": {}, "pain_pool": {"kinds": {}},
            "spend": {"date": "2026-10-31", "today_cny": 0.0, "history": []},
            "intero": {}, "learned": {}, "trace": [], "identity": {},
            "dead_channels": [], "channel_fails": {}, "issues_log": [],
            "messages": [], "external_history": {}, "balance_history": []}


print("=" * 66)
print("① 修不起 → 记一条 issue（只记账）")
print("=" * 66)
st = fresh()
l0.add_wound(st, "api_error", 0.9, 30)
l0.heal(st, balance=0.001)
titles = [r["kind"] for r in st.get("issues_log", [])]
check("记了 cannot_repair", "cannot_repair" in titles, f"({titles})")
check("标了未上报模型", all(not r["reported_to_model"] for r in st["issues_log"]))

print()
print("=" * 66)
print("② 这条 issue 绝对不许进提示词")
print("=" * 66)
r = l0.perceive(st, "你好", 0.001)
i = l0.update_intero(st, r)
prompt = ag.build_prompt(st)
check("提示词里没有“伤/修/坏”这类词",
      not any(w in prompt for w in ("伤", "修", "坏", "疤", "issue", "无法")),
      f"(prompt={prompt[:40]}…)")
check("提示词里没有数字", not any(c.isdigit() for c in prompt))
check("issues 还在 state 里", len(st["issues_log"]) == 1)

print()
print("=" * 66)
print("③ raise_issue 只记账，返回说明等哪一层")
print("=" * 66)
st2 = fresh()
out = l2.raise_issue(st2, "cannot_repair", "api_error")
check("记了日志", len(st2["issues_log"]) == 1)
check("明确说等 L4/L5", "L4" in out["note"] or "L5" in out["note"], f"({out['note']})")
check("没写进提示词标记", st2["issues_log"][0]["reported_to_model"] is False)
check("pending_issues 能列出来", len(l2.pending_issues(st2)) == 1)

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
