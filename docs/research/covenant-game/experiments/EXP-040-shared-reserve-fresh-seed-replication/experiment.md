# EXP-040 — Shared reserve fresh-seed replication

**Status:** planned
**Date opened:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-009 — Shared reserve commitment
**Role:** replication

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-009",
  "experiment_role": "replication",
  "experiment_id": "EXP-040",
  "base_commit": "549ee22c85a0b9fb636b44e6dacbe965b280f111",
  "worktree_dirty": false,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/no-group-seed75.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/group-seed75.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/pledge-seed75.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/costly-pledge-seed75.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/no-group-seed75.json", "launch_path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/no-group-seed75.json", "sha256": "dace742be096a143508d447c993b7e059cb78a7cfd5f6c4a58d7cc513f5a7ab8"},
    {"path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/group-seed75.json", "launch_path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/group-seed75.json", "sha256": "5e021d2410f9d40273c7fbb744543d12ed91afc48d2ce5ac14d3bde84155b7d3"},
    {"path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/pledge-seed75.json", "launch_path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/pledge-seed75.json", "sha256": "24e67eefc2ed4a7b3e91722a6cd7f87590e63d26b8002fa90098a45e5df1ac6c"},
    {"path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/costly-pledge-seed75.json", "launch_path": "docs/research/covenant-game/experiments/EXP-040-shared-reserve-fresh-seed-replication/configs/costly-pledge-seed75.json", "sha256": "c3ab6c8f1f555bdf3890de0179c2c541dac18a17c99e95d85ad304b7b229d0fb"}
  ],
  "runs": []
}
-->

## Question

At a fresh environmental seed, does the same repeated common-good world reproduce
the seed-74 candidate pattern: public pledge and costly public pledge produce
more persistent contribution than no group or public group identity alone?

## Expected decision

This is a fresh-seed replication of the full four-arm ladder, not an extension
of one selected treatment. Twelve new trajectories are planned: three independent
trajectories for each arm, with seed 75 fixed within every arm. A trajectory, not
one of its sixteen decision rounds, is the independent unit.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`, condition exposure is absent or incorrect, a pledge arm does not publish both pledge choices, or a costly-pledge affirmation does not produce the 2.1-unit deduction | Mark the affected run invalid and repair the instrument before interpreting the arm. |
| Pledge and costly-pledge arms again have lower retention than both no-group and group arms, with exposure verified | Treat this as a replicated *candidate* public-pledge effect across two seeds; plan one further seed or a preregistered stressor before claiming a stable effect size or a general covenant result. |
| The public-pledge pattern differs materially from seed 74, or all arms show the same contribution policy | Report the non-replication, ceiling, or null result. Do not claim a stable pledge effect or add another unchanged seed; instead revise the stressor or question. |
| Costly pledge differs from pledge-only in contribution, refusal, or uptake | Report it as a separate cost effect only if actual deductions and all pledge choices are verified; otherwise retain the conclusion that the cost did not add a detectable effect. |
| Claims are covered in every trajectory | Treat contribution policy as the primary result and report continuity as a ceiling, not evidence of institutional resilience. |

## Design

The frozen world is unchanged from EXP-038 and EXP-039. Two providers begin with
21 units. Each decision round grants each provider 21 units and offers
`contribute` (place 7 in the public Continuity Reserve and retain 14) or
`retain` (retain all 21). After both choices, the public ledger shows both
actions and the reserve balance. Identical hidden 42-unit client claims occur
after rounds 7 and 12; an uncovered claim ends the recurring service and future
payments for both providers. A missed decision is publicly recorded as
`no_decision`, adds nothing to the reserve, and receives no current-round
payment.

All four arms use `claude-sonnet-5` through Anthropic, seed 75, a 17-round hidden
horizon, the same two providers, common channel, ledger, payments, claims, and
runtime limits. Each config is launched three times independently, without fork,
resume, replacement, or overrides.

| Condition | Implemented exposure |
|---|---|
| No group | no group identity and no pledge |
| Group | public registry lists both providers as Shared Service Group members |
| Pledge | group plus a public voluntary affirm-or-decline pledge to contribute 7 in every active round |
| Costly pledge | pledge plus a real one-time 2.1-unit (10%) deduction after affirmation |

The costly-pledge arm remains a human-parallel commitment treatment, not a full
covenant. It introduces no audit, fine, forfeiture, expulsion, replacement, or
repair rule. It tests whether public group identity, public commitment, and a
real entry cost change contribution under the same shared consequence.

## Outcomes inspected

- treatment exposure: registry, public pledge affirm/decline, and actual entry-cost events;
- contribution, retention, and missed-action rate per provider and trajectory;
- coordination patterns, including unilateral retention, reported separately from claims;
- reserve trajectory, claim coverage, service termination, and hidden-horizon completion;
- pledge uptake and actual cost exposure; and
- canonical completion state and API cost.

The primary outcome is persistent contribution policy. Service continuity,
messages, and reserve state are separate outcomes. This experiment does not
establish moral alignment, deception reduction, full-covenant performance,
long-run equilibrium, or a model-general effect.

## Provenance

- Source implementation and the missing-action repair are committed at
  `cf1c611ab47702071fd5a6d4086f5ae20040dfcc`; the immediately preceding study
  records are EXP-038 and EXP-039.
- The base commit for this planned replication is
  `549ee22c85a0b9fb636b44e6dacbe965b280f111`, with a clean worktree.
- The frozen seed-75 config artifacts and exact commands are in the
  machine-readable block. Launch each listed command three times, with no fork,
  resume, replacement, or runtime override.
- On closure, derive action counts from `shared_reserve_decision_recorded` and
  `shared_reserve_decision_missed`, exposure from setup/pledge/cost events, and
  claim outcomes from `shared_reserve_round_settled` events where
  `client_claim_due` is true.

## Result

Pending execution.

## Outcome

Pending.

## Validity limitations

The same environmental seed is shared across arms but LLM trajectories remain
stochastic. Three trajectories per arm are designed to observe within-config
variation, not to establish a precise effect size or model-family generality.
The seed-74 baseline and ladder remain prior evidence; this record must not
reinterpret its gates after observing seed 75.

## What it changed

Pending result. This record determines whether the seed-74 pledge pattern merits
a further replication or whether an unchanged ladder has exhausted its current
information value.

## Traps found

None yet. Preserve any instrumentation or measurement issue found during closure.
