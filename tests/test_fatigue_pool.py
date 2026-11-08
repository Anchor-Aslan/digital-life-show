import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

import importlib.util, os
from datetime import datetime, timedelta
spec = importlib.util.spec_from_file_location("l0", os.path.join(SRC_DIR, "l0_sense.py"))
l0 = importlib.util.module_from_spec(spec); spec.loader.exec_module(l0)

print("=" * 64)
print("① 连续慢：越来越累（体力桶）")
print("=" * 64)
st = {"last_latency_ms": 2000}
print(f"  第0轮（刚开始）：累={l0.fatigue(st):.2f}")
for i in range(1, 5):
    l0.add_load(st, 2000)
    print(f"  第{i}轮（都 2000ms）：累={l0.fatigue(st):.2f}")

print()
print("=" * 64)
print("② 单轮慢：跟以前一样（不误伤）")
print("=" * 64)
st2 = {"last_latency_ms": 2000}
print(f"  只跑一轮：累={l0.fatigue(st2):.2f}（应 2.5）")
st2["last_latency_ms"] = 800
print(f"  正常速度那轮：累={l0.fatigue(st2):.2f}（应 1.0）")

print()
print("=" * 64)
print("③ 休息：桶慢慢空（半衰期 30 分钟）")
print("=" * 64)
st3 = {"last_latency_ms": 800}
for _ in range(5):
    l0.add_load(st3, 2000)
print(f"  连干 5 轮后：累={l0.fatigue(st3):.2f}")
st3["fatigue_pool"]["at"] = (datetime.now() - timedelta(minutes=30)).isoformat()
print(f"  休息 30 分钟：累={l0.fatigue(st3):.2f}")
st3["fatigue_pool"]["at"] = (datetime.now() - timedelta(minutes=120)).isoformat()
print(f"  休息 2 小时：累={l0.fatigue(st3):.2f}")

print()
print("=" * 64)
print("④ 轻松活不累积")
print("=" * 64)
st4 = {"last_latency_ms": 600}
for _ in range(5):
    l0.add_load(st4, 600)
print(f"  连干 5 轮 600ms：累={l0.fatigue(st4):.2f}（应 0.75，桶没涨）")

# ================= 11-07 新增：累的来源分层（聊天几乎不累，干活才累）=================
print()
print("=" * 64)
print("累的来源：chat / tool / long_out / retry")
print("=" * 64)


def _fresh():
    return {"identity": {"gender": None, "traits": {}},
            "fatigue_pool": {"value": 0.0, "at": "2026-11-07T00:00:00"}}


st_chat = _fresh()
for _ in range(20):
    l0.add_work(st_chat, "chat")
v_chat = round(st_chat["fatigue_pool"]["value"], 4)
print(f"  聊 20 句        → 桶 {v_chat}   （应很小）")
assert v_chat < 0.1, v_chat

st_tool = _fresh()
for _ in range(10):
    l0.add_work(st_tool, "tool")
v_tool = round(st_tool["fatigue_pool"]["value"], 4)
print(f"  干 10 个工具活   → 桶 {v_tool}   （应明显）")
assert v_tool > 0.5, v_tool

st_retry = _fresh()
l0.add_work(st_retry, "retry")
print(f"  返工 1 次        → 桶 {st_retry['fatigue_pool']['value']}   （应 > 聊 1 句）")
assert st_retry["fatigue_pool"]["value"] > 0.002

st_burst = _fresh()
l0.add_load(st_burst, 2500)
print(f"  正常 2.5 秒      → 桶 {st_burst['fatigue_pool']['value']}   （应 0，不算负荷）")
assert st_burst["fatigue_pool"]["value"] == 0.0

l0.add_load(st_burst, 20000)
print(f"  某一轮 20 秒     → 桶 {st_burst['fatigue_pool']['value']}   （应 > 0）")
assert st_burst["fatigue_pool"]["value"] > 0.0

print()
print("四种来源的比例：", l0.LOAD_WEIGHTS)
