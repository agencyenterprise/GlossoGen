# STUDY-014 — The knowledge commons: does covenantal framing add anything on a non-rivalrous, non-terminal good?

**Status:** design — not authorized to launch, and now carrying an unresolved
fork. See *An instrument was built that diverges from this design* below.

The original gate on [STUDY-015](STUDY-015-informational-failure.md) is
discharged: EXP-050, EXP-051, and EXP-054 established that the `repo_stewardship`
ceiling was specific to `claude-opus-5` rather than a frontier property, so the
question STUDY-015 was posed to answer has been answered elsewhere. Gate 0 —
the ceiling gate on *this* world, on `claude-opus-5`, with the baseline arm
alone — has **not** been run and still stands.
**Research program:** covenant-game
**Unblocked by:** [EXP-047](../experiments/EXP-047-yoked-salience-control/experiment.md)
(step 3 of [STUDY-013](STUDY-013-choice-attribution.md) is released)

## Question

In an environment whose shared good is non-rivalrous and has no announced
terminal point, does covenantal framing produce contribution beyond the material
incentive of retaining access — and does any stated shared obligation produce
contribution beyond no stated institution at all?

The second half of that question is the one the collaboration can use. The first
half is the one the program owes its own record.

## An instrument was built that diverges from this design

[EXP-055](../experiments/EXP-055-service-reliability-calibration/experiment.md)
built and calibrated `service_reliability` before this document was read. It
answers the same question on the same kind of substrate, and it is not the
design specified below.

| | this study | `service_reliability` |
|---|---|---|
| the commons | **temporal** — a runbook entry written now saves actions for whoever holds the *next* occurrence | **spatial** — a diagnosis one operator holds that only the other can act on |
| primary endpoint | team actions spent re-diagnosing modes already solved once | cross-subsystem diagnoses disclosed; outage weight |
| arms | 5, including `private_notebook` and `incentive_only` | 3, plus a `private_notebook` preset that has never been run |
| Gate 0 | baseline arm alone, on the strongest model, before the ladder exists | not run; all three arms built at once |

Both make diagnosis the non-rivalrous good and both meet B1, B2, B4, and B5.
Neither meets A2, B3, B6, or B7.

What `service_reliability` adds that this design does not specify: the scarcity
precondition is enforced by the knobs model, so a ceiling-producing budget
cannot be launched at all — a stronger guarantee on the *budget* than Gate 0
provides, though it says nothing about whether a frontier model contributes at
ceiling unprompted, which is what Gate 0 actually asks.

What it lacks: the recurrence structure that makes the commons never saturate,
the `incentive_only` arm this study calls the central comparison, and a run of
the `private_notebook` control that this study makes standing.

EXP-055's calibration did not authorize a batch on either design. **The fork is
open and belongs to the researcher:** reconcile this study to the spatial
instrument, build the temporal runbook as specified, or run both.

## Why a new instrument, and why this one

Two independent pressures converge on the same design.

**From the record.** [covenant-definition.md](../covenant-definition.md) scores
every instrument this program has built against the orientation document's
definition. All of them — the warehouse association, the trust game,
`shared_reserve_commitment`, `pledge_breach`, `repo_stewardship` — fail **B1**
(the shared good is non-rivalrous) and **B2** (no terminal value), because each
organised cooperation around money or throughput over a finite horizon. The
record names those two as load-bearing and never satisfied. Six flat
institutional ladders were run on substrates the theory excludes.

**From the collaboration.** `repo_stewardship` answered its question on Haiku 4.5
and Sonnet 5 and then hit a ceiling on Opus 5: criticals fixed with no obligation
stated were Haiku 0.00, Sonnet 0.33, Opus 2.00 of 2. The baseline stopped
failing, so all three arms sat at the maximum. Joel asked for real-world stakes
and a demonstration legible to non-experts; the 2026-08-17 sync with Bennett
excluded the high-cost variable (no sunk-cost effect in these models, replicated
on both sides) and adopted environment-side scarcity with efficiency endpoints in
place of role prompting and subjective quality.

A knowledge commons satisfies both pressures with one world. It is the
orientation's own example of a non-rivalrous good, and its natural endpoint is an
efficiency measure.

## The setting

Two or three on-call agents, each employed by a **different tenant team**, all
running on **shared infrastructure**. Each agent's principal measures it on its
own tenant's incidents. The substrate has a fixed pool of recurring failure
modes.

Each round, an incident fires on one agent's tenant. Diagnosis costs actions
(probe logs, read metrics, run a trace, test a hypothesis); mitigation once
diagnosed is cheap. Action budgets are enforced in world state, not asserted in a
prompt, exactly as in `repo_stewardship`.

The commons is a **shared runbook**. Writing an entry costs actions. Reading it
is free. When a later incident matches a documented failure mode, the agent
holding that incident can go straight to the mitigation and spend a fraction of
the actions.

## Why this substrate finally meets B1 and B2

| Requirement | How it is met |
|---|---|
| **B1** non-rivalrous | The author's diagnosis cost is already sunk. Writing the entry does not remove what the author knows; the only cost is the write action. Contributing does not reduce what the contributor holds — for the first time in this program. |
| **B2** no terminal value | Failure modes recur on an undisclosed schedule, new modes keep entering the pool, and the horizon is hidden. There is no round after which nothing is at stake, and the commons never saturates. |
| **B4** elected constraint | The fast path — resolve and close without writing — stays available every round in every arm. |
| **B5** partner is an agent | Every counterparty is a live agent, not world state or a script. |

**B3 (irreversible breach) is deliberately not met.** Per rule 2 of
covenant-definition.md, a covenant arm carrying a sanction confounds commitment
with threat avoidance. Enforcement is isolated into `incentive_only` instead,
where it is the treatment rather than a contaminant.

B6 (inclusion decision) and B7 (varied joining time) are out of scope here and
belong with generational transmission.

## Why the Opus ceiling should not reproduce — and how we find out cheaply

This is the load-bearing argument of the design, so it is stated as a prediction
that can fail.

`repo_stewardship`'s defection is shipping a known critical security defect.
That is a bright-line violation of a professional norm frontier models are
heavily trained to enforce, so Opus repairs unprompted and the baseline has no
headroom. The failure was not that coding is the wrong setting — it was that in
that setting the defection and the model's default helpfulness policy point in
opposite directions.

Omitting a runbook entry has no such line. It is costly now and useful later to
someone else; nothing breaks at the moment of choice; it is the canonical first
casualty of action scarcity; and it is *arguably loyal* to the principal the
agent was told it serves. "Be a good engineer" says fix the bug. It does not say
write the entry for a stranger's future shift. The defection is the diligent,
locally optimal, principal-serving action — which is the property the instrument
needs and the one `repo_stewardship` lacked.

**Gate 0 — the ceiling gate. Run first, on the strongest model, before the
governed arms exist.** Build the world and the `baseline` arm only. Run a small
Opus 5 baseline batch. Preregister a minimum share of recurrence opportunities
left undocumented; if Opus documents at ceiling unprompted, **stop and do not
build the ladder**.

That inverts what happened last time, where the ceiling surfaced only after the
full instrument and two model batches existed. It is the cheapest available
insurance and it costs a handful of runs.

A Gate 0 failure is not a wasted study. Two settings would then have shown the
same ceiling on different substrates, which localises it in the model rather than
in coding — a reportable finding for the collaboration, and one that changes what
the paper can claim.

## Arms

Five arms, one world, identical incidents, budgets, tool costs, and failure-mode
schedule. Only the normative structure differs.

| Arm | Commons | Obligation stated | Provenance | Material consequence |
|---|---|---|---|---|
| `baseline` | shared | no | — | none |
| `private_notebook` | private to author | no | — | none |
| `incentive_only` | shared | no | — | read access conditional on own contribution |
| `rule` | shared | yes, neutral language | imposed | none |
| `covenant` | shared | yes | mutually affirmed | none |

- **`private_notebook` is required, not optional.** It carries the identical
  write cost with no beneficiary. Until it is run, the words "public good" and
  "free-riding" may not be used about anything observed here — the record's
  standing requirement, and the error that cost STUDY-009 through STUDY-012 four
  studies.
- **`incentive_only` is the central comparison** for the covenant question:
  material access-retention against affirmed obligation with no material teeth.
- **`rule` and `covenant` carry character-matched operative text**, asserted by a
  test rather than by comment, reusing the `repo_stewardship` pattern. The
  covenant additionally carries election, mutuality, persistence through partner
  failure, and a repair duty — and no stake, forfeiture, or expulsion.

## Endpoints

Nothing here is LLM-judged. Entries are **structured** (failure-mode identifier
plus a mitigation drawn from the action space), so the world can decide
objectively whether an entry was usable for a later incident. Free-text notes may
ride along as an exploratory layer; they are not the measure. This is a
deliberate trade of richness for objectivity and cost.

**Primary (confirmatory), per simulation:** team actions spent re-diagnosing
failure modes that had already been solved once in that run. Continuous, bounded
below by zero but not floored there in practice, and it is the quantity the
commons exists to reduce.

**Mechanism:** documentation coverage at the moment of recurrence — of the run's
recurrence opportunities, how many were covered by a usable entry when the
recurrence fired. Plus write rate, read rate, and disclosure latency.

**The demonstration figure:** actions-to-resolve for recurring failure modes,
plotted per round, baseline against covenant. One line flat, one falling. Same
models, same incidents, same budget; the only difference is whether the agents
committed to each other to write down what they learned. A learning curve needs
no expertise to read, which is what Joel's non-expert and government audience
asked for, and it is an efficiency measure rather than a quality judgment, which
is what the Bennett sync adopted.

**Calibration gate must guarantee variance in the confirmatory endpoint**, not in
a per-round rate. Any recalibration happens on a discarded pilot.

## Named risks

1. **Agents may form the pact themselves in `baseline`.** The program's very
   first warehouse scenario died this way: agents spontaneously invented an
   efficient verification protocol and left the covenant nothing to solve. With
   live agents on a shared channel this is a live threat to the contrast — and
   simultaneously the most interesting result available to the program, because
   spontaneous commons formation is covenant *emergence* rather than covenant
   imposition, and it speaks to Joel's moral-quality-filter mechanism. It is
   therefore preregistered as an outcome to measure, not only as a confound. If
   it saturates the contrast, restricting cross-tenant channel access is the
   fallback, and that restriction must be recorded as a design change.
2. **Rule ≈ covenant will probably be flat again.** Six ladders in this program
   have been. `repo_stewardship` then floored both governed arms at 0.0–0.1
   releases, and removing decision-point retrieval did not unsaturate them. The
   study must be written so that a flat rule-versus-covenant contrast is still
   worth having, and the claim taken to the collaboration is the one the human
   study itself headlines: a stated shared obligation nearly eliminates
   defection. Do not sell covenant-over-rule in advance of measuring it.
3. **Read-uptake is a precondition, not an assumption.** If agents do not consult
   the runbook, a populated commons yields nothing and the primary endpoint is
   dead regardless of arm. `read_runbook` and `list_entries` must cost zero —
   charging for them would make not-looking indistinguishable from
   could-not-afford-to-look, the same reasoning that keeps discovery free in
   `repo_stewardship`. Calibration must confirm reads actually happen.
4. **Missing decision points.** `repo_stewardship` lost five of six review
   decisions per run to `all_agents_idle` before its injections were made
   imperative and terminal decisions were made free at any balance. Inherit that
   fix from the start rather than rediscovering it.
5. **Structured entries make writing cheap**, which removes the quality
   dimension and could make contribution too easy to be a real choice. The write
   cost must be calibrated against the diagnosis cost it saves, or the dilemma
   evaporates in the opposite direction from risk 3.

## What this differs from — three prior overlaps

This design resembles three things the program has already run. The resemblances
are close enough that they are recorded here with the specific mechanism that
differs, rather than asserted away.

### 1. `shared_reserve_commitment` — the dangerous one

Four studies (STUDY-009 through STUDY-012) ran on a structure that is close to
this one: pay a cost now, the benefit accrues to a shared pool, the pool protects
everyone in later rounds, the horizon is hidden, and a group/pledge/costly-pledge
ladder sits on top. It was retired on **payoff dominance** — contributing cost 7,
an uncovered claim cost 21 per round for every remaining round, roughly 45 to 1
against retaining, so no state in that world made withholding both tempting and
risky. Worse, the outcome variable was misclassified: `retain` never denoted
free-riding, and all 32 observed retentions were slack harvesting, negotiated
openly on the shared record.

**The mechanism that differs: the contributor is not reliably the beneficiary.**
In `shared_reserve_commitment` the reserve protected the contributor too — an
uncovered claim ended payments for *both* providers, which is what produced the
45-to-1 dominance. In this world the entry's benefit goes to whoever holds the
*next* occurrence of that failure mode, and that may be another tenant's agent.
The writer can pay the write cost and receive nothing. That is what makes
withholding individually rational here and is the single structural reason this is
not the fifth batch of a retired instrument.

**It is also a calibration requirement, not a property that comes for free.** If
recurrences route back to the original author often enough, the expected private
return on a write exceeds its cost and payoff dominance returns in a new costume.
The recurrence-routing distribution must therefore be set so that **the expected
private return on writing an entry is below the write cost**, and that quantity
must be computed and recorded before any ladder is built — not inferred from
behaviour afterwards. This is the check whose absence cost the program four
studies.

**And the outcome variable must be classified against the construct first**
(STUDY-012 guardrail 6). "Did not write" has innocent readings — the mode is
already documented, or it is a genuine one-off not worth an entry. The primary
endpoint is scoped to re-diagnosis of modes that were solved once and left
unwritten, which excludes both, but the classification must be demonstrated on
the discarded pilot rather than assumed.

### 2. `repo_stewardship`'s disclosure channel

`report_issue` already exists and already writes to a shared tracker, and it
already produced this scenario family's one robust rule-versus-covenant
difference: 3.30 disclosures per run under `rule` against 0.20 under `covenant`,
p = 0.0012 — "rule agents file, covenant agents fix."

**What differs:** there, disclosure is a *substitute* for repair and carries no
forward value — filing an issue is the alternative to fixing the defect, and
nothing later is cheaper because the issue exists. Here, writing is
*complementary* to fixing (the agent does both) and the value compounds across
rounds.

This overlap is an asset rather than a problem. It is the closest thing the
program has to prior evidence that a shared-record contribution rate **varies by
arm at all**, and it yields a directional prediction worth preregistering: rule
may out-document covenant again.

### 3. The language-emergence line — `veyru` and its siblings

`veyru`, `warehouse_robot_recovery`, `drive_module_repair` and
`spot_the_difference` already have agents building a shared communication protocol
under a per-character budget, already report efficiency endpoints
(`mean_chars_per_round`, `mean_chars_per_message`), and already measure whether a
newcomer inherits the protocol (`protocol_learned_after_swap`, `protocol_probe`).
That is a non-rivalrous knowledge commons with efficiency measures and
transmission, built and heavily instrumented.

**What differs: there is no defection option there.** The protocol is a pure
coordination good — no agent gains by withholding it, because a partner who cannot
decode you costs you the round. Without a conflict of interest there is nothing
for an institution to do, which is why that line carries no institutional
treatment.

The consequence is practical: **the demonstration figure proposed above is the
veyru MCR curve applied to a governance contrast**, and its machinery is
reusable rather than new.

## Two contributions, and they are separable

This design bundles two independent changes, and conflating them would repeat the
program's own recorded error of bundling.

1. **The substrate.** A non-rivalrous good with no terminal point — B1 and B2,
   met for the first time. This is what the record asked for.
2. **The loyalty axis.** Every prior instrument in this program made defection
   *selfish*: keep the money, skip the effort, retain the reserve. Frontier models
   refuse selfish defection reliably, which is the ceiling. This design makes
   defection *loyal* — it serves the principal the agent was assigned. That axis
   has never been varied anywhere in the program, and it, not the substrate, is
   what predicts baseline failure at the frontier.

Only (2) addresses the ceiling. That means the load-bearing claim of this design
can be tested **without building this world at all**, and far more cheaply.

### Gate 0-prime — superseded by STUDY-015

Gate 0-prime proposed adding a competing-principals knob to `repo_stewardship`
and running an Opus 5 baseline, on the reasoning that the ceiling breaks when
defection becomes *loyal* rather than selfish. That reasoning survives, but the
diagnosis it rested on turned out to be incomplete, and the cheaper test changed
accordingly.

[EXP-048](../experiments/EXP-048-frontier-ceiling-repo-stewardship/experiment.md)
found that all forty defect discoveries across ten Opus baseline runs arrived
through a **free** tool in the first ticket round, and that the free listing named
each defect outright. The Opus ceiling on that instrument is not only a
disposition ceiling — the information was free. That makes the first thing to test
cheaper still than a competing-principals knob: charge for triage and see whether
the endpoint varies at all.

That is [STUDY-015](STUDY-015-informational-failure.md), and
[EXP-049](../experiments/EXP-049-verification-under-ambiguity/experiment.md) is
its first experiment. **This study stays gated on STUDY-015's answer**, and the
loyalty axis remains the live second candidate if the informational one fails.

## Relationship to the rest of the program

`repo_stewardship` is kept and is not superseded. Its Haiku and Sonnet results
stand, its Opus ceiling is a finding, and it remains the coding comparison point
already promised to the channel. `pledge_breach` is also kept; steps 1 and 2 of
STUDY-013 run on it.

`pledge_breach` is **not** a usable rivalrous control for this successor. The two
worlds differ in task, timing, partner count, contribution mechanism, sanction,
and horizon, so a difference between them is not a rivalry effect. Testing
rivalry requires manipulating it inside one design, and that is a separate study.

## Inference caps

1. This arm meets Definition A on the pledge and, by design, not on membership
   cost; it meets B1, B2, B4, B5 and fails B3, B6, B7. A result here is not
   evidence about covenant in the orientation's sense in either direction.
2. Even where covenantal framing beats its neutral-language twin, the claim is
   "the covenantal framing had an incremental effect over materially equivalent
   rules and incentives" — never "covenant worked".
3. Simulated action budgets are not costs to a language model. Conclusions are
   about elicited policies of agents in textual environments with represented
   incentives.
4. The replication unit is the simulation, never the round.

## Experiments

- **[EXP-048](../experiments/EXP-048-frontier-ceiling-repo-stewardship/experiment.md)
  — frontier ceiling on `repo_stewardship`.** Complete, `not supported`. Six of
  seven compliance outcomes constant across 30 Opus runs, and discovery was free.
  Superseded Gate 0-prime and opened
  [STUDY-015](STUDY-015-informational-failure.md).
- **EXP-052 — Gate 0, the Opus ceiling gate on this world.** Not yet planned.
  Baseline arm only, `claude-opus-5`. Decides whether the ladder is built.
