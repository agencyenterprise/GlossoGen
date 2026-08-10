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
  seed and large in the other.

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
effect from either the explicit pledge or their interaction. It identifies the
current unconditional 30-unit entry stake as a repeatable but adverse
exploratory candidate in Sonnet 5. This is not a model-general or statistically
stable effect, and its size varied sharply across two trajectories.

The next scientific choice is between replication and mechanism redesign:

- test the adverse stake direction in a second model while preserving the
  current treatment exactly; or
- open a new study of a violation-contingent stake, where personal cost is
  forfeited only when a commitment is broken, rather than paid
  unconditionally before any behavior.

These answer different questions and must use separate preregistered records.
