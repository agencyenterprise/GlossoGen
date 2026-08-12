# STUDY-012 — Contribution ladder under a non-disclosing prompt

**Status:** retired — the outcome variable was the wrong construct; see EXP-044
**Research program:** covenant-game

## Question

When the system prompt no longer discloses that conditions are being compared,
does the shared-reserve world produce provider defection, and do public group
identity, a public pledge, and a costly public pledge change it?

## Why this is a distinct study

[STUDY-009](STUDY-009-shared-reserve-commitment.md),
[STUDY-010](STUDY-010-non-computable-sufficiency.md), and
[STUDY-011](STUDY-011-public-pledge-sole-social-signal.md) are retired. Each was
built on the assumption that the first batch —
[EXP-038](../experiments/EXP-038-shared-reserve-baseline-repair/experiment.md)
and [EXP-039](../experiments/EXP-039-shared-reserve-commitment-ladder/experiment.md)
— represented the instrument's normal behaviour, and that the flatness of every
later batch needed a mechanistic explanation about the *world*. Three such
explanations were preregistered and all three were refuted: claim magnitude,
computable sufficiency, and mutual observability.

That framing was wrong in a specific way. Batch 1 recorded 12 retentions in 96
`no_group` opportunities and 27 in 96 `group` opportunities. Every batch since —
48 trajectories — recorded three retentions in total, none in a `no_group` arm.
**The control lost its defection.** No treatment can be identified against a
control pinned at zero, so EXP-040 through EXP-043 were not measuring
institutions at all; they were measuring whatever moved the baseline.

Two candidate explanations for that shift survive, and they are separable.

The first is the prompt. Every batch from EXP-037 to EXP-043 carried this
sentence in the provider system prompt:

> The same hidden claim schedule is used in every condition.

It tells the agent it is inside an experiment whose conditions are being
compared. An agent that knows it is being compared across arms has reason to
behave consistently across arms. The sentence was removed in `070a494`, along
with a general tightening of both templates.

The second is model drift. Batch 1 and the later batches ran on identical code —
verified: no diff in `src/glossogen/` between the EXP-038, EXP-039, and EXP-040
base commits — and identical knobs, since `seed` is inert in this scenario. The
only remaining uncontrolled variable is the model served by the provider between
those dates.

This study tests the first. The second is tested by re-running the original
templates at commit `e393852`, and is deliberately held in reserve as the
fallback if this study's baseline gate fails.

## What changes

Nothing in the world. [EXP-044](../experiments/EXP-044-corrected-prompt-ladder-replication/experiment.md)
launches from byte-identical copies of the EXP-038 and EXP-039 config files —
same SHA-256 hashes — with the EXP-043 disclosure knobs left at their defaults,
which reproduces batch-1 behaviour exactly. Only the rendered prompt differs,
and that difference is the manipulation.

## Outcomes

- **Defection:** `retain` actions per opportunity and trajectories carrying at
  least one retention, per arm, with the trajectory as the independent unit.
- **Service continuity:** claim coverage and terminations.
- **Pledge uptake and cost exposure:** affirm/decline decisions and recorded
  2.1-unit deductions.
- **Missed decisions:** counted separately from retentions, never merged.
- **Coordination talk:** free-form messages on the shared record, qualitative.

## Sequence and guardrails

1. [EXP-044](../experiments/EXP-044-corrected-prompt-ladder-replication/experiment.md)
   was the replication: four arms, six trajectories each, against three in
   batch 1. **Retention returned** — 32 in the two untreated arms, against three
   across the 48 trajectories of EXP-040 through EXP-043 — so batch 1
   reproduces and EXP-040 was the outlier.
2. Gate A passes literally and fails on its construct. **Every one of the 32
   retentions was slack harvesting**: none left the reserve unable to absorb a
   claim, and the agents negotiated the rotation openly on the shared record.
   Re-reading batch 1 shows the same build-hold-rebuild pattern, so `retain`
   never denoted free-riding in this study at all. Gate B fails: batch 1's
   `group` above `no_group` ordering did not survive doubling the replicas.
3. The study is therefore **retired**, and not for the reason it was opened.
   The prompt hypothesis is neither confirmed nor refuted — retention returning
   is consistent with it, but sampling variance is equally live and this batch
   cannot separate them. What the batch settled instead is that the outcome
   variable was wrong, which makes the question moot for this instrument.
4. `shared_reserve_commitment` is retired on **payoff dominance**. Contributing
   costs 7; an uncovered claim costs 21 per round for every remaining round,
   roughly 45 to 1 against retaining, with an undisclosed horizon so no endgame
   exists. No state in this world makes retention both tempting and risky. This
   is upstream of all three earlier retirement rationales — claim magnitude,
   computable sufficiency, and mutual observability were each downstream of it.
5. The replicated effect is that the pledge produces **literal rule-following**:
   0 retentions in 384 opportunities against 32 in 384, at lower earnings and
   identical service continuity. The same shape appears in the program's
   warehouse pilot, where the covenant condition raised effort through
   duplicated work without improving accuracy. Two unrelated instruments, one
   pattern: commitment structures increase costly compliance without changing
   outcomes.
6. Do not open a sixth batch on this world. Any successor instrument must show
   that its primary outcome can vary before a treatment ladder is built on it,
   and must classify its outcome variable against the construct it claims to
   measure — the failure that cost this study and the three before it.
7. No covenant mechanism was ever implemented here. A covenant needs a
   consequence for breaking the pledge; the `costly_pledge` arm charges an entry
   fee and imposes nothing for defecting afterwards, which is a contract. The
   two mechanisms the collaboration asked for in March — **loss of membership**
   and **probing why** agents cooperate — have never been run on this scenario
   and should be carried to whatever instrument succeeds it.
8. `seed` is inert in this scenario and reads no code path. Do not describe any
   batch here as a fresh-seed replication or draw seed-sensitivity conclusions
   from one.
9. Do not read contribution as moral alignment. The causal question is whether
   the implemented institutional exposure changes observable contribution
   persistence and service continuity under the same common-good world.
