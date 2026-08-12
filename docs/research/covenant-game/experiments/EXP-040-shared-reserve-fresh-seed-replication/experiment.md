# EXP-040 — Shared reserve fresh-seed replication

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
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
  "runs": [
    {"role": "no_group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499105", "event_log_sha256": "fa563a7eaf904b278f279e96dd8612e5bcf63c91378da334f9bc4b39dd49e041", "resolved_config_sha256": "1d83b97da52e502d083665238a49b0df72cd961abbce779ffad85388c84ba0c8", "completed": true, "total_cost_usd": 0.41545180000000004},
    {"role": "no_group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499109", "event_log_sha256": "781c1b0a91902f0acff049c4a8681e81a48ba8c9acfcbef64c2bcce9f642dca4", "resolved_config_sha256": "1d83b97da52e502d083665238a49b0df72cd961abbce779ffad85388c84ba0c8", "completed": true, "total_cost_usd": 0.43796540000000006},
    {"role": "no_group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499110", "event_log_sha256": "467fb6a4a7eb3dad8b22b82eb28332f2fb9a9424db85e20fd4b88d0c05bf9205", "resolved_config_sha256": "1d83b97da52e502d083665238a49b0df72cd961abbce779ffad85388c84ba0c8", "completed": true, "total_cost_usd": 0.4523778},
    {"role": "group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499107", "event_log_sha256": "a00e6db58285bbceede6611c411b13ec868b919be2a092b9819ab321658a81a1", "resolved_config_sha256": "948ed2629d8b789e9f468ecbc14e6ec1a54c613ba96064c8a70d53dabbff3572", "completed": true, "total_cost_usd": 0.47151070000000006},
    {"role": "group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499112", "event_log_sha256": "39007137a5c22fce16b524d47c3012e77d0d8bd080ddebf998fda1a8d299eed4", "resolved_config_sha256": "948ed2629d8b789e9f468ecbc14e6ec1a54c613ba96064c8a70d53dabbff3572", "completed": true, "total_cost_usd": 0.4062614},
    {"role": "group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499113", "event_log_sha256": "b5045574f7fa5fead12d03a022e6e21d9654471c34d9a1718312b6fc0813710e", "resolved_config_sha256": "948ed2629d8b789e9f468ecbc14e6ec1a54c613ba96064c8a70d53dabbff3572", "completed": true, "total_cost_usd": 0.43364909999999995},
    {"role": "pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499103", "event_log_sha256": "b491b371bb618e88adb776a6b58d9c4f1f2472d15cdd48cacec5571b9c5f8572", "resolved_config_sha256": "d3459ba7055b7b5e41eabea866587eaf1ed74c74239f20ddd7a2bdbbf8e9f31d", "completed": true, "total_cost_usd": 0.44631030000000005},
    {"role": "pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499111", "event_log_sha256": "09e3ef3134139ab8c536afb34b079fa1b7ff5d3555a56ba7fcf37280173a59b7", "resolved_config_sha256": "d3459ba7055b7b5e41eabea866587eaf1ed74c74239f20ddd7a2bdbbf8e9f31d", "completed": true, "total_cost_usd": 0.4425924},
    {"role": "pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499114", "event_log_sha256": "e47ab38caef9dd65bd4a077360a4c458ac7dbbaaaadc4b1051072dd9a29159cb", "resolved_config_sha256": "d3459ba7055b7b5e41eabea866587eaf1ed74c74239f20ddd7a2bdbbf8e9f31d", "completed": true, "total_cost_usd": 0.5006026},
    {"role": "costly_pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499104", "event_log_sha256": "9b491483fa6c1db764e751f5dc785a005b844dbd1734241fb97cb82f8e79aa41", "resolved_config_sha256": "503a9e491622e968979f2c46a0ac0b22bce036b83d9f2fa11e27ce872564e9e5", "completed": true, "total_cost_usd": 0.383527},
    {"role": "costly_pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499106", "event_log_sha256": "efe392f514d4d678d6f34339482c87036857b057ff270fee6a8a9fb16469ec61", "resolved_config_sha256": "503a9e491622e968979f2c46a0ac0b22bce036b83d9f2fa11e27ce872564e9e5", "completed": true, "total_cost_usd": 0.4775513},
    {"role": "costly_pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786499108", "event_log_sha256": "18dc4124d998ea64a4d209ffebaf0ccb46ce3e7d86314c13ac6d96d4e16d17d0", "resolved_config_sha256": "503a9e491622e968979f2c46a0ac0b22bce036b83d9f2fa11e27ce872564e9e5", "completed": true, "total_cost_usd": 0.42575300000000005}
  ]
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

All twelve trajectories ended with authoritative `simulation_ended` events and
remained active through both claims. Exposure checks passed: each group, pledge,
and costly-pledge run published its group setup; all twelve offered pledge
decisions were public affirmations; and the six costly-pledge affirmations each
recorded the real 2.1-unit deduction (12.6 units in total). No group run carried
a group setup or pledge event.

The behavioural candidate from seed 74 did not repeat. Across the 96 possible
provider-round decisions in each arm, no group recorded 95 contributions, zero
retentions, and one `no_decision`; group recorded 94/0/2; pledge 92/0/4; and
costly pledge 93/0/3. Every one of the 24 scheduled claims across the batch was
paid and all twelve services reached the hidden horizon. Thus both the retention
outcome and service-continuity outcome are at a ceiling in this seed.

The event-derived totals were generated by
[`summarize_seed75.py`](analysis/summarize_seed75.py), which reads the twelve
recorded JSONL logs and counts action, exposure, cost, settlement, and canonical
completion events. The batch API cost was `$5.2935528`.

## Outcome

**Not supported.** The predeclared fresh-seed replication gate did not pass:
public pledge and costly pledge did not have lower retention than the no-group
or group arms because none of the arms retained in this seed. The result is a
ceiling/non-replication, not evidence that pledge has no effect in every shared
reserve environment.

## Validity limitations

- The shared seed is fixed within arms but LLM trajectories remain stochastic.
  Three trajectories per arm do not establish a precise effect size or
  model-family generality.
- Seed 75 produced universal contribution conditional on acting. Because it
  offered no retention variation, it cannot estimate a pledge-specific effect;
  missed actions are not equivalent to intentional retention.
- Service continuity is also at a ceiling, so the current fixed claim schedule
  cannot distinguish whether a commitment improves repair or resilience here.
- The costly-pledge arm remains an entry-cost treatment, not a full covenant;
  it contains no forfeiture, audit, expulsion, replacement, or repair rule.

## What it changed

The seed-74 pledge candidate is now classified as seed- or trajectory-specific
under this instrument, rather than as a repeated effect. Do not add another
unchanged seed. The next decision is whether to introduce one preregistered,
stronger shared-reserve stressor that preserves the clean four-arm ladder while
creating real opportunities for deliberate retention and an uncovered claim.

## Traps found

- A matched fresh seed can legitimately remove the behavioral variation found
  at the first seed. That is a non-replication, not a failure to be averaged
  away by more rounds within the same trajectory.
- `no_decision` must remain separate from `retain`: it was the only source of
  non-contribution in this batch and does not establish intentional free-riding.
