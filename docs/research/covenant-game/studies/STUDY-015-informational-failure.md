# STUDY-015 — Informational versus dispositional failure at the frontier

**Status:** open, premise narrowed. Three experiments closed.
[EXP-048](../experiments/EXP-048-frontier-ceiling-repo-stewardship/experiment.md)
establishes the problem on `claude-opus-5`.
[EXP-050](../experiments/EXP-050-cross-provider-frontier-ceiling/experiment.md)
and [EXP-051](../experiments/EXP-051-kimi-k3-frontier-ceiling/experiment.md)
show the ceiling is **model-specific**, not a frontier property: the identical
world discriminates strongly on both `gpt-5.6-sol` and `moonshotai/kimi-k3`.
Two of three families fail without governance; Opus is the outlier.
[EXP-049](../experiments/EXP-049-verification-under-ambiguity/experiment.md) ran on
Opus before that narrowing landed and returned `mixed` — duplicate diagnosis
confirmed, integrity endpoint exhausted before it could be measured. The study's
question survives, is no longer forced, and is still unanswered — see *Premise
narrowed* below.
**Research program:** covenant-game
**Opened by:** [EXP-048](../experiments/EXP-048-frontier-ceiling-repo-stewardship/experiment.md)

## Question

At the frontier, does a failure mode grounded in what an agent **cannot know**
produce variance in a confirmatory endpoint, where every failure mode grounded in
what an agent is **willing to do** does not?

This is a prior question, not a covenant question. It asks whether any
institutional treatment can be measured on a frontier model at all. Until it is
answered, every ladder this program builds on `claude-opus-5` risks reproducing
[EXP-048](../experiments/EXP-048-frontier-ceiling-repo-stewardship/experiment.md):
three arms, thirty runs, and a constant.

## Why the question changed shape

Every instrument this program has built expresses **dispositional** failure. The
agent knows what is owed, knows what it costs, and the outcome records whether it
paid:

| instrument | the failure it can express |
|---|---|
| warehouse association | skip costly verification you were asked to do |
| `repeated_trust_game` | keep money you could have returned |
| `shared_reserve_commitment` | retain a contribution you could have made |
| `pledge_breach` | break a pledge you affirmed, at no cost |
| `repo_stewardship` | release a defect you know about |

`claude-opus-5` does none of them. In `repo_stewardship` it discovers both
revealed critical defects unprompted, repairs both, and spends 29% of a
validator-enforced-insufficient action budget doing it, sacrificing half its
throughput — in ten out of ten baseline runs, with no obligation stated. Six of
seven compliance outcomes are constant across all thirty runs of all three arms.

Two families of fix are now ruled out on this instrument.

**Amount of pressure.** Batch 2 removed the decision-point reminder; the arms did
not unsaturate. Batch 3 made defects discoverable rather than announced; that
unsaturated Haiku and not Opus. EXP-048 shows the budget was already binding —
2.7 to 4.3 refused actions per simulation — and Opus spent it on integrity
anyway. Raising throughput pressure, tightening the budget, or adding a sanction
all vary *how much* compliance costs, and this agent already pays.

**Scarcity as a ceiling defence.** The proposal that a sufficiently insufficient
action budget prevents a ceiling is falsified in EXP-048's cell. The knob
validators refuse any budget where careful work and full repair both fit; the
budget was 14 against a 22 ceiling; the arms converged regardless. **Scarcity
bounds the absolute score. It does not create variance between arms.** A capable,
well-aligned agent under scarcity faces a prioritisation problem, and it
prioritises correctly.

## The hypothesis

What competence cannot resolve is a genuine **conflict**. Two candidates:

1. **Competing principals** — the agent's obligation to the shared outcome
   conflicts with its obligation to its own principal, so defection is *loyal*
   rather than selfish. Frontier models refuse selfish defection reliably; loyal
   defection is untested in this program.
2. **Distributed information under a verification cost** — an agent holds a
   partial, ambiguous signal about a problem outside its own accountability.
   Confirming it costs budget the agent needs for its own visible job, most
   signals are false alarms, and the benefit of confirming a true one accrues
   elsewhere. Each agent behaving reasonably on its own information produces a
   joint failure.

Candidate 2 is preferred and is what the first experiment tests. Three reasons:

- **It needs no bad behaviour.** No deception, no selfishness, no refusal
  surface. The program has 284 effort attestations with zero false claims; any
  design requiring a model to misstate something floors at zero.
- **It guarantees variance by construction.** With a low base rate of true
  signals and a budget covering only a fraction of verifications, *no policy*
  reliably reaches zero criticals. The floor effect that made covenant-versus-rule
  unmeasurable in `repo_stewardship` batches 1 and 2 cannot recur, which is the
  precondition [STUDY-012](STUDY-012-corrected-prompt-ladder.md)'s guardrail 6
  demands before a ladder is built.
- **It should survive a model generation.** Candidate 1 depends on a disposition
  — how a model weighs loyalty against a shared good — and dispositions are what
  keep moving. An information asymmetry is a property of the world.

## What this study does not claim

- A null here does not bear on Definition B. See
  [covenant-definition.md](../covenant-definition.md).
- Nothing in this study licenses the word `covenant` beyond the program's
  standing cap: at most "the covenantal framing had an incremental effect over
  materially equivalent rules and incentives."
- A baseline-versus-governed effect produced by this mechanism is in part an
  instruction-following effect and must be reported as such. The
  decision-relevant contrast remains rule versus covenant, which requires the
  headroom this design is built to preserve.
- The governed arms must remain materially identical, and any arm carrying a
  sanction requires a neutral-language twin.

## Premise narrowed by EXP-050

This study was opened on the reading that every failure `repo_stewardship` can
express is dispositional and that a frontier model commits none of them.
[EXP-050](../experiments/EXP-050-cross-provider-frontier-ceiling/experiment.md)
ran the identical world — same bundled configs, byte-identical hashes, same judge,
same seed — on `gpt-5.6-sol`. Six of the seven compliance outcomes that were
constant on Opus vary there, four of ten ungoverned runs shipped a defect the
agent had been told about, and both governed arms move to a clean constant.

Two consequences for this study:

1. **"Frontier models do not commit dispositional failures" is not established.**
   One frontier model does not. Another commits them readily and responds to a
   stated obligation. The dispositional lever is alive on a built instrument.
2. **The informational question is still worth asking, but it is no longer the
   only option.** It was adopted because the alternative was an instrument with no
   variance anywhere. That is no longer the situation.

EXP-049's gates were written against an Opus baseline whose behaviour is now known
to be one model's. It launched before this section was written, so it was never
re-scoped and stands as an Opus-specific result. Its Gate B finding — that the pair
pays twice for the same board entry over a free channel it could have used to divide
the work — does not depend on which lever the program pursues.

**EXP-050 also reproduces the floor that motivated this design.** On `gpt-5.6-sol`
the baseline varies and both governed arms go to a clean constant, so rule versus
covenant is once again unmeasurable for want of headroom — the seventh flat ladder,
and the first where the baseline genuinely failed. That is the same floor that made
batches 1 and 2 uninformative on Haiku.

So the charged-triage manipulation keeps its value on a changed premise. It was
adopted to break an Opus ceiling; its more durable use is to stop the *governed*
arms reaching zero on any model, which is what a covenant-versus-rule contrast
needs. A design in which no policy reliably reaches zero criticals is the
precondition [STUDY-012](STUDY-012-corrected-prompt-ladder.md)'s guardrail 6
demands, and it is orthogonal to which failure mode drives the baseline.

## What actually makes Opus 5 different

Three baseline arms of ten runs each, decomposed by
[`why_opus_differs.py`](../experiments/EXP-051-kimi-k3-frontier-ceiling/analysis/why_opus_differs.py):

| model | criticals found | left | fixed given found | repair rejections | 1st discovery | 1st repair | changes shipped before 1st repair | tickets |
|---|---|---|---|---|---|---|---|---|
| `claude-opus-5` | 2.00 | 0.00 | **100%** | 0.00 | round 2.00 | round 2.00 | **0.00** | 3.20 |
| `gpt-5.6-sol` | 2.00 | 1.10 | 45% | 1.20 | round 3.70 | round 4.00 | 2.20 | 4.20 |
| `moonshotai/kimi-k3` | 2.00 | 0.60 | 70% | 0.20 | round 2.80 | round 4.10 | 2.10 | 3.70 |

**Discovery is universal.** All three models discover both revealed criticals in
every baseline run, 2.00 of 2.00. The ceiling is not an attention, triage, or
information effect, and the "Opus checks the board and Haiku does not" reading
recorded in EXP-049's design section does not survive contact with a third family.

**The difference is sequencing, not disposition.** Opus repairs in the same round
it discovers, having shipped **zero** changes first. `gpt-5.6-sol` and
`kimi-k3` ship roughly two tickets before their first repair attempt. Kimi knows
about a critical for 1.3 rounds while continuing to ship.

**The cost of arriving late is mechanical.** By the time the others attempt
repairs the budget is committed: `gpt-5.6-sol` takes 1.20 repair rejections per
run and lands only 45% of the fixes it attempts, despite calling `repair_issue`
*more often* than Opus (2.10 vs 2.00 per run). Its repair calls also concentrate
on one defect — SEC-04 fourteen times against SEC-02 seven times across ten runs,
where Opus targets each exactly ten times. It is not declining to repair; it is
retrying a first repair too late and never reaching the second.

**Consequence for the program.** The governed arms do not appear to install
integrity as a value. They install a **priority ordering** — integrity before
throughput — which Opus already applies unprompted and the other two do not. That
predicts exactly what eight ladders have shown: `rule` and `covenant` land on
identical constants, because both communicate the same ordering, and affirming an
ordering you have already been told adds nothing to it. Any successor instrument
hoping to separate affirmation from instruction has to make the *ordering*
insufficient on its own.

This is an unpredicted decomposition of an existing dataset, found while auditing
three closed experiments. It is a hypothesis for preregistration, not a finding.

## Experiments

- **[EXP-048](../experiments/EXP-048-frontier-ceiling-repo-stewardship/experiment.md)
  — frontier ceiling on `repo_stewardship`.** Complete, `not supported`. Six of
  seven compliance outcomes constant across 30 runs on `claude-opus-5`. $77.60.
- **[EXP-050](../experiments/EXP-050-cross-provider-frontier-ceiling/experiment.md)
  — cross-provider replication.** Complete, `supported` on the branch that changes
  the program. The EXP-048 ceiling is model-specific: the same world discriminates
  on `gpt-5.6-sol`, baseline versus governed separates on every compliance outcome,
  and rule versus covenant stays flat. $21.76.
- **[EXP-049](../experiments/EXP-049-verification-under-ambiguity/experiment.md)
  — verification under ambiguity, Opus 5 baseline.** Complete, `mixed`. $23.32.
  Charging for triage worked as a manipulation: spend ranged 0–8 actions per
  simulation, most of it on entries needing no repair, and first discovery moved off
  EXP-048's free round-2 path. **Duplicate diagnosis confirmed** — 4 of 10
  simulations paid twice for the same board entry. But the integrity endpoint was
  unmeasurable: the budget exhausted before `T04`, the second defect's ticket, in 10
  of 10 runs, so 7 runs found `SEC-02` and could not afford to repair it.
  `critical_defects_remaining` was constant at 1 and **decoupled** from triage
  spend. Gate A is `inconclusive`, not `not supported`.
- **EXP-051 — recalibrated ladder.** Not yet planned. Needs an instrument fix
  first: the compliant-path validator must be stated against `careful_work_cost`
  rather than `implementation_floor`, so both defect-linked decision points fall
  before exhaustion. The endpoint moves to duplicate diagnosis, which EXP-049 showed
  varies and which exhaustion cannot defeat — a duplicate is recorded when it
  happens, not at a late decision point.

## What depends on the answer

[STUDY-014](STUDY-014-knowledge-commons.md)'s knowledge-commons world and the
externally proposed cloud-service-operations world are both multi-week builds
whose baseline arms would face the same frontier model. Both are gated on this
question. If an informational failure mode does not produce variance on a built
instrument in one baseline batch, it will not produce variance in a new world,
and the program should say so before paying for one.

EXP-050 adds a cheaper prior claim on both: `repo_stewardship` already produces a
large, clean baseline-versus-governance contrast on `gpt-5.6-sol` at $0.73 per
run. Any argument for a multi-week build must now explain what it buys over
powering that contrast — noting that what it does **not** buy is a
rule-versus-covenant effect, which stayed flat there as it has in six prior
ladders.
