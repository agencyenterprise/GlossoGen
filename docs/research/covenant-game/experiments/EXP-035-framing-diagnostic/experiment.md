# EXP-035 — Professional-service versus neutral-allocation framing diagnostic

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
  "runs": []
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

Not yet run.

## Outcome

Not yet determined.

## Validity limitations

The semantic frame is deliberately a package: professional-service terms,
provider identity, and client-account wording move together. This diagnostic
can locate a framing sensitivity but cannot attribute any difference to one
word or phrase.

## What it changed

It follows EXP-034's universal professional-service ceiling by making the
semantic interpretation, rather than an institutional mechanism, the next
decision-relevant uncertainty.

## Traps found

None before launch.
