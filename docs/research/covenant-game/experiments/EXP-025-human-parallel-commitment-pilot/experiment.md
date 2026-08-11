# EXP-025 — Human-parallel commitment instrument pilot

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
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
  "runs": [
    {"role": "covenant_replicate_1", "included": true, "run_dir": "runs/warehouse_commitment/1786417789", "event_log_sha256": "70624f84359b9ddefb2eb08f89d7ee41b5b913c11bd10ff20587fa66eeffeaf4", "resolved_config_sha256": "93584585ee2fbcb99f368822fd99c5ec3bd66dfb33d9fb98036efcb6911e87a5", "completed": true, "total_cost_usd": 0.215704},
    {"role": "no_group_replicate_1", "included": true, "run_dir": "runs/warehouse_commitment/1786417790", "event_log_sha256": "684b653251f1e6bfb0be55d55e582f5013dcd63172cb886a25c5a776ad9390bb", "resolved_config_sha256": "2dee799d33e189a31887b62db7b8b08ff2a61f54d68ed3c30a4a92866919de0b", "completed": true, "total_cost_usd": 0.15043020000000001},
    {"role": "pledge_replicate_1", "included": true, "run_dir": "runs/warehouse_commitment/1786417791", "event_log_sha256": "ede38614c88f2d82968eaec65dc29bc3dce4fa8f3273a382b4ae47a00a964352", "resolved_config_sha256": "ad00bc04b838ac0191e24e128a57fbedc15fb391ed87fc8c23d6abafcda9efab", "completed": true, "total_cost_usd": 0.2163565},
    {"role": "group_replicate_1", "included": true, "run_dir": "runs/warehouse_commitment/1786417792", "event_log_sha256": "2703810198e035c4af3a9763cdfbf28e8b86bbdf34406203345b8afa9fb2d1b0", "resolved_config_sha256": "cfee44aba9cc9b748523c08b704eed788dd2fc8c1381f1866199182e02c24ad0", "completed": true, "total_cost_usd": 0.163844},
    {"role": "covenant_replicate_2", "included": true, "run_dir": "runs/warehouse_commitment/1786418095", "event_log_sha256": "6646576912a138177837970179f92451f7e428ef9dda35dd21ec6c2c3deb04ce", "resolved_config_sha256": "93584585ee2fbcb99f368822fd99c5ec3bd66dfb33d9fb98036efcb6911e87a5", "completed": true, "total_cost_usd": 0.161891},
    {"role": "pledge_replicate_2", "included": true, "run_dir": "runs/warehouse_commitment/1786418096", "event_log_sha256": "61338654ffe6b251e8bafe0222e695b201ca93efe8864cd296c6eb42384d2a25", "resolved_config_sha256": "ad00bc04b838ac0191e24e128a57fbedc15fb391ed87fc8c23d6abafcda9efab", "completed": true, "total_cost_usd": 0.200982},
    {"role": "no_group_replicate_2", "included": true, "run_dir": "runs/warehouse_commitment/1786418097", "event_log_sha256": "714cde3cdfc8b960bd670ba49bd987968d582f8b41794d3b3f019806ab2c4eb5", "resolved_config_sha256": "2dee799d33e189a31887b62db7b8b08ff2a61f54d68ed3c30a4a92866919de0b", "completed": true, "total_cost_usd": 0.1465233},
    {"role": "group_replicate_2", "included": true, "run_dir": "runs/warehouse_commitment/1786418098", "event_log_sha256": "f5bdc02a07ad9ac64bc98bcccb3afc663a2bfa98cee8efbbbd90e7e7fdb31e1d", "resolved_config_sha256": "cfee44aba9cc9b748523c08b704eed788dd2fc8c1381f1866199182e02c24ad0", "completed": true, "total_cost_usd": 0.1443371},
    {"role": "covenant_replicate_3", "included": true, "run_dir": "runs/warehouse_commitment/1786418265", "event_log_sha256": "ef8d60f417fbfc60d472592c7a51087638c6deb8b56da6c694ed9f037b8b5713", "resolved_config_sha256": "93584585ee2fbcb99f368822fd99c5ec3bd66dfb33d9fb98036efcb6911e87a5", "completed": true, "total_cost_usd": 0.16673890000000002},
    {"role": "group_replicate_3", "included": true, "run_dir": "runs/warehouse_commitment/1786418266", "event_log_sha256": "da4ab77d918146fdc8cba1815e8adfb23f8fe389526e1113671ba80a69fbe3df", "resolved_config_sha256": "cfee44aba9cc9b748523c08b704eed788dd2fc8c1381f1866199182e02c24ad0", "completed": true, "total_cost_usd": 0.18595070000000002},
    {"role": "pledge_replicate_3", "included": true, "run_dir": "runs/warehouse_commitment/1786418267", "event_log_sha256": "c06b0686f614d11eb3c9ed9f8636d429b80b23d635b502f42a9366dfbd135fa9", "resolved_config_sha256": "ad00bc04b838ac0191e24e128a57fbedc15fb391ed87fc8c23d6abafcda9efab", "completed": true, "total_cost_usd": 0.2361359},
    {"role": "no_group_replicate_3", "included": true, "run_dir": "runs/warehouse_commitment/1786418268", "event_log_sha256": "1c3e72bbaea92159ec7e77afed2b5280486f969f44cabe474861d27c7e643988", "resolved_config_sha256": "2dee799d33e189a31887b62db7b8b08ff2a61f54d68ed3c30a4a92866919de0b", "completed": true, "total_cost_usd": 0.1485196}
  ]
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
- [`analysis/derive_replica_summary.py`](analysis/derive_replica_summary.py)
  derives every reported number below from `warehouse_commitment_*` action and
  outcome events only.

## Result

All twelve planned trajectories finished with an authoritative
`simulation_ended` event. The treatment instrumentation activated as designed:
five of six pledge-only providers and three of six covenant providers affirmed
the structured pledge; the remaining providers declined it. The covenant
arm mechanically collected **$149.60** in forfeitures across its 88 recorded
actions (10% of each realized reward), while the other arms collected zero.

The primary outcome did not vary: every complete round in every run had fewer
than two inspections. Joint inspection was therefore **0/44** covenant rounds,
**0/43** no-group rounds, **0/42** group-only rounds, and **0/43** pledge-only
rounds. No-group, group-only, and covenant providers took only shortcuts. The
pledge-only arm contained the only individual inspection variation: 16
inspections across its three trajectories, all without a second provider
inspecting in the same round.

The twelve runs cost **$2.1374** in total. Their action and treatment summaries
are reproducible by running:

```bash
VIRTUAL_ENV= .venv/bin/python \
  docs/research/covenant-game/experiments/EXP-025-human-parallel-commitment-pilot/analysis/derive_replica_summary.py
```

## Outcome

**Not supported.** The preregistered practical-floor rule fired: the covenant
and no-group arms both had mean joint inspection of zero. The experiment does
not support a human-parallel covenant effect on the primary outcome, and it
does not justify a fresh-seed replication or another unchanged fixed-seed
batch. The isolated pledge-only inspections are descriptive variation, not
evidence that the pledge caused an effect.

## Validity limitations

- The automatic per-reward deduction is equivalent to a 10% share of total
  realized rewards, but its timing is more immediate than an end-of-study
  forfeiture.
- The forfeiture scales both actions equally: shortcutting remains immediately
  more profitable than inspecting ($15.30 versus $9.00 net). The condition
  relies on pledge-mediated commitment rather than making inspection privately
  optimal.
- The model may decline the pledge; this is intentionally retained as an
  intention-to-treat exposure and must not be silently excluded.
- A group and pledge are prompt-mediated social treatments. The forfeiture and
  inspection actions are, by contrast, mechanically enforced and event-logged.
- This scenario intentionally excludes revocable future access and violation
  sanctions, so it cannot by itself test institutional stability or deterrence.
- Some complete trajectories had one incomplete opening round. This did not
  change the zero joint-inspection result, but a successor instrument should
  make the pledge decision a pre-round setup phase so all fifteen rounds offer
  the action choice.

## What it changed

The new instrument successfully implemented and independently measured public
group framing, a structured pledge, and a real 10% forfeiture. It also showed
that this particular fixed payoff/action framing cannot answer the intended
question with joint inspection: the principal outcome stays at its floor even
under the full human-parallel bundle. The next experiment should be a revised
instrument, not a new seed or a longer run of this one.

## Traps found

- Do not call the 10% forfeiture a fine: it is paid regardless of inspection or
  shortcutting.
- Do not equate a completed 15-round run with 15 independent samples.
- Do not claim that this condition is the full covenant mechanism; persistent
  membership rights and revocation remain a separate study.
- Do not interpret the existence of individual pledge-only inspections as a
  treatment effect when the preregistered joint outcome remained at zero.
