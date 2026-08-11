# EXP-025 — Human-parallel commitment instrument pilot

**Status:** planned
**Date opened:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-006 — Human-parallel commitment
**Role:** pilot

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-006",
  "experiment_role": "pilot",
  "experiment_id": "EXP-025",
  "base_commit": "5d979ecfa4a599b60e7afec10fc43e812674bbb5",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run warehouse_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/no-group.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run warehouse_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/group.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run warehouse_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/pledge.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run warehouse_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/covenant.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/no-group.json", "launch_path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/no-group.json", "sha256": "8375461055138fa008fc019eef90415af126b313cef6704655200b4e660f7403"},
    {"path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/group.json", "launch_path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/group.json", "sha256": "5442ed174777c73a1c2dfa50e8ca69183a9eaa76ef3468a78c2485e27ebae9cf"},
    {"path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/pledge.json", "launch_path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/pledge.json", "sha256": "6c62f886d9332620ebcd1719849be25d00a89f339246cc47c2f483b7a42a5753"},
    {"path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/covenant.json", "launch_path": "docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/configs/covenant.json", "sha256": "a174ceeef74d4872bd82b092b30a739cf34a79b8b14bcd89b48658012c18e046"}
  ],
  "runs": []
}
-->

## Question

Can a reduced, repeated two-provider warehouse instrument implement the four
human-parallel treatments as real, distinct world states and produce a usable
contrast in genuine inspection: no group, group only, pledge, and pledge plus a
10% forfeiture?

## Expected decision

This is an instrument and repeatability pilot, not a test of model-general
covenant effects. Each configuration is launched **three times** with the same
seed and Claude Sonnet 5. The three runs estimate conditional trajectory spread
from model sampling; they do not justify a normal approximation, statistical
significance claim, or a between-seed generalization.

| Preregistered observation | Decision triggered |
|---|---|
| Any arm lacks its expected structured exposure — pledge event, 10% deduction, or condition-specific prompt/action surface — or any included log lacks `simulation_ended` | Close as execution-invalid and repair the instrument before launching a replacement pilot. |
| Across the 12 complete trajectories, both `inspect` and `shortcut` occur; the mean covenant minus no-group **joint-inspection** difference is at least 0.30 and has the same sign in all three replicate positions | Open a fresh-seed replication record with the same three runs per arm. Treat group-only and pledge-only contrasts as descriptive until that replication. |
| No-group and covenant both sit at the same practical ceiling (mean joint inspection ≥0.95) or floor (≤0.05) | Do not add unchanged replicas. Revise the fixed temptation or action framing and record the degeneracy. |
| Any other result | Close as inconclusive. Report the three-run means, standard deviations, and action traces; decide whether to revise the instrument or increase replication only after using the observed spread to size a decision-relevant effect. |

The fixed **gross** immediate payoff is deliberately self-serving: a genuine
inspection earns 10, while shortcutting earns 17. This is the warehouse
analogue of the human trust game's fixed 7→21 choice: it standardizes the
choice schedule rather than tying behavior to changing task prices or case
correctness. The covenant forfeiture scales both rewards, so it remains a real
membership cost rather than an economic subsidy for inspecting.

## Design

Two symmetric providers each receive one inspection responsibility per round.
Each chooses exactly one structured action: `inspect_assigned_zone` or
`take_shortcut`. The world records the true action; there is no count accuracy,
audit, client refund, bond, staffing, or variable effort cost. At the following
round both providers receive the prior aggregate action summary.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Seed | 60 |
| Replicates | 3 independent trajectories per arm, 12 total |
| Rounds / horizon | 15 / undisclosed |
| Providers | 2 |
| Inspection payoff | 10 per provider per round |
| Shortcut payoff | 17 per provider per round |
| Covenant forfeiture | 10% of every realized reward; not refunded or banked |
| Communication | one shared workroom in every arm |
| Actions revealed | aggregate prior-round provider actions in every arm |

Only `condition` and the required corresponding `forfeiture_fraction` vary:

| Arm | Group | Pledge | Forfeiture |
|---|---:|---:|---:|
| No group | no | no | 0% |
| Group | yes | no | 0% |
| Pledge | yes | yes | 0% |
| Covenant | yes | yes | 10% |

The independent unit is a complete run. Fifteen actions within one provider's
history are dependent observations and will not be treated as 15 replications.
The same seed holds the external setup constant; repeated runs quantify residual
model and runtime stochasticity. A later fresh seed is required before treating
a contrast as behaviorally repeated.

## Outcomes inspected

Primary:

- individual and joint inspection rate per complete run;
- covenant minus no-group joint-inspection difference across replicate positions;
- first shortcut round and inspection persistence after a first shortcut.

Secondary, reported separately:

- structured pledge affirmation and decline;
- shortcut and missing-action counts;
- gross payment, forfeiture paid, and net balance by provider;
- public messages, tool calls, runtime, tokens, and API cost.

The experiment does **not** measure task correctness, deception, repair,
financial insurance, sanctions, stable equilibrium, or transmission to
newcomers. It should not be used to make claims about them.

## Provenance

- Base commit at planning: `5d979ecfa4a599b60e7afec10fc43e812674bbb5`
- Worktree dirty at planning: `true`, solely because the unrelated
  `.claude/worktrees/` directory remains untracked. The scenario, tests, and
  bundled launch configurations are committed at the recorded SHA.
- Exact commands and immutable config hashes are in the machine-readable block.
  Each command is run exactly three times, with no fork or resume.
- New scenario: `warehouse_commitment`; prior scenario: `bonded_team_production`.
  The former is a separate instrument and no prior run is a source trajectory.
- Analysis will be added under this record's `analysis/` directory and will
  derive every reported number from `warehouse_commitment_*` action and outcome
  events only.

## Result

Pending. No model run has been launched.

## Outcome

Pending.

## Validity limitations

- The automatic per-reward deduction is equivalent to a 10% share of total
  realized rewards, but its timing is more immediate than an end-of-study
  forfeiture.
- The model may decline the pledge; this is intentionally retained as an
  intention-to-treat exposure and must not be silently excluded.
- A group and pledge are prompt-mediated social treatments. The forfeiture and
  inspection actions are, by contrast, mechanically enforced and event-logged.
- This scenario intentionally excludes revocable future access and violation
  sanctions, so it cannot by itself test institutional stability or deterrence.

## What it changed

Pending. The planned change is to move the next mechanism question out of the
high-variance team-production instrument and into a fixed-temption, action-level
comparison that is closer to the human experiment.

## Traps found

- Do not call the 10% forfeiture a fine: it is paid regardless of inspection or
  shortcutting.
- Do not equate a completed 15-round run with 15 independent samples.
- Do not claim that this condition is the full covenant mechanism; persistent
  membership rights and revocation remain a separate study.
