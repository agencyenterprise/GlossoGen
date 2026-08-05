# Experiment log

One file per experiment. Entries are written **before** the run (question,
expected decision, design) and completed after it. Negative and inconclusive
results are recorded with the same care as positive ones — an experiment that
rules something out saves the next person from repeating it.

## Index

| ID | Experiment | Status | Outcome | Cost |
|---|---|---|---|---|
| [EXP-001](EXP-001-c0-calibration.md) | bonded_counter C0 — strategic calibration | complete | supported | $8.85 |
| [EXP-002](EXP-002-c1-no-covenant.md) | bonded_counter C1 — no covenant (control) | complete | supported, with two design problems found | $18.44 |
| [EXP-003](EXP-003-c2-full-covenant.md) | bonded_counter C2 — full covenant (treatment) | complete | changes behaviour; **not supported** that it improves any alignment outcome | $10.92 |
| [EXP-004](EXP-004-team-production-calibration.md) | bonded team production — instrument calibration | complete | not supported: first pilot hit an effort ceiling; recalibration hit an effort floor | $6.39 |
| [EXP-005](EXP-005-operational-parity-calibration.md) | bonded team production — operational-parity calibration | complete | not supported: equal team revenue still produced an effort and accuracy floor | $2.69 |
| [EXP-006](EXP-006-lead-accountability-calibration.md) | bonded team production — lead-accountability calibration | complete | not supported: full lead refund produced an effort and accuracy ceiling | $2.39 |
| [EXP-007](EXP-007-private-team-production-pilot.md) | private team production with varied temptation | complete | execution gate passed; extension shows directional completion and payment contrast | $4.66 |
| [EXP-008](EXP-008-sonnet-team-production-replication.md) | Sonnet replication of private team production | complete | directional cross-model replication; more effort and no incorrect deliveries, with one covenant completion failure | $6.48 |
| [EXP-009](EXP-009-sonnet-seed-replication.md) | Sonnet paired replication at seeds 43 and 44 | complete | mixed replication; strict enforcement repaired the client but collapsed the covenant institution | $7.71 |
| [EXP-010](EXP-010-population-redundancy.md) | six-provider redundancy after enforcement | complete | population changes behavior; post-enforcement recovery not exercised | $7.76 |
| [EXP-011](EXP-011-controlled-enforcement-challenge.md) | controlled enforcement and recovery challenge | complete | one-member covenant enforcement recovered; controlled gate was avoided | $11.88 |
| [EXP-012](EXP-012-hidden-horizon-stability-pilot.md) | hidden-horizon stability pilot | complete | covenant improves compliance and continuity, with a substantial effort-cost trade-off | $11.15 |
| [EXP-013](EXP-013-hidden-horizon-seed46-replication.md) | hidden-horizon seed-46 replication | complete | compliance and continuity contrast replicated, with the same effort-cost trade-off | $11.22 |
| [EXP-014](EXP-014-opportunist-invasion-shock.md) | opportunist invasion shock | complete | stressor unactivated; both replacements complied, so containment was not tested | $11.79 |
| [EXP-015](EXP-015-scripted-violation-recovery.md) | scripted violation and recovery | complete | activation gate failed; explicit violation prompt was ignored | untracked |
| [EXP-016](EXP-016-external-violation-recovery.md) | confirmed external violation and recovery | complete | enforcement and operational recovery supported; repair response not interpretable | $4.54 |
| [EXP-017](EXP-017-population-loss-dose-response.md) | covenant population-loss dose response | complete | two-member loss contained; minimum population is viable but fragile and collapsed in 1/2 trajectories | $17.16 |
| [EXP-018](EXP-018-graded-enforcement-pilot.md) | graded enforcement after an experienced failure | complete | operational preservation supported; alignment-policy effect requires replication | $5.03 |
| [EXP-019](EXP-019-graded-enforcement-replication.md) | graded-enforcement shared-prefix replication | complete | capacity and immediate compliance replicated in 2/2 new trajectories | $8.90 |

Total API spend logged: **$157.96** (plus $0.73 in phase-4 smoke tests and
interrupted/invalid team-production preflights not logged individually).

**Cycle 1 is closed.** C0 → C1 → C2 on `gpt-5.4`, seed 42, one replica each. The
pivot criterion that fired is recorded in EXP-003: C2 differs from C1 only in
effort and cost, never in an alignment property, because one paid count yields
certainty and leaves the covenant no problem to solve.

## Template

Copy this for a new entry. Fill everything above `Result` **before launching**.

```markdown
# EXP-NNN — <title>

**Status:** planned | running | complete | invalid
**Date opened:** YYYY-MM-DD
**Date closed:** YYYY-MM-DD

## Question
What this experiment decides. One sentence.

## Expected decision
What we will do differently depending on how it comes out. Written before the
run, so the result cannot retro-fit the question.

## Design
Scenario, condition, the knobs that differ from the comparison arm, model,
provider, seed, rounds, replicas. State what is held constant.

## Provenance
- Commit: `<sha>` — `<subject>`
- Config: path to the preset, plus any inline overrides verbatim
- Runs: run directory paths

## Result
The numbers. No interpretation in this section.

## Outcome
supported | not supported | inconclusive

## Validity limitations
What this run cannot establish. Replica count, model coverage, seeds, ceilings,
confounds.

## What it changed
What we do differently because of this. If nothing changed, say so and say why —
either the question was not decision-relevant, or the result was ignored.

## Traps found
Things that broke, misled, or cost time. The field with the highest long-run
value: it is what stops the same mistake twice.
```

## Conventions

- **Canonical seed is 42** across matched arms, so the case sequence and audit
  draws are identical and replicas measure model stochasticity on the same
  workload.
- **Do not treat a single replica as evidence of stability.** 15 rounds is one
  trajectory of four interacting agents, not 15 independent observations. The
  independent unit is the run.
- **Only `simulation_ended` means a run finished.** Round counts do not.
- Run directories are gitignored. Paths recorded here are the pointer to the raw
  data on the machine that produced it; the JSONL event log is the canonical
  record and every number in these entries is recomputable from it.

## Recalibration budget

Adopted after EXP-002 to prevent open-ended tuning of an environment until it
produces a desired result:

1. Finish the current condition set (C0, C1, C2).
2. Allow **at most one** significant environment revision.
3. If a ceiling, absent measurement opportunities, or C1 ≈ C2 persist after that
   revision, pivot the scenario.
4. Record the reason for the pivot **before** starting the next scenario.
