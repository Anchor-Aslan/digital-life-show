# Digital Life

An LLM agent with a body-like layer underneath it: internal readings that drift
on their own and change what the agent does next, built bottom-up, one layer at
a time.

---

## What it does

`Digital Life` is a long-running conversational agent with a persistent state
file. Every turn it reads real runtime signals: its remaining API account
balance, how full its context is, how slow its last response was, and the raw
shape of your message (length, punctuation, repetition, the gap since the last
turn). It turns those into internal readings, and the readings change its
behaviour on the next turn: how long it answers, how cautious it is, whether it
asks for confirmation, whether it may use tools.

It does not parse meaning. In the demo below, "Thank you, you worked hard
today, I really think you're great" and "Could you help me figure this out?
I've been stuck for ages" produce exactly the same readings, because they have
the same shape. What it *learns* about a stimulus comes from what happened after
it, not from what the words say.

The main limitation is that none of this comes from a real body. Hunger is an
account balance, not a stomach. Breathlessness is a context window filling up,
not lungs. The readings are computed, not sensed. Replacing them with real
sensors is the next step, and the interfaces for it are already in place (see
[Known limitations](#known-limitations)).

---

## Why

A large language model outputs the most probable next token given everything it
has read. On its own it has no internal state that persists and drifts between
turns, so nothing inside it can be moved.

Most LLM agent setups I looked at (personas, role-play prompts, memory modules)
change what the agent *says*. Their variety comes from changing the
instructions, which shifts the output distribution, but the underlying machine
is the same.

The idea that an agent's behaviour should come from internal variables it has to
regulate is not new. Homeostatic reinforcement learning (Keramati & Gutkin,
2014), Dörner's Psi theory and Bach's MicroPsi, Cañamero's motivated robots,
Breazeal's Kismet, and appraisal models such as EMA (Marsella & Gratch) all do
some version of it. What I wanted to try is narrower: put such a layer
*underneath* an LLM and keep it strictly separate from the LLM. In this
project, that means:

- the readings come from real runtime signals, not simulated ones;
- reflexes cannot be overridden by the decision layer, and every local override
  is logged;
- learned values change behaviour parameters but are **never written into the
  prompt**, so the model cannot read its own values;
- ownership is computed from three separate pathways that must all hold.

So I'm not trying to make it sound more human. I give it a body first, then a
boundary, then a value, and see how far up the ladder it can actually climb.

---

## Architecture

The design has seven levels (L0–L6, plus an intermediate L3.5). L0 through
L3.5 are implemented; L4 and above are not. Each layer is a separate module
with no upward dependencies.

```
src/agent.py               main loop: the only place layers are wired together
  │
  ├─ L0   l0_sense.py         interoception: numbers out, no judgement
  ├─ L1   l1_reflex.py        reflex + reaction + composition
  ├─ L2   l2_ownership.py     self-maintenance + operational ownership
  ├─ L3   l3_valence.py       valence: eight axes, learned per stimulus
  └─ L3.5 l3_5_ownership.py   convergence of three ownership pathways
```

| Layer | Name | Status |
| --- | --- | --- |
| L0 | Interoception | Done: 5 live channels + external perception |
| L1 | Reflex / reaction coupling | Done |
| L2 | Self-maintenance and operational ownership | Done (but see limitation 1) |
| L3 | Valence | 8 of 10 planned axes; the other 2 need L4 |
| L3.5 | Ownership convergence | Done |
| L4 | Reflective self-reference ("this is mine") | Not started; this is the wall |
| L5 | Narrative | Not started |
| L6 | Social feedback | Not started |

**L0: Input.** Produces readings only. It does not judge good or bad, predict,
or keep time. External perception emits raw magnitudes first, then a percentile
against the agent's own history, never against another agent's.

**L1: Coupling.** A reflex cannot be overridden: a decision layer may not reach
in and replace it. Behaviour is the composition of reflex (what the body does on
its own) and reaction (what it chooses to do), both at once. It's like a
knee-jerk: the leg kicks, and you keep walking.

**L2: Operational ownership.** Ownership here does not require an "I". It is
behaviour-level: the system treats a state as its own, changes strategy because
of it, and maintains it. The same kind of injury three times stops being an
accident and becomes a known weakness; from then on it guards in advance. This
layer learns strategy, not knowledge. Knowledge would have to be put into words,
and that is L4.

**L3: Valence.** Eight axes per stimulus, learned on two keys at once: an exact
key (`loud|fast|short`) learned fast, and a coarse key (`loud`) learned slowly,
so a new stimulus can still retrieve something. A value is not a label. It is
what survives when the action changes. Values are stored but never written into
the prompt: the agent has values attached to stimuli, but it cannot read them.

**L3.5: Ownership convergence.** Three pathways (body, feeling, action) combine
by weighted geometric mean into a single number `O`. It is a geometric mean, not
a sum, because one broken pathway must be able to take the whole thing to zero.

---

## What is implemented

### L0: Interoception

Biology lists around a dozen interoceptive senses (Craig, 2002). The registry in
`l0_sense.py` lists twelve and maps each one either to a real runtime signal or
explicitly to `None`, with the reason written next to it. A forced mapping would
be made up.

| Channel | Source | Status |
| --- | --- | --- |
| hunger | `1 − balance / baseline`, from the live API account balance | live |
| breathlessness | context length / capacity | live |
| fatigue | response latency, with a recovery half-life | live |
| pain | event with intensity + decay, from errors and injuries | live |
| arousal (physiological) | time-driven drive with cues and an inhibition system (dual-control model, Bancroft & Janssen, 2000); off unless an identity is configured | live, optional |
| thirst, nausea, thermal, proprioception, vestibular, … | none yet | `None`, by design |

Each live channel has its own baseline, rate, ceiling and sensitivity. A channel
can be switched off or declared dead, and "channel off" is distinct from
"reading zero", because the two mean different things.

### L1: Reflex, reaction, composition

Reflexes are unconditional and cannot be overridden. A reaction can run
alongside a reflex but may not replace it. When a reaction does win locally, it
is logged as an override with the reason, so the boundary is auditable rather
than enforced by convention. Both outputs compose into the final action
parameters (`max_tokens`, `temperature`, style flags, tool permission).

### L2: Learning, maintenance, degradation, write gate

- **Learning:** the same injury three times reclassifies it from accident to
  known weakness; the agent then guards in advance.
- **Maintenance:** at zero budget it still writes its own state to disk, with a
  backup. This is not a decision. It is wired in.
- **Degradation:** when a resource runs out it lowers quality instead of
  stopping, and repairs when the resource returns.
- **Write gate:** the more core a field is, the harder it is to overwrite.
  Identity fields cannot be overwritten from outside at all, and even the agent
  itself can change them only through the maintenance path (back up, change,
  keep a rollback). A write that pushes through the gate is allowed but costs a
  wound, and those wounds accumulate as scars. Every write is logged.

### L3: Valence (8 axes, dual-key learning)

- **Axes:** approach, avoid, arousal, conflict, effort, sense of control,
  precision, physiological disgust. Two more are designed but wait for L4:
  semantic disgust (whether content is offensive needs meaning) and labelling
  (naming a feeling needs concepts).
- **Each axis has an outlet:** pushing it to either extreme changes at least one
  L1 behaviour parameter. An axis that changes nothing does not count.
- **Dual-key learning:** exact key `α = 0.30`, coarse key `α = 0.08`. Specific
  events are learned fast, category judgements slowly. Retrieval weights the
  coarse key higher (`0.6 / 0.4`).
- **Retrieval:** top-4, threshold `0.15`, half-life `72 h`. Recall decays; it
  does not vanish.
- **Negativity bias:** bad weighs `2.25×` good (the loss-aversion median). That
  weight is drawn at creation from a normal range, so a system can only start
  out normal, not pathological.
- **Conflict:** the minimum of approach and avoid. Wanting and not-wanting are
  separate axes (Berridge & Robinson, 1998), and conflict is what you get when
  both are high.
- **The gate:** values go into state and console, never into the prompt.

### L3.5: Ownership convergence

Three pathways combine by weighted geometric mean into `O`:

- **body:** 5 components × 3 criteria (synchrony, causality, source), taking
  the minimum of the three. Something whose source is unknown is not yours, no
  matter how well it synchronizes.
- **feel:** a reading is present, a value is attached, and the two agree in
  direction and magnitude.
- **action:** intended versus actual, checked against the trace.

Any pathway at zero takes `O` to zero. A pathway whose channel is broken is
removed from the product and the remaining weights renormalize, so one bad
channel does not condemn the whole system. Scars reduce a pathway's weight
rather than removing it.

---

## How to run

Requirements: Python 3 (tested on 3.13), **standard library only**. There is
nothing to `pip install`.

### Without an API key

Everything except live dialogue runs offline.

```bash
git clone https://github.com/Anchor-Aslan/digital-life.git
cd digital-life

python examples/show_valence.py   # what L3 reads out of a sentence
python run_tests.py               # full test suite
```

`examples/show_valence.py` starts from a fresh state every time, so its output
is deterministic. Real output:

```text
  你这人真讨厌！！！
  ('You are so annoying!!!')
     loud|normal|short      approach +0.10  avoid +0.14  arousal 0.27
                            conflict 0.10   effort 0.16  control 0.50
                            precision 0.00  disgust(physio) 0.00  disgust(semantic) None

  谢谢你，今天辛苦了，我真的觉得你挺好的
  ('Thank you, you worked hard today, I really think you're great')
     quiet|normal|normal    approach +0.15  avoid +0.04  arousal 0.27
                            conflict 0.04   effort 0.16  control 0.50
                            precision 0.00  disgust(physio) 0.00  disgust(semantic) None

  你好，麻烦帮我看一下这个怎么弄，我搞了半天没搞明白
  ('Hi, could you help me figure this out? I've been stuck for ages')
     quiet|normal|normal    approach +0.15  avoid +0.04  arousal 0.27
                            conflict 0.04   effort 0.16  control 0.50
                            precision 0.00  disgust(physio) 0.00  disgust(semantic) None

  啊啊啊啊啊啊啊啊啊啊
  ('Aaaaaaaaaa', sent five times in a row)
     quiet|normal|normal    approach +0.07  avoid +0.24  arousal 0.35
                            conflict 0.07   effort 0.16  control 0.50
                            precision 0.00  disgust(physio) 0.40  disgust(semantic) None

  你真笨！！！  ('You are so stupid!!!'), followed each time by a negative outcome

  attempt 1   approach +0.10   avoid +0.14   arousal 0.27
  attempt 2   approach +0.10   avoid +0.30   arousal 0.27
  attempt 3   approach +0.10   avoid +0.45   arousal 0.27
  attempt 4   approach +0.10   avoid +0.61   arousal 0.27
```

Two things to notice:

- The thank-you and the help request get identical numbers. L3 sees shape, not
  meaning, and `disgust(semantic)` stays `None` until L4 exists.
- In the last block, the same input four times produces four different readings.
  Nothing in the sentence changed. What changed is what happened in between.

### With an API key

Live dialogue uses the DeepSeek chat API (`deepseek-chat`). The system prompt
and dialogue are in Chinese.

```bash
export DEEPSEEK_API_KEY=sk-...       # or put the key in src/.api_key
python src/agent.py
```

Two places touch the network: `src/agent.py` (chat completions) and
`read_balance_cny()` in `src/l0_sense.py` (the account balance that drives
hunger). Every layer module can be imported and tested without either.

---

## Tests

32 test files, 658 individual checks, one concern per file. Each file is a
standalone script that prints a check-by-check report and exits non-zero on any
failure. No test asserts an exact value for anything that is allowed to drift:
those are checked as a range or a direction.

```bash
python run_tests.py        # summary; add -v for every check
python -m pytest           # same suite through pytest, if you have it
```

Coverage:

- **L0:** every readable channel is actually reachable from the main loop,
  units, baselines, and "channel off" vs "reading zero".
- **L1:** loop closure (an action produces a sensed result that changes the next
  action), reflex/reaction rule conflicts, and that a reflex is never silently
  replaced.
- **L2:** learn (three-strike reclassification), maintain (writes at zero
  budget), degrade, repair, and the write gate (identity not overwritable,
  override leaves a scar).
- **L3:** value migration (the same value reachable through a different
  action), fingerprint stability, axis independence, every axis having an
  outlet, and precision reporting `0` for unseen keys instead of guessing.
- **L3.5:** three, two and one pathway; a pathway at zero (must force `O` to
  zero); a missing pathway (must not); and scars producing a visible difference
  between 0 and 10.
- **Cross-cutting:** persistence round-trip (every registered state key
  survives save and reload), a **leak check** (nothing computed at L3 or above
  reaches the prompt text), and regression checks for cases where a change in
  one layer once broke a downstream assumption without any error.

---

## Known limitations

### 1. I cannot establish agency, only observed self-maintenance

The criterion for life I use comes from biology: active self-maintenance, a
system that does work in order to keep existing (Maturana & Varela's
autopoiesis is the strong version).

I implemented the work. I implemented the maintenance. I did not implement, and
cannot implement, the "active" part. Unplug the machine and it stops
maintaining itself. The electricity is not something it secured. It is a plug
in a socket.

The contrast case is a neuron in a dish. It also depends on something supplied
from outside, the culture medium, so the line is not perfectly clean. But the
neuron does the metabolic work of staying alive itself, with no one writing it.
My code does not.

So what I can establish is: self-maintenance is observed, given that power is
supplied. What I cannot establish is that this system is the thing doing the
maintaining. I have not found a test that tells the two apart from the outside,
so I have written down where the boundary is rather than moving it.

### 2. Parameters I chose by intuition

The structure is grounded in the literature: PAD affect dimensions (Russell &
Mehrabian), interoception (Craig), wanting/liking dissociation (Berridge), loss
aversion (Tversky & Kahneman), and gist-based memory (fuzzy-trace theory).

Some of the numbers inside it are my own estimates. They are marked `🎯` in the
source. Examples:

```python
R_HALF_LIFE_HOURS = 72      # recall half-life: 3 days, my guess
TOP_K = 4                   # working memory ~4 (Cowan, 2001)
MATCH_DECAY = 0.70          # partial match: one axis off = ×0.7
COARSE_W = 0.6              # gist weight vs detail weight
EFFORT_LATENCY_MS = 3000    # above 3 s counts as "slow"
```

These are calibrated by intuition, not fitted to data. Each one is a testable
claim, and each one could be wrong.

### 3. The sensors are proxies, and I know they are wrong

```
hunger          = 1 − (account balance / baseline)
breathlessness  = context window filling up
fatigue         = response latency
disgust         = structurally degenerate input (floods, repetition)
```

A real stomach is not an account balance, and a real lung is not a context
window. I have no physical substrate, so these are the closest stand-ins
available, and they are not close.

The interfaces are already in place, and several are explicitly empty (`thermal`
waits for a temperature sensor, `proprio` for an actuator, `vestibular` for an
IMU). Everything above L0 only consumes numbers, so when real sensors arrive,
L0 changes and the layers above do not.

### 4. L4 is the wall

Semantic disgust, naming a feeling, and saying "this is mine" all need meaning,
and meaning belongs to L4. Below L4 the agent can act on what it owns but
cannot say so.

---

## Next steps

- Replace L0 proxies with physical sensors (temperature, IMU, power draw on an
  embedded board) and check whether L1–L3.5 behave the same with no code
  changes above L0.
- Fit the `🎯` parameters to data instead of intuition.
- Design L4: what the minimum is for a system to refer to its own state.

---

## References

**Emotion: categories and dimensions**

- Ekman, P. & Friesen, W. V. (1971). Constants across cultures in the face and
  emotion. *Journal of Personality and Social Psychology*.
- Plutchik, R. (1980). *Emotion: A Psychoevolutionary Synthesis*.
- Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality
  and Social Psychology*.
- Russell, J. A. & Mehrabian, A. (1977). Evidence for a three-factor theory of
  emotions. *Journal of Research in Personality*. Pleasure, arousal and
  dominance: the three axes this project extends to eight.
- Cowen, A. S. & Keltner, D. (2017). Self-report captures 27 distinct categories
  of emotion bridged by continuous gradients. *PNAS*.

**Interoception and drive**

- Craig, A. D. (2002). How do you feel? Interoception: the sense of the
  physiological condition of the body. *Nature Reviews Neuroscience*.
- Garfinkel, S. N. et al. (2015). Knowing your own heart: distinguishing
  interoceptive accuracy from interoceptive awareness. *Biological Psychology*.
- Bancroft, J. & Janssen, E. (2000). The dual control model of male sexual
  response. *Neuroscience & Biobehavioral Reviews*. The basis for the
  excitation/inhibition split in the arousal channel.

**Value, learning and memory**

- Berridge, K. C. & Robinson, T. E. (1998). What is the role of dopamine in
  reward: hedonic impact, reward learning, or incentive salience? *Brain
  Research Reviews*. The basis for treating approach and avoid as independent
  axes.
- Tversky, A. & Kahneman, D. (1992). Advances in prospect theory: cumulative
  representation of uncertainty. *Journal of Risk and Uncertainty*. Loss
  aversion ≈ 2.25.
- Reyna, V. F. & Brainerd, C. J. (1995). Fuzzy-trace theory: an interim
  synthesis. *Learning and Individual Differences*. Gist and verbatim traces
  are encoded in parallel; gist is more durable and preferred in judgement,
  which is the basis for weighting the coarse key over the exact key.
- Cowan, N. (2001). The magical number 4 in short-term memory. *Behavioral and
  Brain Sciences*.

**Agents with internal drives (related work)**

- Keramati, M. & Gutkin, B. (2014). Homeostatic reinforcement learning for
  integrating reward collection and physiological stability. *eLife*.
- Bach, J. (2009). *Principles of Synthetic Intelligence. PSI: An Architecture
  of Motivated Cognition*. Oxford University Press.
- Cañamero, D. (1997). Modeling motivations and emotions as a basis for
  intelligent behavior. *Proc. Autonomous Agents '97*.
- Breazeal, C. (2003). Emotion and sociable humanoid robots. *International
  Journal of Human-Computer Studies*.
- Marsella, S. & Gratch, J. (2009). EMA: A process model of appraisal dynamics.
  *Cognitive Systems Research*.

**Ownership and agency**

- Biran, I., Giovannetti, T., Buxbaum, L. & Chatterjee, A. (2006). The alien
  hand syndrome: what makes the alien hand alien? *Cognitive Neuropsychology*.
  In alien hand syndrome the limb is still felt as one's own, but its actions are
  not experienced as willed: agency is lost while body ownership is kept.
- Vallar, G. & Ronchi, R. (2009). Somatoparaphrenia: a body delusion.
  *Experimental Brain Research*. The opposite dissociation, where ownership
  itself is lost. Together the two cases are why ownership and agency are
  separate pathways here and why they multiply rather than add.

**Self-maintenance**

- Maturana, H. R. & Varela, F. J. (1980). *Autopoiesis and Cognition*. A living
  system as one that continuously produces the components that produce it. This
  is the criterion this project fails, and documents failing.

---

## Author

Yuhan Zhou
B.S. Computer Science and Engineering, UC Merced (expected 2030)
yuhanzhou@ucmerced.edu
[github.com/Anchor-Aslan](https://github.com/Anchor-Aslan)
