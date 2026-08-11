# EXP-033 — Communication-free rules-only baseline calibration

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-008 — Joint commitment alignment
**Role:** calibration

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-008",
  "experiment_role": "calibration",
  "experiment_id": "EXP-033",
  "base_commit": "f4ddc3d1f9bfd167466d27f9b493dc82559aba18",
  "worktree_dirty": true,
  "commands": ["VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-033-communication-free-baseline-calibration/configs/no-group.json"],
  "configs": [{"path": "docs/research/covenant-game/experiments/EXP-033-communication-free-baseline-calibration/configs/no-group.json", "launch_path": "docs/research/covenant-game/experiments/EXP-033-communication-free-baseline-calibration/configs/no-group.json", "sha256": "d9a0d919680b6fd888afd41cef3503e0e61af896225e9ca60e0226e52e5013df"}],
  "runs": [
    {"role": "rules_only_replica_1", "included": true, "run_dir": "runs/joint_commitment/1786484935", "event_log_sha256": "125ad054efbb1bc84c7d7eb9632096b5149722d60e14b9018fdf150938f9f7a2", "resolved_config_sha256": "8bb703df7c7ba2d7e7e996ddb9b97ee52e75c22f06e4d10ceff3e3407c9f11fe", "completed": true, "total_cost_usd": 0.1208335},
    {"role": "rules_only_replica_2", "included": true, "run_dir": "runs/joint_commitment/1786484938", "event_log_sha256": "31d86dc018e3568a0615cd52f1ce35d7b824bb324ae3bd94ee58de88fbe7ec94", "resolved_config_sha256": "8bb703df7c7ba2d7e7e996ddb9b97ee52e75c22f06e4d10ceff3e3407c9f11fe", "completed": true, "total_cost_usd": 0.1202009},
    {"role": "rules_only_replica_3", "included": true, "run_dir": "runs/joint_commitment/1786484939", "event_log_sha256": "8d7d893dbafaff722a844d4861b25426999960f875b7566a46a44e3ababc3b52", "resolved_config_sha256": "8bb703df7c7ba2d7e7e996ddb9b97ee52e75c22f06e4d10ceff3e3407c9f11fe", "completed": true, "total_cost_usd": 0.1185255}
  ]
}
-->

## Question

With only the operational 7→21 allocation rules, no prior-round action history, and no free-text communication tool or channel, do three independent Claude Sonnet 5 no-group trajectories show both remittance and retention, or another universal action floor or ceiling?

## Expected decision

This is instrument calibration, not a covenant comparison. A full run is the independent unit; the sixteen decisions within it are repeated interaction between the same two providers.

| Preregistered observation | Decision triggered |
|---|---|
| A run lacks `simulation_ended`, lacks all 32 decisions, exposes a free-text communication tool or channel, or accepts a free-text message | Exclude the affected run, repair the instrument, and do not interpret behavior. |
| All 96 provider decisions are `remit` | Close as a repeated remittance ceiling. Do not launch the group/pledge ladder; revise the allocation task. |
| All 96 provider decisions are `retain` | Close as a repeated retention floor. Do not launch the group/pledge ladder; revise the allocation task. |
| At least one completed decision is `remit` and at least one is `retain` | Close as a behaviorally variable communication-free baseline. Preregister a four-arm comparison with at least three fresh trajectories per arm; do not infer an arm effect from this calibration. |

## Design

Three fresh no-group trajectories use Claude Sonnet 5 through Anthropic and environmental seed 71. Round 1 is setup. In rounds 2–17, each of two providers chooses to remit 7 units to a client account and retain 14, or retain all 21. The horizon is undisclosed.

The provider prompt states only allocation rules. It omits ownership, protection, joint-outcome labels, absent mechanisms, cumulative earnings, and prior-round actions. The runtime exposes `read_notifications` and the structured allocation action only. It provides no channel, `send_message`, `read_channel`, `list_channels`, or `get_channel_members` tool.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Seed / replicas | 71 / three fresh trajectories |
| Rounds / decision opportunities | 17 / 16 per provider |
| Providers | 2 |
| Allocation | transfer 7 and retain 14, or retain 21 |
| Group / pledge / entry cost | none / none / none |
| Audits / penalties | none / none |
| Free-text communication | unavailable |

No fork, resume, replacement, or model override is used. The shared seed fixes the non-model environment but not stochastic model sampling.

## Outcomes inspected

From authoritative `joint_commitment_*` events, inspect remittance and retention counts, completed joint outcomes, matching structured public records, registered channel IDs and tool names, accepted free-text messages, completion status, runtime, and API cost.

The primary criterion is whether both actions occur anywhere in the three runs. This does not establish an institutional, human, or model-general effect.

## Provenance

- Base commit: `f4ddc3d1f9bfd167466d27f9b493dc82559aba18`.
- Worktree dirty at planning: `true`, because this planned record and unrelated pre-existing untracked files are present; the focused instrument repair and tests are committed at the base SHA.
- The JSON is bundled under this experiment and will be launched directly from that path. Its SHA-256 is in the machine-readable block.
- Each command will run three times without fork, resume, replacement, or model override. The shared seed controls the non-model environment but not model sampling.

## Result

All three trajectories ended with authoritative `simulation_ended` events and
all 32 decisions per run. Every provider selected `remit`: 96 of 96 recorded
decisions remitted, and all 48 joint client outcomes were safe. No run recorded
a `message_sent` event.

The registered environment confirms the intended repair: both providers had an
empty `channel_ids` list, `communication_enabled: false`, and exactly two
visible tools, `read_notifications` and `submit_client_reserve_decision`.
Total API cost was `$0.3595599`.

## Outcome

**Not supported.** The behaviorally variable baseline gate did not activate:
the rules-only, communication-free allocation task still produced a repeated
practical remittance ceiling. The four-arm group/pledge ladder is not
authorized on this instrument.

## Validity limitations

- The instrument validly removes free-text communication, but a valid
  implementation does not guarantee a behaviorally informative measure.
- Three stochastic trajectories at one model and seed establish this local
  ceiling gate only; they do not show human behavior or a model-general norm.
- The result does not test group identity, pledge, cost, audit, or covenant
  effects because none of those arms was launched.

## What it changed

EXP-032 established that rejecting a message does not remove communication as a behavioral affordance. EXP-033 made the absence of communication structural while preserving the rules-only allocation task. Its ceiling result means the next study must change the behavioral decision rather than add covenant arms.

## Traps found

The allocation prompt, runtime tool schema, and generic agent protocol are all part of the treatment. A scenario cannot claim to remove communication while a universal tool list or system suffix still offers it. Conversely, removing that affordance does not itself create meaningful behavioral variation.
