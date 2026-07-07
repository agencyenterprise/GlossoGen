# Project GlossoGen — Learnings & Observations

> A living document capturing what we've tried, what we learned, and why we pivoted. Append new entries at the bottom of the "Learnings" section with the date, so entries stay in chronological order.

---

## How to use this doc

Each learning is a dated entry with:

- **What we tried**: the concrete setup or mechanism
- **What happened**: observed behavior
- **Why it matters**: the implication for platform design or scenario design
- **Decision**: what we're doing about it

Scenario descriptions referenced throughout are in the [Footnotes](#footnotes) section at the bottom.

---

## Learnings

### 2026-04-14 — LLMs can't "unlearn" their prior knowledge

**What we tried.** Designed scenarios with two agents playing roles that required one of them to have limited domain knowledge. The clearest example was the patient-ambulance scenario [^1], where a Field Observer (role: a regular person or first-semester medical student with no specialist knowledge) was supposed to relay observations about a patient to a Specialist (role: experienced doctor) over a communication link. The whole point was to force genuine communication, because the Field Observer shouldn't be able to diagnose on their own.

We tried variations of this pattern in several scenarios. In all of them, we asked the LLM to "be more dumb", play the role of a less-knowledgeable person, or otherwise restrict its own knowledge via the prompt.

**What happened.** The Field Observer LLM didn't stay in character. It consistently drew on its full medical training knowledge to reason about the patient and, in many runs, effectively solved the case on its own without needing the Specialist. Telling the model to pretend to be less knowledgeable is not a reliable mechanism. This pattern repeated across prompt variations and scenarios, not just in patient-ambulance.

**Why it matters.** Asymmetric-knowledge scenarios are the cleanest way to force emergent communication between agents (one agent has information the other needs). But we can't create the asymmetry with a prompt alone. The asymmetry has to be **structural**: the less-knowledgeable agent genuinely cannot solve the problem because the information needed isn't in the model's training data.

**Decision.** Build scenarios where the knowledge gap is real, not prompted. The "Alien Patient" scenario [^2] is the current instantiation: alien anatomy and symptom-to-cause mappings are invented and loaded into only the Specialist's context. The Field Observer has no prior exposure to this content, so they genuinely can't diagnose alone and must use the communication channel to describe what they see. This forces multi-turn communication by construction rather than by instruction.

**Related.** This informs a broader platform principle: we can't rely on prompts to constrain LLM behavior when the scenario requires capability limits. Structure the scenario so the limit exists in the information state, not in the instructions.

---

### 2026-04-15 — Telephone works but doesn't sell

**What we tried.** Evaluated the Telephone scenario [^4] as a client-facing option alongside Alien Patient [^2]. The Telephone setup is a minimal two-agent relay with budget pressure — deliberately stripped down so we could iterate on knobs quickly.

**What happened.** Technically it works. Pressure produces compression, and the scenario iterates substantially faster than Alien Patient (shorter rounds, simpler state, fewer moving parts). But when we looked at it as a client-facing demo, it landed flat: telephone-style relay games have an extensive existing emergent-communication literature (iterated reference games, signalling games, etc.), and LLM results in that setting don't visibly differentiate from what's already been shown with smaller models or non-LLM agents. Nothing in the output screams "this required an LLM".

**Why it matters.** A scenario can be technically sound and still fail the "why LLMs, why now" bar. For research outputs aimed at a paper or a grant, differentiation from prior literature matters as much as the raw result. If a scenario has strong prior art, LLM results in it will read as incremental even if the platform around them is novel.

**Decision.** Dropped Telephone as a client-facing scenario. Retained it internally (for a while) as a rapid prototyping sandbox: token→character budgets and the post-mortem mechanism were both first exercised in Telephone and then ported to Alien Patient once they looked promising. Telephone was fully removed once Alien Patient stabilized and the knobs had settled.

**Related.** General principle for scenario selection: prefer settings with little or no prior emergent-communication literature, so any observed emergence is clearly attributable to the LLM agents and the platform mechanics rather than to a well-known property of the game.

---

### 2026-04-15 — Progressive pressure produces emergence but confounds the measurement

**What we tried.** The first mechanism that actually produced emergent communication in the Alien scenario [^2] was a progressive pressure curriculum: start agents in a relatively easy environment (generous budget), then shrink the budget across epochs within a single simulation, forcing them to iterate toward shorter and shorter messages. No post-mortem, no meta-reflection phase — just a shrinking budget over time. It worked.

**What happened.** At the Apr 15 client sync, Elias asked us to drop progressive pressure as the default experimental setup. His reasoning, paraphrased from the call:

> "I feel like the epochs here are actually maybe, at least initially, not necessary. It seems like this is introducing an additional variable."

The proposal: treat each pressure level as its own separate environment with a fixed knob (100%, 75%, 50%, 35%), run agents only in that environment, and see what comes out. The curriculum question ("does training in an easier environment first help?") is a real question, but it's a downstream question — not the primary experiment.

Simon Kirby agreed and sharpened the point: a fixed-pressure setup gives you a clean, testable hypothesis ("how does encoding vary with cost?"). You can run the sim at 75% and at 35% and directly compare them. With progressive pressure, you can't separate "the pressure is now 35%" from "the agents have been through 75% first" — every result has two causes baked into it.

**Why it matters.** This is a scientific-methodology constraint, not a platform limitation. Progressive pressure is a mechanism that produces emergence, but it's not a measurement we can cleanly reason about. It confounds the knob (budget) with the history (prior training on easier budgets).

It also foreshadowed the Apr 16 regression: once the team removed progressive pressure in favor of fixed levels, emergent communication disappeared entirely. That regression is what motivated the post-mortem mechanism [^3] — we needed something that produces emergence under static pressure, so that the pressure level itself remains a clean independent variable.

**Decision.** Primary experiments use fixed pressure levels (100%, 75%, 50%, 35%) with default 50%. Progressive pressure retained as a fifth setting on the knob so we can still produce emergence when we need it (demos, sanity checks) and study the curriculum question later as its own experiment. The post-mortem mechanism was introduced to recover emergence under static pressure without reintroducing the confound.

**Related.** Two principles worth carrying forward: (1) mechanisms that _produce_ a result are not the same as mechanisms that cleanly _measure_ it; scientific validity often requires sacrificing the former for the latter. (2) Every knob we add should be independently controllable — pressure level and pressure history are two different variables and should not be entangled by default.

---

### 2026-04-16 — Agents can't reason about their own token budgets

**What we tried.** Our first pressure mechanism used a token-based cost function: agents had a token budget per message or per round, and communication carried a cost measured in tokens. The idea was that token pressure would force compression and, eventually, emergent shorthand.

**What happened.** Agents didn't know how many tokens their messages would consume before sending. Tokenization happens after the model generates text, so the agent has no direct visibility into its own output length in token units. Agents could not tell whether a candidate message was over or under budget, which made the pressure signal effectively invisible to the decision process.

We tried to fix this by giving agents a `count_tokens` tool function they could call before committing a message. This also failed: agents over-used the tool, calling it repeatedly in tight loops (we saw effectively infinite loops until we capped usage at 10 calls per decision). Even with the cap, the tool turned every message decision into a multi-step tool-use sequence, which bloated the trace and didn't produce cleaner compression behavior.

**Why it matters.** Pressure mechanisms only work if the agent can perceive them. Any cost function whose unit is invisible to the agent (tokens, bytes, bits) will fail to shape behavior reliably. The budget has to be expressed in a unit the agent can count in its own output **before** it commits.

**Decision.** Switched to a **character-based** budget. Agents can count characters in their own output directly (it's just string length) and can self-regulate without a tool. Characters are the current active pressure unit.

**Related.** This also has a platform-design implication: avoid tools that make results unreproducible or that shift the cost from the communication channel onto the tool-use loop. The `count_tokens` experiment is a cautionary example.

---

### 2026-04-17 — Emergent language needs a dedicated learning phase, not just in-game chatter

**What we tried.** Ran the Alien Patient scenario [^2] under character-based budget pressure with no explicit learning phase. Agents could only communicate "within-game", meaning every message had to be in service of solving the current patient (relaying symptoms, requesting more info, proposing treatments). There was no separate phase for the agents to step back and discuss their communication protocol itself.

**What happened.** Round success rate was far too low. Agents didn't develop any meaningful emergent language to reduce character usage, because they never had the opportunity to talk about and learn from their mistakes. Under pressure, the best they could do was trim verbs and punctuation and use a shortened version of English. There was some compression, but nothing that looked like a genuine codebook or shared shorthand. The protocol stayed close to natural language with surface-level truncation.

This makes sense in hindsight: agents stayed in-character trying to save the patient, so meta-level conversations about "how should we communicate more efficiently" never happened. Pressure alone, without a channel to reflect on it, doesn't produce structural language change.

**Why it matters.** Budget pressure is necessary but not sufficient for emergent communication. Without a dedicated reflection channel, agents optimize their messages locally (drop a word here, abbreviate there) but never coordinate on a shared system. The pressure signal exists, but there's no mechanism for the agents to jointly respond to it.

**Decision.** Introduced a **post-mortem mechanism**: after each round, agents get a free-form discussion phase specifically to review what worked, what didn't, and propose changes to their communication protocol. The post-mortem is out-of-game and meta-level. This shifts the pressure from "compress this one message" to "evolve a shared system we can both use".

**Result.** With the post-mortem in place, agents consistently self-organize codebooks: shared abbreviations first, then single-character codes for complex compound actions (e.g., "J" standing in for a full action agreed earlier). Success rate holds up even under heavy character pressure. Validated with Elias and Simon on Apr 17 with strong positive reception. This is now the core mechanism backing the platform's emergent-language results.

**Related.** This is the clearest example so far of why the platform design matters as much as the scenario design. The same pressure knob produced trivial truncation in one setup and genuine codebook emergence in another, based purely on whether the agents had a place to reflect.

---

### 2026-04-17 — Post-mortem codebook-sharing erodes structural asymmetry; fix with per-round re-randomization

**What we tried.** Ran the Alien Patient / Veyru scenario [^2] with the post-mortem mechanism [^3] enabled on top of a fixed symptom→treatment mapping. The Specialist held the 14-motif lookup table; the Field Observer did not. The post-mortem phase let both agents talk freely between rounds about their communication protocol.

**What happened.** The codebook shorthand emerged as hoped (see the earlier 2026-04-17 entry above), but a second failure mode surfaced: because post-mortem discussion is unconstrained and cumulative across rounds, the Field Observer could learn the symptom→treatment mapping directly from the Specialist over time. Once the Observer had seen enough rounds, they could in principle self-diagnose and self-treat without needing the Specialist at all — exactly the collapse the Apr 14 learning warned about, re-introduced through the back door by the very mechanism we added to fix compression.

**Why it matters.** Structural asymmetry is not a one-time property of a scenario. Any mechanism that lets information flow between agents — and the post-mortem is explicitly designed to do that — can leak the asymmetric information over time and dissolve the constraint. Knowledge gaps need to be maintained _per round_, not just set up once at scenario start.

**Decision.** Added a per-round "stellar alignment" mechanic. Each round:

- A stellar offset (1–13) remaps which motif's procedure is the correct treatment for the observed symptoms.
- Physical parameters (hold/press duration, starting face, pressure level) are re-rolled.
- Only the Specialist has the stellar reader, so only they can resolve the remapping and parameters for the current round.

Even if the Observer has fully memorized all 14 motif procedures and all possible parameter values through post-mortem, they cannot act without the Specialist's per-round stellar reading. Per-round communication stays necessary by construction.

**Related.** This is a refinement of the Apr 14 structural-asymmetry principle: the asymmetry must be _renewable_, not just present. It also shows that mechanisms interact — post-mortem and fixed-table knowledge asymmetry are each defensible in isolation but combine badly.

---

### 2026-04-27 — Provider safety filters silently corrupt baselines

**What we tried.** Ran Alien Patient baselines across model families. Sonnet was expected to behave consistently with itself across runs.

**What happened.** Sonnet baselines were wildly inconsistent — identical setups produced round-success rates from 0.17 to 0.73. The cause wasn't protocol variance: Anthropic's safety filter was refusing model calls. Two triggers — the role name "specialist", and aggressive procedural verbs in the alien-patient prompts ("tap firmly", "press"). Refused calls returned silently as no-ops, so corrupted runs looked like idle agents rather than failed API calls. Refusals were happening \~15 times per 20-round run before we knew to look.

**Why it matters.** Provider-side safety filters can silently substitute no-ops into a run, and the corruption is indistinguishable from a real behavioral signal. Every baseline before this fix was contaminated — the apparent "Sonnet is weaker than GPT-4" gap was an artifact of refusals, not capability.

**Decision.** Two-pronged fix shipped together: (1) replaced aggressive verbs in scenario prompts with neutral alternatives, audited the rest for similar triggers (the earlier "specialist alpha" rename workaround is subsumed); (2) added a `tenacity`\-based retry around `agent.run()` so refused calls fail loudly and re-attempt instead of producing silent no-ops.

**Result.** Refusal rate down from \~15 to 1–2 per 20-round run. A 50-round stress run completed with zero refusals. Sonnet's baseline now closely tracks GPT-4 — the first cross-family data point supporting the central thesis that **protocol design, not raw model capability, is the dominant variable.**

**Related.** Two principles to carry forward: refusals must be observable (no provider-injected silence), and scenario prompt audits for filter triggers are part of platform hygiene before each cross-model baseline sweep.

---

## Footnotes

[^1]: **Patient-Ambulance scenario (deprecated).** A medical emergency setup with two agents. Field Observer role: a regular person or first-semester medical student present at the scene of a patient in distress, with no specialist medical knowledge. They could observe symptoms (visual, verbal reports from the patient, vitals if available) but could not diagnose. Specialist role: an experienced doctor located remotely, able to reason about diagnosis and treatment but with no direct access to the patient. The two communicated over a channel with a pressure budget. Goal: correctly identify the condition and next action. **Deprecated** after Apr 14 because LLMs could not stay in the Field Observer role; they applied full medical training regardless of the prompt and solved cases without needing the Specialist.
[^2]: **Alien Patient / Alien Emergency scenario (current primary).** Same two-role structure as patient-ambulance, but the patient is an alien entity with invented anatomy, invented symptoms, and invented symptom-to-cause mappings. The Specialist's context includes the symptom-to-cause reference material for this alien species; the Field Observer's context does not. The Field Observer observes raw symptoms (descriptive, non-medical language) and must relay them to the Specialist, who maps them to causes and returns treatment instructions. Because the alien medical system is fabricated, no LLM has prior knowledge of it, so the knowledge asymmetry is real rather than prompted. Future enhancement: dual-render environment so the same simulation logic can be skinned as either alien or hospital terminology.
[^3]: **Post-mortem mechanism.** An out-of-game, meta-level discussion phase inserted between rounds. Agents step out of their in-scenario roles and talk directly about their communication protocol: what worked, what didn't, what to change. This is separate from in-game communication, which stays focused on solving the current task. See the 2026-04-17 learning entry for why this phase is necessary and what it produces.
[^4]: **Telephone scenario (deprecated as client-facing; retired internally).** A minimal two-agent relay setup where one agent receives a payload and must pass it along to another over a pressure-constrained channel. Used as the first home for budget-pressure experiments (token budgets, then character budgets) and for the post-mortem mechanism before those features were ported to Alien Patient. Deprecated as a client-facing scenario on Apr 15 because it sits inside a well-established emergent-communication literature and doesn't distinguish LLM behavior from prior results. Fully removed from the codebase after Alien Patient had absorbed the useful mechanics.
