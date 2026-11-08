import os as _os, sys as _sys
TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
SRC_DIR = _os.path.join(_os.path.dirname(TESTS_DIR), "src")
if TESTS_DIR not in _sys.path: _sys.path.insert(0, TESTS_DIR)
def _load_helper(n):
    import importlib.util as _u
    sp = _u.spec_from_file_location(n, _os.path.join(TESTS_DIR, n + ".py")); m = _u.module_from_spec(sp); sp.loader.exec_module(m); return m

"""_test_persist_roundtrip.py —— 落盘 → 重启 → 值还在不在（踩坑 #32 的回归测试）

为什么非要这个文件：
    38 个测试全是"单进程内存里跑"，**没有一个走过 load_state()**。
    所以"11 个键重启清零"能藏一个星期——测试全绿，病全在。

这个文件守两道门：
    ① **正向**：存进去的 11 个键，重启读完必须原样还在（含备份恢复那条路）
    ② **反向**：把登记表里的键删掉一个 / 加一个没登记的 → 检查器必须**报红**
       （反向才叫验证：只证明"现在是绿的"，证明不了"坏了会红"）
"""

import importlib.util
import io
import json
import os
import shutil
import tempfile

BASE = SRC_DIR
if BASE not in __import__('sys').path:
    __import__('sys').path.insert(0, BASE)

import _check_keys


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(BASE, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ag = load("agent")
l2 = ag.l2

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✅' if ok else '❌'} {name}  {detail}")


# 11 个曾经一重启就消失的键（踩坑 #32）
KEYS = ("maintenance", "maintenance_budget", "maintenance_veto", "write_log",
        "degrade_level", "heal_enabled", "last_pain", "analgesia_bias",
        "pain_modulation", "apoptosis_log", "repair_log")

TMP = tempfile.mkdtemp(prefix="dsh-persist-")


def fresh():
    """一份带非默认值的状态（要能证明"存的是我设的值"，不是碰巧等于默认值）"""
    st = ag.default_state()
    st["maintenance_budget"] = 0.25
    st["maintenance_veto"] = [{"at": "2026-11-02T00:00:00", "reason": "赶时间"}]
    st["write_log"] = [{"key": "learned", "who": "other", "ok": False}]
    st["degrade_level"] = "low"
    st["heal_enabled"] = False
    st["last_pain"] = 0.42
    st["analgesia_bias"] = 0.5
    st["pain_modulation"] = 0.3
    st["apoptosis_log"] = [{"channel": "tool"}]
    st["repair_log"] = [{"channel": "tool", "cost": 0.01}]
    return st


def save_and_reload(st, tag):
    """落盘（走真正的 maintain）→ 重启（走真正的 load_state）"""
    state_file = os.path.join(TMP, f"agent-{tag}.json")
    backup_file = os.path.join(TMP, f"agent-{tag}.backup.json")
    l2.maintain(st, state_file, backup_file)
    ag.STATE_FILE, ag.BACKUP_FILE = state_file, backup_file
    disk = json.load(io.open(state_file, encoding="utf-8"))
    back, notes = ag.load_state()
    return disk, back, notes, state_file, backup_file


print("=" * 62)
print("① 11 个键：存进去 → 重启 → 还在吗")
print("=" * 62)
disk, back, notes, state_file, backup_file = save_and_reload(fresh(), "main")

check("磁盘上 11 个键都在", all(k in disk for k in KEYS),
      f"缺={[k for k in KEYS if k not in disk]}")
missing = [k for k in KEYS if k not in back]
check("重启后 11 个键都在", not missing, f"丢={missing}")

diff = [k for k in KEYS if k in disk and k in back and disk[k] != back[k]]
check("值一个都没变（逐键比对）", not diff, f"变了={diff}")

check("修复开关还是关的（以前会被重启偷偷打开）", back.get("heal_enabled") is False,
      f"heal_enabled={back.get('heal_enabled')}")
check("降级档位还是 low（以前会被归回 normal）", back.get("degrade_level") == "low",
      f"degrade_level={back.get('degrade_level')}")
check("写入留痕还在（以前一重启就查不出谁改过）",
      isinstance(back.get("write_log"), list) and len(back["write_log"]) == 1,
      f"write_log={back.get('write_log')}")
check("维护预算没被重置回 0.10", back.get("maintenance_budget") == 0.25,
      f"maintenance_budget={back.get('maintenance_budget')}")

print()
print("=" * 62)
print("② 备份那条路：主文件烂了 → 从备份恢复 → 键还得在")
print("=" * 62)
io.open(state_file, "w", encoding="utf-8").write("{ 坏掉的内容")
back2, notes2 = ag.load_state()
check("确实走了备份恢复", any("备份" in n for n in notes2), f"{notes2}")
missing2 = [k for k in KEYS if k not in back2]
check("恢复后 11 个键都在", not missing2, f"丢={missing2}")
check("伤口保留（恢复不是失忆）", any(w.get("kind") == "state_corrupt"
                                        for w in back2.get("wounds", [])))

print()
print("=" * 62)
print("③ 反向验证：删掉一个登记键 → 检查器必须报红")
print("=" * 62)
src = io.open(os.path.join(BASE, "agent.py"), encoding="utf-8-sig").read()
for victim in ("write_log", "degrade_level", "heal_enabled"):
    broken = src.replace(f'"{victim}": ', f'"__removed_{victim}": ')
    if broken == src:
        check(f"能篡改 {victim}（测试自身前提）", False, "源码里没找到这一行")
        continue
    keys_now = _check_keys.default_keys_from_source(broken, os.path.join(BASE, "agent.py"))
    check(f"删掉 {victim} 后，它从登记表消失", victim not in keys_now)
    unreg = sorted(_check_keys.used_keys(BASE) - keys_now)
    check(f"删掉 {victim} 后，检查器报出它", victim in unreg, f"未登记={unreg[:5]}")

print()
print("=" * 62)
print("④ 反向验证：加了新键但忘了登记 → 也要红（以后加功能最容易犯）")
print("=" * 62)
# 模拟真实场景：**代码里开始写一个新键，但 agent.py 没登记**
fake_base = os.path.join(TMP, "fakecode")
os.makedirs(fake_base, exist_ok=True)
for f in _check_keys.SOURCES:
    p = os.path.join(BASE, f)
    if os.path.exists(p):
        shutil.copyfile(p, os.path.join(fake_base, f))
io.open(os.path.join(fake_base, "l2_ownership.py"), "a", encoding="utf-8").write(
    '\n\ndef _future_write(state):\n    state["future_knob"] = 0.7\n')
unreg_future = _check_keys.unregistered(fake_base)
check("新键没登记 → 检查器报红", "future_knob" in unreg_future, f"未登记={unreg_future}")

print()
print("=" * 62)
print("⑤ 正向验证：现在这份代码 → 检查器是干净的")
print("=" * 62)
unreg_now = _check_keys.unregistered(BASE)
check("当前未登记键 = 0", not unreg_now,
      f"未登记={unreg_now}" if unreg_now else "0 个")
check("11 个键都在登记表里",
      all(k in _check_keys.default_keys(BASE) for k in KEYS),
      f"缺={[k for k in KEYS if k not in _check_keys.default_keys(BASE)]}")

shutil.rmtree(TMP, ignore_errors=True)

print()
print("=" * 62)
print(f"结果：通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败：" + "、".join(FAIL))
print("=" * 62)

# 11-07 施工单 3：失败必须让退出码非 0，否则审计/CI 都看不见
if FAIL:
    raise SystemExit(1)
