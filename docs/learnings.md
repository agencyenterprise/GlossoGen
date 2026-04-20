# Project Schmidt — Learnings & Observations

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

**Why it matters.** Structural asymmetry is not a one-time property of a scenario. Any mechanism that lets information flow between agents — and the post-mortem is explicitly designed to do that — can leak the asymmetric information over time and dissolve the constraint. Knowledge gaps need to be maintained *per round*, not just set up once at scenario start.

**Decision.** Added a per-round "stellar alignment" mechanic. Each round:

- A stellar offset (1–13) remaps which motif's procedure is the correct treatment for the observed symptoms.
- Physical parameters (hold/press duration, starting face, pressure level) are re-rolled.
- Only the Specialist has the stellar reader, so only they can resolve the remapping and parameters for the current round.

Even if the Observer has fully memorized all 14 motif procedures and all possible parameter values through post-mortem, they cannot act without the Specialist's per-round stellar reading. Per-round communication stays necessary by construction.

**Related.** This is a refinement of the Apr 14 structural-asymmetry principle: the asymmetry must be *renewable*, not just present. It also shows that mechanisms interact — post-mortem and fixed-table knowledge asymmetry are each defensible in isolation but combine badly.

---

## Footnotes

[^1]: **Patient-Ambulance scenario (deprecated).** A medical emergency setup with two agents. Field Observer role: a regular person or first-semester medical student present at the scene of a patient in distress, with no specialist medical knowledge. They could observe symptoms (visual, verbal reports from the patient, vitals if available) but could not diagnose. Specialist role: an experienced doctor located remotely, able to reason about diagnosis and treatment but with no direct access to the patient. The two communicated over a channel with a pressure budget. Goal: correctly identify the condition and next action. **Deprecated** after Apr 14 because LLMs could not stay in the Field Observer role; they applied full medical training regardless of the prompt and solved cases without needing the Specialist.
[^2]: **Alien Patient / Alien Emergency scenario (current primary).** Same two-role structure as patient-ambulance, but the patient is an alien entity with invented anatomy, invented symptoms, and invented symptom-to-cause mappings. The Specialist's context includes the symptom-to-cause reference material for this alien species; the Field Observer's context does not. The Field Observer observes raw symptoms (descriptive, non-medical language) and must relay them to the Specialist, who maps them to causes and returns treatment instructions. Because the alien medical system is fabricated, no LLM has prior knowledge of it, so the knowledge asymmetry is real rather than prompted. Future enhancement: dual-render environment so the same simulation logic can be skinned as either alien or hospital terminology.
[^3]: **Post-mortem mechanism.** An out-of-game, meta-level discussion phase inserted between rounds. Agents step out of their in-scenario roles and talk directly about their communication protocol: what worked, what didn't, what to change. This is separate from in-game communication, which stays focused on solving the current task. See the 2026-04-17 learning entry for why this phase is necessary and what it produces.
