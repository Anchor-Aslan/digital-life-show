"""_check_keys.py —— 状态键登记检查（审计第 8 步 / 持久化测试 共用）

判据（踩坑 #32）：
    代码里任何 `state["x"] = ...` / `state.setdefault("x", ...)` 的 x，
    必须出现在 `agent.default_state()` 里；
    否则 `load_state()` 只搬默认状态里有的键 → **这个键每次重启都清零**。

为什么单独一个文件（而不是在 _audit.py 里写一段）：
    这条判据要给两边用——审计（静态查）和持久化测试（反向验证"删一个会不会红"）。
    两边各写一遍 = 迟早不一致，**而这次 bug 本身就是"两张键表各写各的"**。
"""

import importlib.util
import io
import os
import re

# 会被写状态的源文件（新增模块记得加进来）
SOURCES = ('l0_sense.py', 'l1_reflex.py', 'l2_ownership.py', 'l3_valence.py', 'l3_5_ownership.py', 'agent.py')


def code_only(text):
    """去掉三引号块和整行注释：注释里写一句 state["x"] 不算真的写。"""
    text = re.sub(r'"""[^"]*"""', '', text)
    text = re.sub(r"'''[^']*'''", '', text)
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith('#'))


def used_keys(base):
    """代码里**读过或写过**的所有 state 键。

    为什么"读"也算：
        接口键（heal_enabled / analgesia_bias / pain_modulation / maintenance_budget）
        代码只读、**上层才写**。只查"写过"就保护不到它们——
        删掉登记，读的时候永远拿到默认值，**上层设了也白设**（这是同一个 bug 的潜伏版）。

    已知盲区（写在这里，别当没有）：
        动态键名（`state.get(channel + "_modulation")`）抓不到，只能靠人登记。
    """
    out = set()
    for f in SOURCES:
        p = os.path.join(base, f)
        if not os.path.exists(p):
            continue
        body = code_only(io.open(p, encoding='utf-8-sig').read())
        out |= set(re.findall(r'state\["([a-zA-Z_]+)"\]\s*=', body))      # 写
        out |= set(re.findall(r'state\.setdefault\("([a-zA-Z_]+)"', body))  # 写
        out |= set(re.findall(r'state\.get\("([a-zA-Z_]+)"', body))         # 读
    return out


def default_keys_from_source(src, filename):
    """从 agent.py 源码（可以是改过的）里取 default_state() 的键表。"""
    ns = {"__name__": "agent_probe", "__file__": filename}
    exec(compile(src, filename, "exec"), ns)
    return set(ns["default_state"]())


def default_keys(base, agent_file='agent.py'):
    """现在这份 agent.py 里登记过的键。"""
    path = os.path.join(base, agent_file)
    return default_keys_from_source(io.open(path, encoding='utf-8-sig').read(), path)


def unregistered(base, agent_file='agent.py'):
    """用过、但没登记的键（= 重启会丢 / 上层设了白设）。空列表 = 干净。"""
    return sorted(used_keys(base) - default_keys(base, agent_file))
