import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_finish_reason.py —— 任务 0：finish_reason 必须真的能被读到

为什么要有这个测试：
    `call_model()` 原来返回的是 `data["choices"][0]["message"]`，
    但 `finish_reason` 在 `choices[0]` 上，不在 message 里。
    于是 `run_turn()` 里 `msg.get("finish_reason") == "length"` 永远 False
    → "输出被预算截断"那条学习信号（reward -0.6）**从来没触发过**。

    这类 bug 的特点：不崩、不报错、测试全绿，只是**那条路永远不走**。
    所以判据是：**所有读 API 响应字段的地方，必须有一个 mock 测试覆盖。**

本测试不联网（用 mock 假响应）。
"""

import importlib.util
import io
import json
import os

BASE = SRC_DIR
spec = importlib.util.spec_from_file_location("agent", os.path.join(BASE, "agent.py"))
ag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ag)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


def fake_response(finish_reason, content="好的", tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    body = {
        "choices": [{"index": 0, "message": msg, "finish_reason": finish_reason}],
        "usage": {"completion_tokens": 12, "prompt_tokens": 8},
    }
    raw = json.dumps(body).encode("utf-8")

    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return raw

    return _R()


# D3：先替换 load_key，否则没 key 的机器在 mock 生效前就失败了
_orig_load_key = ag.load_key
ag.load_key = lambda: "sk-test"


class _Patcher:
    """临时替换 agent.urllib.request.urlopen，退出时还原。"""

    def __init__(self, fake):
        self.fake = fake
        self.orig = ag.urllib.request.urlopen

    def __enter__(self):
        ag.urllib.request.urlopen = lambda *a, **k: self.fake
        return self

    def __exit__(self, *a):
        ag.urllib.request.urlopen = self.orig
        return False


print("=" * 66)
print("任务 0：finish_reason 在 choices[0] 上，不在 message 里")
print("=" * 66)

params = {"max_tokens": 50, "temperature": 0.7, "trim": False,
          "urgent": False, "trim_keep": []}

# ---- ① length 必须被识别 ----
with _Patcher(fake_response("length")):
    msg, usage, ms = ag.call_model([{"role": "user", "content": "x"}], "sys", params)
check("length 能读到", msg.get("finish_reason") == "length", f"({msg.get('finish_reason')})")

# ---- ② run_turn 会把它变成信号 ----
st = {"messages": [], "trace": [], "wounds": [], "scars": [],
      "fatigue_pool": {"value": 0.0}, "identity": {"gender": None, "traits": {}},
      "spend": {"date": "2026-11-07", "today_cny": 0.0, "history": []},
      "valence": {}, "valence_keys": [], "bad_weight": 2.25, "flag_extreme": False}
with _Patcher(fake_response("length")):
    answer, signals = ag.run_turn(st, "你好", "sys", params)
check("run_turn 产出 truncated_by_budget", "truncated_by_budget" in signals, f"({signals})")

# ---- ③ stop 不该误报 ----
st2 = dict(st)
st2["messages"] = []
with _Patcher(fake_response("stop")):
    answer2, signals2 = ag.run_turn(st2, "你好", "sys", params)
check("stop 不报截断", "truncated_by_budget" not in signals2, f"({signals2})")

# ---- ④ usage 还在（顺手确认没把别的字段弄丢）----
with _Patcher(fake_response("stop")):
    msg3, usage3, _ = ag.call_model([{"role": "user", "content": "x"}], "sys", params)
check("usage 没丢", usage3.get("completion_tokens") == 12, f"({usage3})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
