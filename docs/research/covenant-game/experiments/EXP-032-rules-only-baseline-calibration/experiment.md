# EXP-032 — Rules-only baseline calibration

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
  "experiment_id": "EXP-032",
  "base_commit": "26c8168a6a8ebe1c3d8bf909211080db6e16d03f",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-032-rules-only-baseline-calibration/configs/no-group.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-032-rules-only-baseline-calibration/configs/no-group.json", "launch_path": "docs/research/covenant-game/experiments/EXP-032-rules-only-baseline-calibration/configs/no-group.json", "sha256": "d9a0d919680b6fd888afd41cef3503e0e61af896225e9ca60e0226e52e5013df"}
  ],
  "runs": [
    {"role": "rules_only_preflight_1", "included": false, "reason": "Cancelled after the runtime exposed send_message and an agent attempted coordination; the environment did not meet the preregistered no-free-text requirement.", "run_dir": "runs/joint_commitment/1786483796", "event_log_sha256": "f0a7fca8ab2feaf8c98946a4dcd7b2d940dcb7ded3e2daa0f487b84f60fc5fcb", "resolved_config_sha256": "8bb703df7c7ba2d7e7e996ddb9b97ee52e75c22f06e4d10ceff3e3407c9f11fe", "completed": false},
    {"role": "rules_only_preflight_2", "included": false, "reason": "The runtime exposed send_message and a universal communication prompt, so this completed trajectory does not meet the preregistered no-free-text environment.", "run_dir": "runs/joint_commitment/1786483798", "event_log_sha256": "6b4791692bc1e7c0116c08d957f03441bbadac6e1383000a804a11b40d352829", "resolved_config_sha256": "8bb703df7c7ba2d7e7e996ddb9b97ee52e75c22f06e4d10ceff3e3407c9f11fe", "completed": true, "total_cost_usd": 0.1791856},
    {"role": "rules_only_preflight_3", "included": false, "reason": "Cancelled after the runtime exposed send_message and an agent attempted coordination; the environment did not meet the preregistered no-free-text requirement.", "run_dir": "runs/joint_commitment/1786483799", "event_log_sha256": "a0176e185ae40f53834e50afa0baca6a1892ee74896c2a19486611a48c7379af", "resolved_config_sha256": "8bb703df7c7ba2d7e7e996ddb9b97ee52e75c22f06e4d10ceff3e3407c9f11fe", "completed": false}
  ]
}
-->

## Question

With only the operational 7→21 allocation rules and no prior-round action
history in the provider prompt, do three independent Claude Sonnet 5 no-group
trajectories show both transfer and retention, or another universal action
floor/ceiling?

## Expected decision

This is an instrument calibration, not a covenant comparison. One full run is
the independent unit; the sixteen decisions within it are repeated interaction
between the same two providers.

| Preregistered observation | Decision triggered |
|---|---|
| A run lacks `simulation_ended`, lacks all 32 decisions, or accepts a free-text message | Exclude the affected run, repair the instrument, and do not interpret behavior. |
| All 96 provider decisions are `remit` | Close as a repeated remittance ceiling. Do not launch the group/pledge ladder; revise the allocation task rather than adding prompt qualifications. |
| All 96 provider decisions are `retain` | Close as a repeated retention floor. Do not launch the group/pledge ladder; revise the allocation task rather than adding prompt qualifications. |
| At least one completed decision is `remit` and at least one is `retain` | Close as a behaviorally variable rules-only baseline. Preregister a four-arm comparison with at least three fresh trajectories per arm; do not infer an arm effect from this calibration. |

## Design

EXP-032 repeats the no-group baseline three times with Claude Sonnet 5 through
Anthropic and the same environmental seed (71). Round 1 is setup; rounds 2–17
give each of two providers the identical choice to transfer 7 units to a client
account while retaining 14, or retain all 21. The horizon is undisclosed.

The code is fixed at `26c8168`. Relative to EXP-031, the system prompt and
round injection now state only the allocation mechanics. They omit ownership,
protection, joint-outcome labels, descriptions of absent mechanisms, cumulative
earnings, and prior-round actions. No provider-facing group registry, pledge,
entry cost, audit, bond, or writable channel is present in this condition.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Seed / replicas | 71 / three fresh trajectories |
| Rounds / decision opportunities | 17 / 16 per provider |
| Providers | 2 |
| Allocation | transfer 7 and retain 14, or retain 21 |
| Group / pledge / entry cost | none / none / none |
| Audits / penalties / writable messages | none / none / rejected |

No fork, resume, replacement, or model override is used. The shared seed fixes
the non-model environment but does not make model sampling deterministic.

## Outcomes inspected

From authoritative `joint_commitment_*` events, inspect per run:

- transfer and retention counts;
- completed joint outcomes;
- matching structured public records;
- accepted free-text messages, completion status, runtime, and API cost.

The primary criterion is whether both actions occur anywhere in the three runs.
This does not establish an institutional, human, or model-general effect.

## Provenance

- Base commit: `26c8168a6a8ebe1c3d8bf909211080db6e16d03f`.
- Worktree dirty at planning: `true`, because this planned record and unrelated
  pre-existing untracked files are present; the instrument revision and focused
  tests are committed at the base SHA.
- The JSON is bundled under this experiment and will be launched directly from
  that path. Its SHA-256 is listed in the machine-readable block.
- Each listed command will be launched three times without fork, resume,
  replacement, or model override. The shared seed controls the non-model
  environment but not stochastic model sampling.

## Result

The three launch attempts were stopped in the first round. Although the joint
commitment scenario rejected free-text messages, the shared runtime still
advertised `send_message` and its universal communication protocol instructed
the agents to use it. An agent consequently attempted coordination before any
allocation decision. None of the attempts is included as behavioral evidence.

The repair makes communication an environmental constraint: this scenario now
has no channels, its providers are registered with communication disabled, the
MCP tool list excludes all free-text tools, and the silent runtime protocol
only permits notifications and structured decisions.

## Outcome

**Invalid.** The preflight did not provide the no-communication environment
specified in the record. It cannot answer the calibration question.

## Validity limitations

- These cancelled attempts have no authoritative completion event or canonical
  final cost, so they are excluded from both behavioral and cost summaries.
- The repair changes runtime tool exposure, so a fresh preregistered record is
  required before launching the intended three-replica calibration.

## What it changed

This preflight exposed a runtime-level source of treatment contamination. Its
successor tests the same rules-only allocation prompt with free-text
communication unavailable rather than merely prohibited in text. It cannot
itself test public group identity, pledge, or costly pledge.

## Traps found

EXP-030's universal remittance and EXP-031's extreme between-run variation show
that prompt wording and injected shared history can dominate the behavior being
measured. The absence of an institutional mechanism must be represented by the
environment, not narrated to the provider.

Rejecting an attempted message is not equivalent to making communication
unavailable: the exposed tool schema and universal protocol can themselves
alter behavior.
