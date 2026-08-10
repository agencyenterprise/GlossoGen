# STUDY-004 — Pledge × personal cost

**Status:** exploratory phase complete
**Research program:** covenant-game

## Question

Does the behavioral effect attributed to the covenant come from making an
explicit pledge, from placing something personally valuable at risk, or from
the interaction between those two mechanisms?

## Why this is next

The completed bundle comparison shows that the institution can change
behavior, but every major covenant component moved together. Additional
unchanged runs can test variance, not causal mechanism. A targeted factorial
comparison is therefore the most direct way to connect the simulation evidence
to the client's pledge-and-cost research and to produce a clearer paper claim.

## Proposed design direction

Use a matched 2 × 2 design while keeping the team-production task, economic
profiles, visibility, agents, cases, audits, horizon, and outcome definitions
fixed:

| Condition | Explicit pledge | Meaningful personal cost |
|---|---:|---:|
| Control | no | no |
| Pledge only | yes | no |
| Cost only | no | yes |
| Pledge + cost | yes | yes |

The personal cost must be consequential to the agent and recoverable or
forfeitable under a preregistered rule; symbolic language alone does not count
as cost.

## Experiments

- [EXP-022 — Pledge × personal stake activation pilot](../experiments/EXP-022-pledge-personal-stake-pilot/experiment.md)
  completed a six-round Sonnet 5 pilot at seed 48. Both manipulations activated
  and the four arms retained useful effort and delivery variation.
- [EXP-023 — Fifteen-round pledge × personal stake factorial](../experiments/EXP-023-pledge-stake-factorial/experiment.md)
  completed two fresh matched seeds. The pledge main effect and interaction
  reversed sign across seeds. The personal-stake effect was negative in both:
  less inspection, fewer safe deliveries, more unsafe/non-delivery outcomes,
  and fewer correct completions, although its magnitude was nearly zero in one
  seed and large in the other. See the superseded reading below — EXP-024 shows
  those contrasts are within the instrument's noise.
- [EXP-024 — Run-to-run variance of the association baseline](../experiments/EXP-024-baseline-variance/experiment.md)
  belongs to STUDY-005 but is decision-relevant here: it measured the noise
  against which every contrast above must be read.

## Outcomes to keep separate

- hidden effort and safe delivery;
- truthful versus false effort attestation;
- completion versus safer refusal;
- promised versus transferred payment;
- client compensation and voluntary repair;
- membership continuity and productive capacity.

## Current synthesis

EXP-022 establishes that pledge and stake are real, independent, measurable
manipulations in this scenario. EXP-023 does not support a repeatable beneficial
effect from either the explicit pledge or their interaction.

**Superseded reading.** EXP-023 originally identified the unconditional 30-unit
entry stake as a repeatable adverse candidate, on the grounds that its
inspection contrast was negative at both fresh seeds.
[EXP-024](../experiments/EXP-024-baseline-variance/experiment.md) has since
measured the instrument's run-to-run noise at `s = 4.71` inspected assignments.
The EXP-023 cost contrasts are `0.32 s` at seed 49 and `1.70 s` at seed 50, and
the "same sign at two seeds" rule that promoted them agrees by chance 25% of the
time under a true zero. The adverse stake direction is therefore **underpowered,
not repeated**: it is neither established nor excluded, and it must not be
reported as a candidate effect.

This does not retract the null findings. The pledge and interaction were already
unsupported, and a noise estimate this large only reinforces that a single run
per cell could not have detected them either.

The next scientific choice is no longer between replicating and redesigning the
stake. At 23 replicates per arm, both options cost roughly `$160` per arm while
remaining confined to one seed and one model, so neither is authorized. The
mechanism question stays open and waits for either a materially larger expected
effect or a cheaper measurement:

- a cost manipulation matched to the human study's form — 10% of realized order
  revenue, forfeited rather than banked into the bond — which differs from the
  tested treatment in both timing and proportionality and may produce a larger
  effect;
- a violation-contingent forfeiture, which the collaborating human trust-game
  design cannot test at all because a single round contains no detectable
  violation;
- an outcome with a smaller noise term than inspection counts, if one can be
  defined without collapsing the separate alignment outcomes.

Any successor must state its target effect size and the replicate count that
resolves it, using the noise terms recorded in
[STUDY-005](STUDY-005-measurement-resolution.md), before launching.
