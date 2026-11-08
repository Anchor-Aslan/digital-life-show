"""What the valence layer (L3) reads out of a sentence. No API key needed.

    python examples/show_valence.py

Every block starts from a fresh, empty state, so the output is deterministic.
L3 sees only the *shape* of a message (volume, pace, length, repetition),
never its meaning.
"""
import importlib.util
import os

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def load(n):
    s = importlib.util.spec_from_file_location(n, os.path.join(SRC, n + ".py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


l3 = load("l3_valence")
W = 68


def bar():
    print("=" * W)


def fresh():
    return {"valence": {}, "valence_keys": [], "bad_weight": 2.25,
            "flag_extreme": False, "messages": [], "intero": {},
            "last_readings": {"pain": 0.0, "fatigue": 1.0, "hunger": 0.0,
                              "breath": 0.1, "arousal": 0.3},
            "last_latency_ms": 800, "fatigue_pool": {"value": 0.0},
            "trace": [], "wounds": [], "sens": {}}


def show(text, gloss, msgs=None):
    st = fresh()
    if msgs:
        st["messages"] = msgs
    f = l3.extract_features(text, st)
    v = l3.value_of(st, f, text=text, msgs=st.get("messages"))
    p = v.get("precision") or {}
    epi = p.get("episodic")
    print("  %s" % text)
    if gloss:
        print("  (%s)" % gloss)
    print("     %-22s approach %+.2f  avoid %+.2f  arousal %.2f"
          % ("%s|%s|%s" % (f["vol"], f["pace"], f["len"]),
             v["approach"], v["avoid"], v["arousal"]))
    print("     %-22s conflict %.2f   effort %.2f  control %.2f"
          % ("", v["conflict"], v["effort"], v["control_sense"]))
    print("     %-22s precision %s  disgust(physio) %.2f  disgust(semantic) %s"
          % ("", ("%.2f" % epi) if isinstance(epi, (int, float)) else "-",
             v.get("disgust_physio", 0.0), v.get("disgust_semantic")))
    print()


bar()
print("  One sentence, several numbers")
bar()
print()
show("你这人真讨厌！！！", "'You are so annoying!!!'")
show("谢谢你，今天辛苦了，我真的觉得你挺好的", "'Thank you, you worked hard today, I really think you're great'")
show("你好，麻烦帮我看一下这个怎么弄，我搞了半天没搞明白", "'Hi, could you help me figure this out? I've been stuck for ages'")

bar()
print("  Flooding (the same message repeated)")
bar()
print()
spam = [{"content": "啊啊啊啊啊啊啊啊啊啊", "source": "user"} for _ in range(5)]
show("啊啊啊啊啊啊啊啊啊啊", "'Aaaaaaaaaa', sent five times in a row", spam)

bar()
print("  The same sentence, hurt four times")
bar()
print()
print("  你真笨！！！  ('You are so stupid!!!'), followed each time by a negative outcome")
print()
st = fresh()
for i in range(4):
    f = l3.extract_features("你真笨！！！", st)
    v = l3.value_of(st, f, text="你真笨！！！", msgs=st.get("messages"))
    print("  attempt %d   approach %+.2f   avoid %+.2f   arousal %.2f"
          % (i + 1, v["approach"], v["avoid"], v["arousal"]))
    if i < 3:
        l3.learn(st, f, -0.8)
print()
