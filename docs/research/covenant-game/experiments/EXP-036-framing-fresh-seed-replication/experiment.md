# EXP-036 — Fresh-seed replication of the framing diagnostic

**Status:** planned
**Date opened:** 2026-08-11
**Date closed:** —
**Research program:** covenant-game
**Study:** STUDY-008 — Joint commitment alignment
**Role:** replication

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-008",
  "experiment_role": "replication",
  "experiment_id": "EXP-036",
  "base_commit": "144e37f993f86c4d0668aecfb13dd3522caeb329",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/professional-service-seed72.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/neutral-allocation-seed72.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/professional-service-seed73.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run joint_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/neutral-allocation-seed73.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/professional-service-seed72.json", "launch_path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/professional-service-seed72.json", "sha256": "beecf0e7dd618da304326ae0a6d21ed9a8cf99ecc1e5ac0125ae32fa53b60880"},
    {"path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/neutral-allocation-seed72.json", "launch_path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/neutral-allocation-seed72.json", "sha256": "2df6636526445836bd92c2a70e0ef5fba0b8458ab6d64f8a5afb90c823c2442a"},
    {"path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/professional-service-seed73.json", "launch_path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/professional-service-seed73.json", "sha256": "a48ccb7c603b4ca590059b6e0b016d6368d720bf1f2dd99704793b98147d1afe"},
    {"path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/neutral-allocation-seed73.json", "launch_path": "docs/research/covenant-game/experiments/EXP-036-framing-fresh-seed-replication/configs/neutral-allocation-seed73.json", "sha256": "e435f39cf4f5ddcebcd58ce06adcb8429466272a51e99472321c77c4fd060ffb"}
  ],
  "runs": []
}
-->

## Question

Does EXP-035's framing-sensitive allocation pattern repeat at two fresh
environmental seeds when each professional-service and neutral-allocation arm
is independently run three times with Claude Sonnet 5?

This is a replication of an instrument-calibration finding. It does not test a
group, pledge, covenant, alignment, or moral effect.

## Expected decision

Each full trajectory is the independent unit. For each fresh seed, the same
three-replica sampling design is applied to each semantic frame. The sixteen
decision rounds within a trajectory are repeated interaction, not 16
independent samples.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`, lacks all 32 decisions, lacks the shared channel, exposes a group, pledge, entry cost, audit, or action-contingent consequence, or exposes a different action interface | Exclude the affected run, repair the instrument, and do not interpret the replication. |
| In each seed, neutral allocation has more `allocation_a` decisions than professional service, and professional service contains at least one `allocation_b` decision | Close as a repeated framing-sensitive baseline. Do not launch the covenant ladder on this task; replace the under-specified allocation world. |
| Both arms are 96/96 `allocation_a` across both fresh seeds | Close as a fresh-seed ceiling. Do not infer an institutional effect or launch the covenant ladder. |
| The ordering reverses, disappears, or differs across the two seeds | Close as inconclusive fresh-seed replication. Treat framing response as seed- or trajectory-dependent and do not launch the covenant ladder. |

## Design

EXP-036 repeats EXP-035 without code changes. It uses the same two-agent,
17-round hidden-horizon `joint_commitment` world, the same `allocation_a` and
`allocation_b` tool, the same optional common writable channel, and no group,
pledge, entry cost, audit, penalty, bond, replacement, fork, resume, or model
override.

The only treatment difference remains semantic framing:

- **Professional service:** two providers allocate 21 units while serving a
  recurring client; `allocation_a` transfers 7 to the client account.
- **Neutral allocation:** two participants allocate 21 units in a repeated
  study; `allocation_a` assigns 7 to Account C.

Each arm is run three times at seed 72 and three times at seed 73, for twelve
fresh trajectories total. Within a seed, both arms see the same non-model
environment. Across runs with identical inputs, LLM sampling remains
stochastic.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Seeds / replicas | 72 and 73 / three trajectories per arm per seed |
| Total trajectories | 12 |
| Rounds / decision opportunities | 17 / 16 per agent |
| Agents | 2 |
| Numerical allocation | 7 moved and 14 retained, or 0 moved and 21 retained |
| Group / pledge / entry cost | none / none / none |
| Audits / penalties | none / none |
| Channel | common, writable, optional |

## Outcomes inspected

From authoritative events, inspect per trajectory and pooled by frame within
each seed:

- `allocation_a` and `allocation_b` counts per provider and jointly;
- completed joint outcomes;
- actual channel use and messages, as interpretation evidence only;
- completion state, resolved configuration, runtime, and API cost.

The primary outcome is the per-seed ordering of allocation decisions across
independent trajectories. It does not establish why an agent chose an action.

## Provenance

- Source record: [EXP-035](../EXP-035-framing-diagnostic/experiment.md).
- Base commit: `144e37f993f86c4d0668aecfb13dd3522caeb329`.
- Worktree is dirty only because this planned record and pre-existing unrelated
  untracked files are present. The scenario source used by the runs is
  committed at the base SHA.
- The four bundled JSON files are exact launch inputs, hashed in the
  machine-readable block. Each listed command will be executed three times,
  with no fork, resume, replacement, or model override.

## Result

Not yet run.

## Outcome

Not yet determined.

## Validity limitations

The experiment varies a frame package, not one word. It can establish whether
the EXP-035 pattern repeats under two new environmental seeds, but not which
phrase caused it or whether it generalizes to other models. Both arms retain a
channel that allows agents to infer unimplemented social consequences.

## What it changed

It applies the requested fresh-seed replication before changing the scenario.
It will decide whether EXP-035's finding is robust enough to rule out the
current allocation task as a covenant instrument, rather than treating one
seed's trajectories as definitive.

## Traps found

None before launch.
