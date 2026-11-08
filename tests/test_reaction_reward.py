import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_reaction_reward.py —— 任务 5（B 版三重锁）+ 施工单 2 / C2、A4

判据（施工单 1 任务 5 + 施工单 2 C2/A4）：
    ① 4 种情况 reward 对得上（升温 / 原样重发 / 间隔太久不学 / 其他不学）
    ② 连续 20 条安静消息：learn 被调用 0 次
    ③ 学一次再回滚：值表和学之前**逐键完全相等**（含粗键、指纹键）
    ④ 一场最多 3 次（A4：启动清零）
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
ag = load("agent")

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'OK ' if ok else 'BAD'} {name}  {detail}")


def feat(text, st=None):
    # 造一个"刚刚才说过话"的 state：gap≈0 → pace=fast（A1 修好之后真机就是这样）
    if st is None:
        st = {"messages": [], "last_seen": datetime.now().isoformat()}
    return l3.extract_features(text, st)


print("=" * 66)
print("① 四种情况的 reward")
print("=" * 66)

f_quiet = feat("你好")
f_loud = feat("你好啊！！！")
r, why = l3.reaction_reward(f_quiet, "你好", f_loud, "你好啊！！！")
check("安静 → 变吼：-0.30", r == l3.REACTION_ESCALATE, f"({r}, {why})")

r2, _ = l3.reaction_reward(f_quiet, "你好", f_quiet, "你好")
check("原样重发：-0.20", r2 == l3.REACTION_REPEAT, f"({r2})")

slow = dict(f_quiet); slow["pace"] = "slow"
r3, _ = l3.reaction_reward(f_quiet, "你好", slow, "你好")
check("间隔太久（pace=slow）→ 不学", r3 is None, f"({r3})")

r4, _ = l3.reaction_reward(f_quiet, "你好", feat("今天天气不错"), "今天天气不错")
check("普通下一句 → 不学", r4 is None, f"({r4})")

print()
print("=" * 66)
print("② 20 条安静消息：一次都不学")
print("=" * 66)
n_learn = 0
prev_f, prev_t = None, ""
for q in ["你好", "在吗", "嗯", "好的", "谢谢", "晚安", "随便聊", "吃了吗",
          "我回来了", "今天挺热", "有点累", "先这样", "回头说", "知道了",
          "收到", "明白了", "先忙", "晚点聊", "拜拜", "走了"]:
    f = feat(q)
    if prev_f:
        r, _ = l3.reaction_reward(prev_f, prev_t, f, q)
        if r is not None:
            n_learn += 1
    prev_f, prev_t = f, l3._norm_text(q)
check("20 条安静消息 → learn 0 次", n_learn == 0, f"(实际 {n_learn})")

print()
print("=" * 66)
print("③ 学一次再回滚：逐键还原（含粗键、指纹键）")
print("=" * 66)
st = ag.default_state()
st["messages"] = []
f = feat("你好啊！！！", st)
keys = l3.keys_touched_by_learn(f)
before = {k: dict((st.get("valence") or {}).get(k) or {}) for k in keys}
l3.learn(st, f, l3.REACTION_ESCALATE)
l3.log_reaction(st, keys, l3.REACTION_ESCALATE, before)
after_learn = {k: dict((st.get("valence") or {}).get(k) or {}) for k in keys}
check("学完之后确实有变化", any(after_learn[k] != before[k] for k in keys),
      f"(变了 {[k for k in keys if after_learn[k] != before[k]][:3]}…)")

res = l3.rollback_reaction(st, 0)
after_rb = {k: dict((st.get("valence") or {}).get(k) or {}) for k in keys}
same = all(after_rb[k].get("avoid", 0) == before[k].get("avoid", 0)
           and after_rb[k].get("approach", 0) == before[k].get("approach", 0) for k in keys)
check("回滚后逐键取值相同", same, f"({res.get('restored')} 还原 / {res.get('deleted')} 删除)")
check("学之前不存在的键被删掉", all((k in st["valence"]) == bool(before[k]) for k in keys))

print()
print("=" * 66)
print("④ 一场最多 3 次（A4）")
print("=" * 66)
st2 = ag.default_state()
cnt = 0
for _ in range(6):
    r, _ = l3.reaction_reward(f_quiet, "你好", f_loud, "你好啊！！！", learned_count=cnt)
    if r is not None:
        cnt += 1
check("学满 3 次后不再学", cnt == l3.REACTION_CAP, f"({cnt}/{l3.REACTION_CAP})")

print()
print("=" * 66)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 66)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
