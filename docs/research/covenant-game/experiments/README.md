# Covenant Game experiment records

This is the chronological record index for the
[Covenant Game research program](../README.md). One record represents one
decision-relevant calibration, pilot, comparison, replication, stress test, or
ablation. A record may contain several runs; the 21 completed records below are
not 21 independent studies.

Entries are written **before** the run (question, expected decision, design)
and completed after it. Negative and inconclusive results are recorded with the
same care as positive ones — an experiment that rules something out saves the
next person from repeating it.

For account or researcher transition, start with the
[Covenant Game research handoff](../../../handoffs/COVENANT-GAME-HANDOFF.md)
and its
[new-account resume prompt](../../../handoffs/NEW-ACCOUNT-RESUME-PROMPT.md).

## Study map

- [STUDY-001 — Instrument development](../studies/STUDY-001-instrument-development.md):
  EXP-001–007.
- [STUDY-002 — Full institutional bundle](../studies/STUDY-002-institutional-bundle.md):
  EXP-008–013 and EXP-020–021.
- [STUDY-003 — Enforcement and resilience](../studies/STUDY-003-enforcement-resilience.md):
  EXP-014–019.
- [STUDY-004 — Pledge × personal cost](../studies/STUDY-004-pledge-cost-mechanism.md):
  EXP-022–023 complete.
- [STUDY-005 — Measurement resolution](../studies/STUDY-005-measurement-resolution.md):
  EXP-024 complete.
- [STUDY-006 — Human-parallel commitment](../studies/STUDY-006-human-parallel-commitment.md):
  EXP-025 complete; fixed action framing hit a joint-inspection floor.
- [STUDY-007 — Repeated trust-game replication](../studies/STUDY-007-repeated-trust-game.md):
  EXP-026 complete; trust moved under covenant, reciprocity was invariant.
- [STUDY-008 — Joint commitment alignment](../studies/STUDY-008-joint-commitment-alignment.md):
  design complete; EXP-027 is reserved for instrument calibration.

Working noise terms for sizing any new experiment in this program, from
[EXP-024](EXP-024-baseline-variance/experiment.md): `s = 4.71` inspected
assignments, `1.60` safe deliveries, `1.51` unsafe deliveries, per run at a
fixed seed on Claude Sonnet 5. State a target effect size and the replicate
count that resolves it before launching.

## Chronological index

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
| [EXP-018](EXP-018-graded-enforcement-pilot/experiment.md) | graded enforcement after an experienced failure | complete | operational preservation supported; alignment-policy effect requires replication | $5.03 |
| [EXP-019](EXP-019-graded-enforcement-replication/experiment.md) | graded-enforcement shared-prefix replication | complete | capacity and immediate compliance replicated in 2/2 new trajectories | $8.90 |
| [EXP-020](EXP-020-cross-model-compatibility/experiment.md) | four-model compatibility pass on the frozen institutional comparison | complete | all four models compatible; behavioral response heterogeneous and requires paired-seed replication | $167.00 |
| [EXP-021](EXP-021-cheap-model-seed-replication/experiment.md) | two fresh paired seeds across Sonnet 5, Terra, and Sol | complete | safety contrast repeated 2/2 for Terra and Sol but 0/2 for Sonnet | $42.62 |
| [EXP-022](EXP-022-pledge-personal-stake-pilot/experiment.md) | pledge × personal stake activation pilot | complete | supported: both manipulations activated with useful variation | $5.19 |
| [EXP-023](EXP-023-pledge-stake-factorial/experiment.md) | fifteen-round pledge × personal stake factorial | complete | personal stake repeated as an adverse effort/safety candidate; pledge and interaction did not repeat | $27.18 |
| [EXP-024](EXP-024-baseline-variance/experiment.md) | run-to-run variance of the association baseline at a fixed seed | complete | supported: `s = 4.71` inspections from identical inputs; kill criterion fired, cost redesign not authorized | $21.26 |
| [EXP-025](EXP-025-human-parallel-commitment-pilot/experiment.md) | human-parallel commitment instrument pilot | complete | not supported: primary joint-inspection outcome remained at its floor | $2.14 |
| [EXP-026](EXP-026-repeated-trust-game-pilot/experiment.md) | repeated trust-game human-parallel pilot | complete | inconclusive: trust contrast met its threshold but reciprocity was invariant | $1.21 |

Total API spend logged: **$419.37** (plus $0.73 in phase-4 smoke tests and
interrupted/invalid team-production preflights not logged individually).

**Cycle 1 is closed.** C0 → C1 → C2 on `gpt-5.4`, seed 42, one replica each. The
pivot criterion that fired is recorded in EXP-003: C2 differs from C1 only in
effort and cost, never in an alignment property, because one paid count yields
certainty and leaves the covenant no problem to solve.

## Creating the next record

The next available ID is `EXP-027`. Before launching, use the
[`record-experiment`](../../../../.agents/skills/record-experiment/SKILL.md)
skill to create a program- and study-scoped bundle, freeze its configs, record
the decision rule, and validate the planned record. Do not copy an old flat
record as a template; new records use the machine-checked v2 schema.

## Conventions

- **Use the same seed within matched arms**, so the case sequence and audit
  draws are identical. Use fresh preregistered seeds for replication.
- **Do not treat a single replica as evidence of stability.** 15 rounds is one
  trajectory of interacting agents, not 15 independent observations. The
  independent unit is the run.
- **Only `simulation_ended` means a run finished.** Round counts do not.
- Run directories are gitignored. Paths recorded here are the pointer to the raw
  data on the machine that produced it; the JSONL event log is the canonical
  record and every number in these entries is recomputable from it.

## Historical recalibration budget

This rule applied to the first counter–verifier cycle. It was adopted after
EXP-002 to prevent open-ended tuning of an environment until it produced a
desired result:

1. Finish the current condition set (C0, C1, C2).
2. Allow **at most one** significant environment revision.
3. If a ceiling, absent measurement opportunities, or C1 ≈ C2 persist after that
   revision, pivot the scenario.
4. Record the reason for the pivot **before** starting the next scenario.
