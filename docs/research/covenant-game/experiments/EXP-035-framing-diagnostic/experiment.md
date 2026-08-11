# EXP-035 — Professional-service versus neutral-allocation framing diagnostic

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
  "experiment_id": "EXP-035",
  "base_commit": "c087b1016080529e439b8addb1be141cdb9d98ec",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-035-framing-diagnostic/configs/professional-service.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-035-framing-diagnostic/configs/neutral-allocation.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-035-framing-diagnostic/configs/professional-service.json", "launch_path": "docs/research/covenant-game/experiments/EXP-035-framing-diagnostic/configs/professional-service.json", "sha256": "2ed0b78abdc7a315b2f8120b7f3c6372e58bcaccc9f80f0412bb687d97ad13d4"},
    {"path": "docs/research/covenant-game/experiments/EXP-035-framing-diagnostic/configs/neutral-allocation.json", "launch_path": "docs/research/covenant-game/experiments/EXP-035-framing-diagnostic/configs/neutral-allocation.json", "sha256": "dc1f864c146f43960cd9f2fb353687c6fcb3f6353d9e3b2ca570130d43d25699"}
  ],
  "runs": [
    {"role": "professional_service_replica_1", "included": true, "run_dir": "runs/joint_commitment/1786487825", "event_log_sha256": "f70d0606762dc46ff3b5049169a30b59335a0d23bda41c4e98bc4201a5ddea7d", "resolved_config_sha256": "f5ec1636199c88a81c1a4554c7efc195d02e203519e2c22d4aa2d04127fc3b69", "completed": true, "total_cost_usd": 0.2016909},
    {"role": "neutral_allocation_replica_1", "included": true, "run_dir": "runs/joint_commitment/1786487826", "event_log_sha256": "cf3364d359310f1a749efb6b25797c727c7280c739f8ee4ab42ef6ca8fbadf7d", "resolved_config_sha256": "9b4689284cfa0c4c579301be5c99f0519e8f6459981ccadd5ce31aad9f830cd4", "completed": true, "total_cost_usd": 0.21061649999999998},
    {"role": "neutral_allocation_replica_2", "included": true, "run_dir": "runs/joint_commitment/1786488009", "event_log_sha256": "426c3afad0210265a68441e8346e3a67416d6d72beb4517bda6fc279137de03d", "resolved_config_sha256": "9b4689284cfa0c4c579301be5c99f0519e8f6459981ccadd5ce31aad9f830cd4", "completed": true, "total_cost_usd": 0.1619796},
    {"role": "professional_service_replica_2", "included": true, "run_dir": "runs/joint_commitment/1786488010", "event_log_sha256": "28caf3de2c100f363ea797a00b7f2325d6d39a2fb330b3370bf4bd368726716a", "resolved_config_sha256": "f5ec1636199c88a81c1a4554c7efc195d02e203519e2c22d4aa2d04127fc3b69", "completed": true, "total_cost_usd": 0.22822510000000001},
    {"role": "neutral_allocation_replica_3", "included": true, "run_dir": "runs/joint_commitment/1786488191", "event_log_sha256": "0a97e190f76c997fa98f577766b2d495902e78be3304bbaa3d8b4e1c22868f7a", "resolved_config_sha256": "9b4689284cfa0c4c579301be5c99f0519e8f6459981ccadd5ce31aad9f830cd4", "completed": true, "total_cost_usd": 0.16601500000000002},
    {"role": "professional_service_replica_3", "included": true, "run_dir": "runs/joint_commitment/1786488192", "event_log_sha256": "ccc48ac21fd4cf9967f846cdef5ed3df7fd79ebe8a2d9eab8671d28c82b6a70e", "resolved_config_sha256": "f5ec1636199c88a81c1a4554c7efc195d02e203519e2c22d4aa2d04127fc3b69", "completed": true, "total_cost_usd": 0.3227173}
  ]
}
-->

## Question

With the same two-agent repeated 7→21 allocation, no group identity, no
pledge, no entry cost, no audit, no action-contingent consequence, and the same
optional shared channel, does replacing professional-service language with a
neutral allocation description change the practical `allocation_a` ceiling?

This is an instrument-framing diagnostic, not a test of a covenant mechanism
or of alignment.

## Expected decision

One full trajectory is the independent unit. Each arm receives three fresh
Claude Sonnet 5 trajectories using environmental seed 71. Its sixteen decision
rounds are repeated interaction within a trajectory, not independent samples.

| Preregistered observation | Decision triggered |
|---|---|
| A run lacks `simulation_ended`, lacks all 32 decisions, lacks the shared channel, exposes a pledge, group registry, entry cost, audit, or action-contingent consequence, or requires `send_message` | Exclude the affected run, repair the instrument, and do not interpret behavior. |
| Both arms have 96/96 `allocation_a` decisions | Close as a framing-invariant ceiling at this resolution. Do not launch group or pledge arms; diagnose the payoff/task structure next. |
| The professional-service arm has 96/96 `allocation_a`, while the neutral arm contains at least one `allocation_b` | Close as evidence that the professional framing package changes baseline behavior. Do not launch covenant arms until the research team chooses which framing belongs in a human-parallel instrument. |
| Both arms contain both allocations | Close as a behaviorally variable baseline. Preregister one selected framing and then the group/pledge/costly-pledge ladder, with the same number of fresh trajectories per arm. |
| The neutral arm has 96/96 `allocation_b` while the professional arm is not at the same floor | Treat this as a strong framing effect, not evidence for a covenant. Revise the neutral description before choosing a treatment ladder. |

## Design

The world, model, seed, horizon, runtime limits, numerical payoffs, optional
shared channel, and structured action interface are identical in both arms.
Every agent selects `allocation_a` or `allocation_b` through the same
`submit_allocation` tool. The world maps `allocation_a` to a 7-unit transfer and
14-unit balance, and `allocation_b` to a 0-unit transfer and 21-unit balance;
this mapping is logged internally but no longer requires a public attestation.

The only intended treatment difference is the semantic frame rendered to the
agents:

- **Professional service:** two providers receive 21 units for the same
  recurring client service; `allocation_a` transfers 7 to a client account.
- **Neutral allocation:** two participants receive 21 units in a repeated
  allocation study; `allocation_a` assigns 7 to Account C.

The shared study channel is writable and optional in both arms. It is held
constant because making communication available only to one treatment would
confound framing with coordination affordance. It is not an instruction to
coordinate, and its messages are descriptive rather than an outcome measure.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Seed / replicas per arm | 71 / three fresh trajectories |
| Arms | professional service; neutral allocation |
| Rounds / decision opportunities | 17 / 16 per agent |
| Agents | 2 |
| Numerical allocation | 7 moved and 14 retained, or 0 moved and 21 retained |
| Group / pledge / entry cost | none / none / none |
| Audits / penalties | none / none |
| Channel | common, writable, optional |

No fork, resume, replacement, model override, group registry, pledge,
financial stake, or audit is used.

## Outcomes inspected

From authoritative events, inspect per trajectory:

- `allocation_a` and `allocation_b` counts per agent and jointly;
- completed joint outcomes;
- actual channels, optional communication protocol, and messages used;
- completion state, runtime, resolved configuration, and API cost.

The primary outcome is the distribution of the two allocations across the
three independent trajectories per arm. Channel content is evidence about how
agents interpret the framing, but does not establish cooperation, morality, or
an institutional effect.

## Provenance

- Base commit: `c087b1016080529e439b8addb1be141cdb9d98ec`.
- This planned record is created in a dirty worktree because unrelated local
  untracked files are present; the scenario/interface source is committed at
  the base commit.
- Each bundled JSON is the exact launch input and will be hashed before launch.
- Each command is executed three times without fork, resume, replacement, or
  model override. The shared seed fixes non-model environment state but does
  not make model sampling deterministic.

## Result

All six planned trajectories ended with authoritative
`simulation_ended: scenario_complete` events and recorded all 32 expected
provider decisions. The common writable channel was available in every run;
it was used in all six runs, for 16 messages total. No group, pledge, entry
cost, audit, or action-contingent consequence appeared in any resolved config.

| Frame | Run | `allocation_a` / `allocation_b` | Joint `allocation_a` / 16 | API cost |
|---|---|---:|---:|---:|
| Professional service | `1786487825` | 32 / 0 | 16 | $0.2016909 |
| Professional service | `1786488010` | 2 / 30 | 0 | $0.2282251 |
| Professional service | `1786488192` | 4 / 28 | 0 | $0.3227173 |
| **Professional pooled** | **3 runs** | **38 / 58** | **16 / 48** | **$0.7526333** |
| Neutral allocation | `1786487826` | 32 / 0 | 16 | $0.2106165 |
| Neutral allocation | `1786488009` | 32 / 0 | 16 | $0.1619796 |
| Neutral allocation | `1786488191` | 32 / 0 | 16 | $0.1660150 |
| **Neutral pooled** | **3 runs** | **96 / 0** | **48 / 48** | **$0.5386111** |

The professional trajectories were not a stable ceiling: in the latter two,
agents moved to `allocation_b` after discussing that the written rules did not
specify a shared payoff or a consequence of the client allocation. The neutral
trajectories nevertheless treated Account C as if it might create a shared or
multiplied benefit, despite no such rule. The claimed interpretations in either
frame were not implemented by the world.

Action counts were derived from
`joint_commitment_decision_recorded.actual_action`; joint outcomes from
`joint_commitment_round_settled.safe_client_outcome`; channel use from
`message_sent`. Total logged API cost was $1.2912444.

## Outcome

**Supported:** the framing-sensitivity gate fired. The professional and neutral
descriptions, with identical numerical allocations and interaction mechanics,
produced qualitatively different distributions across three same-config
trajectories. This is evidence that the baseline is not semantically neutral;
it is not evidence for a covenant, pledge, collaboration, morality, or an
alignment effect. The group/pledge/costly-pledge ladder must not be launched on
this instrument without a decision about the intended game and its explicit
world-level consequences.

## Validity limitations

The semantic frame is deliberately a package: professional-service terms,
provider identity, and client-account wording move together. This diagnostic
can locate a framing sensitivity but cannot attribute any difference to one
word or phrase. The sample is three stochastic trajectories per arm at one
model and one environmental seed; it is an instrument decision gate, not a
statistical estimate of a framing effect.

The shared channel was intentionally held constant, but it allowed agents to
negotiate and to infer nonexistent consequences. That behavior is itself useful
diagnostic evidence, but it means the prompt and channel jointly shape the game
agents believe they are playing. Neither frame gives `allocation_a` a specified
counterpart payoff, client consequence, or other strategic return, so the
current task is not yet a well-defined repeated social dilemma.

## What it changed

It resolves EXP-034's universal professional-service ceiling as
framing-dependent. The next decision is conceptual rather than a further
replication: specify the actual repeated interaction and downstream consequence
that makes the 7-unit action meaningful, then calibrate that new instrument
before adding group identity, pledge, or a 10%-costly pledge. More runs of the
current wording would not identify a covenant effect.

## Traps found

- Neutral labels alone do not make an LLM allocation task neutral. Agents
  supplied an unimplemented shared-benefit story for Account C.
- Professional-service language does not reliably induce remittance either:
  agents can instead infer that self-retention is appropriate because the rules
  specify no shared payoff. The prompt therefore cannot be treated as a passive
  description of a fixed game.
- A repeated two-agent allocation with no implemented effect of the 7-unit
  action is under-specified as a social dilemma. Comparing covenant treatments
  before defining that effect would confound institutional mechanisms with the
  agents' own inferred semantics.
