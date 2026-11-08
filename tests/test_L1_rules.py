import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_L1_rules.py —— L1 的五条核心规矩（施工单 4 / 第 4 条）

背景：这五条以前只有 `_show_*.py` 在演示（打印数字，没有断言）。
施工单 3 把它们改名成 `_show_*` 之后，**自动测试里一条都没在守**。

现在按 `_show_*` 打印出来的结论写成断言：
    ① 强压弱：疼极高时，别的信号被压下去
    ② 速率检测：没到线但涨得太快，也能触发
    ③ 阈值走天性：同一个人改 trait，同一个读数反应不同
    ④ 反应不能放开反射：反射说 800/0.3，反应想 4000/0.9，最终仍是 800/0.3
    ⑤ 裁剪时救回要留的消息：trim_keep 里的消息一条都不能丢
"""

import importlib.util
import os

BASE = SRC_DIR


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l1 = load("l1_reflex")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


print("=" * 66)
print("① 强压弱：疼到 0.95，憋 0.82 被压下去")
print("=" * 66)
fired = l1.detect({}, {"pain": 0.95, "breath": 0.82})
kept, suppressed = l1.inhibit(fired)
by_ch = {f["channel"]: f for f in kept}
sp_ch = {f["channel"]: f for f in suppressed}
pain_sev = by_ch.get("pain", {}).get("severity_eff")
breath_eff = sp_ch.get("breath", {}).get("severity_eff")
check("疼留下，且强度几乎没被削", pain_sev is not None and pain_sev > 0.8, f"({pain_sev})")
check("憋被踢出 kept", "breath" not in by_ch, f"({list(by_ch)})")
check("憋的强度被压到 0.1 以下", breath_eff is not None and breath_eff < 0.1,
      f"(原 0.1 → 压后 {breath_eff})")

print()
print("=" * 66)
print("② 速率检测：没到线，但涨得太快")
print("=" * 66)
slow = l1.detect_rate({"breath": 0.60, "breath_rate": 0.01})
fast = l1.detect_rate({"breath": 0.60, "breath_rate": 0.30})
print(f"   慢（rate 0.01）→ {slow}")
print(f"   快（rate 0.30）→ {fast}")
check("涨得慢 → 没有信号", not any(s["channel"] == "breath" for s in slow), f"({slow})")
check("涨得快 → 触发信号", any(s["channel"] == "breath" for s in fast), f"({fast})")
check("速率触发的严重度小于 1", all(s["severity"] < 1 for s in fast), f"({fast})")

print()
print("=" * 66)
print("③ 阈值走天性：改 trait，同一个读数反应不同")
print("=" * 66)
normal = {"identity": {"traits": {}}}
biglung = {"identity": {"traits": {"breath": {"threshold": 0.95}}}}
check("普通人：0.82 过线", l1.threshold_of(normal, "breath") == 0.80,
      f"({l1.threshold_of(normal, 'breath')})")
sig_n = l1.detect(normal, {"breath": 0.82})
sig_b = l1.detect(biglung, {"breath": 0.82})
check("普通人 0.82 → 触发", any(s["channel"] == "breath" for s in sig_n), f"({sig_n})")
check("阈值调到 0.95 的人，0.82 → 不触发（线跟着天性走）",
      not any(s["channel"] == "breath" for s in sig_b), f"({sig_b})")

print()
print("=" * 66)
print("④ 反应不能放开反射（朝保守合）")
print("=" * 66)
reflex_params = {"max_tokens": 800, "temperature": 0.3, "trim": True,
                 "urgent": False, "trim_keep": [], "style": [], "tool_choice": "auto"}
resp = {"params": {"max_tokens": 4000, "temperature": 0.9, "trim": False}}
final = l1.combine(reflex_params, resp)
check("max_tokens 取小的（800，不是 4000）", final["max_tokens"] == 800, f"({final['max_tokens']})")
check("temperature 取小的（0.3，不是 0.9）", final["temperature"] == 0.3, f"({final['temperature']})")
check("trim 仍为 True（反应取消不掉）", final["trim"] is True, f"({final['trim']})")

print()
print("=" * 66)
print("⑤ 裁剪时救回要留的消息")
print("=" * 66)
msgs = [{"id": "m%d" % i, "role": "user", "content": "x", "source": "user"} for i in range(45)]
resp2 = {"params": {"trim": True}, "keep_ids": ["m4"]}
final2 = l1.combine({"max_tokens": 800, "temperature": 0.7, "trim": True,
                     "urgent": False, "trim_keep": [], "style": [], "tool_choice": "auto"}, resp2)
keep = final2.get("trim_keep") or []
trimmed = [m for m in msgs if m["id"] in keep]
check("trim_keep 里记下了 m4", keep == ["m4"], f"({keep})")
check("m4 真的被留下来了", len(trimmed) == 1 and trimmed[0]["id"] == "m4", f"({[m['id'] for m in trimmed]})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

if FAIL:
    raise SystemExit(1)
