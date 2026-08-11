# EXP-033 — Communication-free rules-only baseline calibration

**Status:** planned
**Date opened:** 2026-08-11
**Date closed:** —
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
  "runs": []
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

Pending.

## Outcome

Pending.

## Validity limitations

Pending.

## What it changed

EXP-032 established that rejecting a message does not remove communication as a behavioral affordance. EXP-033 makes the absence of communication structural while preserving the rules-only allocation task.

## Traps found

The allocation prompt, runtime tool schema, and generic agent protocol are all part of the treatment. A scenario cannot claim to remove communication while a universal tool list or system suffix still offers it.
