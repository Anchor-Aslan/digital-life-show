import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_no_leak.py —— 不知情测试（10-31 加）

原则（用户定）：
  **L0–L2 是下意识的，不许把读数报给模型。**
  人的自主神经不会告诉你"血氧 98%"。
  它话变短，但不知道为什么——这才是下意识。

判据：
  ① 高读数状态下，模型收到的提示词里**没有任何数字读数**
  ② 没有"体感/基线/变化/档位"这类报告词
  ③ 但行为参数**确实变了**（只观察反应，不问它知不知道）
  ④ 它"说不出原因"——因为提示词里没有原因可抄
"""

import importlib.util
import os
import re

BASE = SRC_DIR


def load(n):
    spec = importlib.util.spec_from_file_location(n, os.path.join(BASE, n + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


l0 = load("l0_sense")
l1 = load("l1_reflex")
l2 = load("l2_ownership")
ag = load("agent")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


# 造一个"很难受"的状态
st = {"identity": {"gender": None, "traits": {}}, "learned": {}, "wounds": [],
      "sens": {}, "intero": {}, "trace": [], "messages": [{}] * int(l0.TRAITS["breath"]["max_messages"] * 0.9),
      "last_latency_ms": 2400}
l0.add_wound(st, "api_error", 0.9, 30)
readings = l0.perceive(st, "你到底在干什么？？？", 10.0)
intero = l0.update_intero(st, readings)
readings_l1 = {**readings, **{f"{k}_rate": v["rate"] for k, v in intero.items()}}

prompt = ag.build_prompt(st)

print("=" * 62)
print("模型收到的全部内容：")
print("-" * 62)
print(prompt)
print("-" * 62)
print()

print("=" * 62)
print("① 提示词里有没有数字读数")
print("=" * 62)
nums = re.findall(r"\d+\.\d+", prompt)
check("没有小数读数", not nums, f"(发现 {nums})")

print()
print("=" * 62)
print("② 有没有报告词")
print("=" * 62)
for word in ("体感", "基线", "变化", "档位", "hunger", "breath", "pain", "fatigue"):
    check(f"没有“{word}”", word not in prompt)

print()
print("=" * 62)
print("③ 行为确实变了（只观察反应）")
print("=" * 62)
params, applied = l1.reflex(st, readings_l1)
params = l1.combine(params, l1.response(st, readings_l1))
params = l2.apply_learned(st, params)
params = l2.degrade(st, params)
print(f"  信号：{l1.describe(applied)}")
print(f"  参数：max_tokens={params['max_tokens']} temp={params['temperature']}")
check("输出被压短了", params["max_tokens"] < 800, f"({params['max_tokens']})")
check("温度降了", params["temperature"] < 0.7, f"({params['temperature']})")
check("憋得慌触发了裁", params["trim"] is True)

print()
print("=" * 62)
print("④ 它没有“答案”可抄（说不出原因才是对的）")
print("=" * 62)
# 提示词里既没有数字，也没有原因说明
check("提示词里没有“因为你憋了/疼了”这类解释",
      not any(w in prompt for w in ("因为", "所以", "读数", "状态")))

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
