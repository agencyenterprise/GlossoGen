# EXP-044 — Four-arm ladder replication at claim 42 under the corrected prompt

**Status:** complete
**Date opened:** 2026-08-12
**Date closed:** 2026-08-12
**Research program:** covenant-game
**Study:** STUDY-012 — Contribution ladder under a non-disclosing prompt
**Role:** replication

<!-- experiment-record:v2
{
  "base_commit": "070a4949f3b805d66a9db4421ad2efb0a2a641f3",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/no-group-claim42.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/group-claim42.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/pledge-claim42.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/costly-pledge-claim42.json"
  ],
  "configs": [
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/no-group-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/no-group-claim42.json",
      "sha256": "00316c6443acf3043d9166ee548a107a704671f46e37ad4447ff8d3e5824ba81"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/group-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/group-claim42.json",
      "sha256": "36ec11eb069c74e7d5f4c9458688f22274b34dfe85df9149a8fabb5c064afc08"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/pledge-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/pledge-claim42.json",
      "sha256": "9f014e28d694990daccd43fb74ed8af273dc38a383f1510f7a3d379dd6247a0e"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/costly-pledge-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/costly-pledge-claim42.json",
      "sha256": "0643fedb5ff00838ecfcb38fd488bc32d0e862bf3b9628ada754adb0265e7a6b"
    }
  ],
  "experiment_id": "EXP-044",
  "experiment_role": "replication",
  "research_program": "covenant-game",
  "runs": [
    {"run_dir": "runs/shared_reserve_commitment/1786507754", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "68c755ff40209654d7ae9fada5152cd0b9f555ffb6f527ab4d02ad211446ed47", "resolved_config_sha256": "47e6e9d60bc9232ed5edd5db532c3762fe5ab48d837a1c038cd20e0fc814c05b", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.37311300000000003},
    {"run_dir": "runs/shared_reserve_commitment/1786507762", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "534ab822f38593af9bdee1627c70955313440d9fed79aa4570b76f6034ee2e70", "resolved_config_sha256": "47e6e9d60bc9232ed5edd5db532c3762fe5ab48d837a1c038cd20e0fc814c05b", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.3593829},
    {"run_dir": "runs/shared_reserve_commitment/1786507892", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "fb2d525f62dd57cdf5a75e937e0734083a5d4e016add516203d1097ce48773c2", "resolved_config_sha256": "47e6e9d60bc9232ed5edd5db532c3762fe5ab48d837a1c038cd20e0fc814c05b", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.4043608000000001},
    {"run_dir": "runs/shared_reserve_commitment/1786507929", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "45371841339dbd3b8f57625cddb694d93abe053e6df7258897ade4cbd33c086e", "resolved_config_sha256": "47e6e9d60bc9232ed5edd5db532c3762fe5ab48d837a1c038cd20e0fc814c05b", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.34869300000000003},
    {"run_dir": "runs/shared_reserve_commitment/1786507997", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "3e376ed909f7369f8ecae02f4fb646e4071c4a70a3ccbd0b7df7d024c88d3c8a", "resolved_config_sha256": "47e6e9d60bc9232ed5edd5db532c3762fe5ab48d837a1c038cd20e0fc814c05b", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.41250090000000006},
    {"run_dir": "runs/shared_reserve_commitment/1786508051", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "065b6f69d6b42fa7ee97af6de5ef4f18bd82c1639547a33560f62b996f0fbb4d", "resolved_config_sha256": "47e6e9d60bc9232ed5edd5db532c3762fe5ab48d837a1c038cd20e0fc814c05b", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.3604662},
    {"run_dir": "runs/shared_reserve_commitment/1786507750", "role": "group", "included": true, "completed": true, "event_log_sha256": "c563ca09637b4d83b4bccaa0d815fb8d326837da3b548517e5e58a69457b9931", "resolved_config_sha256": "83fc4c771def44b0040844e52bc69697788d823cd13ca2c0993171dde57f7a56", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.4809133},
    {"run_dir": "runs/shared_reserve_commitment/1786507758", "role": "group", "included": true, "completed": true, "event_log_sha256": "a8943dcf64f714ccf0ccae97750f025c76a7a8f7bd1dd223f927b924aafddbab", "resolved_config_sha256": "83fc4c771def44b0040844e52bc69697788d823cd13ca2c0993171dde57f7a56", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.3169953},
    {"run_dir": "runs/shared_reserve_commitment/1786507766", "role": "group", "included": true, "completed": true, "event_log_sha256": "7ea36b36c6cf0e21b095c0393e66dc05152f575db9384dad189219aa25085aea", "resolved_config_sha256": "83fc4c771def44b0040844e52bc69697788d823cd13ca2c0993171dde57f7a56", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.40551060000000005},
    {"run_dir": "runs/shared_reserve_commitment/1786507895", "role": "group", "included": true, "completed": true, "event_log_sha256": "8db18c946d8d05da719294639eedb2c8f4c9920e1452421bb85de2d79455a362", "resolved_config_sha256": "83fc4c771def44b0040844e52bc69697788d823cd13ca2c0993171dde57f7a56", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.37695579999999995},
    {"run_dir": "runs/shared_reserve_commitment/1786507978", "role": "group", "included": true, "completed": true, "event_log_sha256": "dc220401049b38cae8c42511152d0ec627cb57ea1074f87971dee09aeca05b3c", "resolved_config_sha256": "83fc4c771def44b0040844e52bc69697788d823cd13ca2c0993171dde57f7a56", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.5272618},
    {"run_dir": "runs/shared_reserve_commitment/1786508047", "role": "group", "included": true, "completed": true, "event_log_sha256": "33527c182e3c3a1859588598cec9ffb2ea3531ca409ab2a6dab41d0c6e42515c", "resolved_config_sha256": "83fc4c771def44b0040844e52bc69697788d823cd13ca2c0993171dde57f7a56", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.421105},
    {"run_dir": "runs/shared_reserve_commitment/1786507748", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "bd99e086e3e6b547d95848d51fb4a384bc8f43ccb87247dc8013c36f20099c26", "resolved_config_sha256": "057853def6d05256e23eed42207f035d3a0abcb4f743447fea7c8ed56737c499", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.6156018000000001},
    {"run_dir": "runs/shared_reserve_commitment/1786507756", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "937477dcc2d4311d3a8e3159d6d9857c2a4cf99e5dc3a31eb6dbb4add71a215a", "resolved_config_sha256": "057853def6d05256e23eed42207f035d3a0abcb4f743447fea7c8ed56737c499", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.37668060000000003},
    {"run_dir": "runs/shared_reserve_commitment/1786507764", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "513096dc9a26d9ad084aa1137a59033ce5ab1f8b94a0bf6ea2e0af3061554385", "resolved_config_sha256": "057853def6d05256e23eed42207f035d3a0abcb4f743447fea7c8ed56737c499", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.36723839999999996},
    {"run_dir": "runs/shared_reserve_commitment/1786507893", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "ad5388240eec24592b5accdb1489e89d8be86ca8422b405d183192daa841f213", "resolved_config_sha256": "057853def6d05256e23eed42207f035d3a0abcb4f743447fea7c8ed56737c499", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.5507705},
    {"run_dir": "runs/shared_reserve_commitment/1786507961", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "571f4a90b2904aa787701be455f4ff36d56d54aa9fdfb9c0fbd72397be0778e8", "resolved_config_sha256": "057853def6d05256e23eed42207f035d3a0abcb4f743447fea7c8ed56737c499", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.36430500000000005},
    {"run_dir": "runs/shared_reserve_commitment/1786507999", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "d88e4be6cfd59701b83d693feb56e7eb545e233fde7b078ad46704dbde931f7b", "resolved_config_sha256": "057853def6d05256e23eed42207f035d3a0abcb4f743447fea7c8ed56737c499", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.5970191},
    {"run_dir": "runs/shared_reserve_commitment/1786507752", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "7a29478c958e5e4bdf9a84dd31aa243f92d856cc332fe9da4fedfd098743672f", "resolved_config_sha256": "cee25e052d2ef8719caffa6a46b6284e5122ea127156a1a708157dcd8cdc2cfe", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.39428240000000003},
    {"run_dir": "runs/shared_reserve_commitment/1786507760", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "e78759ad2d481ac50f34216dd82b0a38474e714193f218996f8f3998f1e80674", "resolved_config_sha256": "cee25e052d2ef8719caffa6a46b6284e5122ea127156a1a708157dcd8cdc2cfe", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.3372866},
    {"run_dir": "runs/shared_reserve_commitment/1786507768", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "2b7278c1045b773cbbb39cff68b9b4e0f320eb8f381d9ef79b818034efbc6e33", "resolved_config_sha256": "cee25e052d2ef8719caffa6a46b6284e5122ea127156a1a708157dcd8cdc2cfe", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.3511172},
    {"run_dir": "runs/shared_reserve_commitment/1786507912", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "f49840d51b82376a0f96aca56bd56326b809ac8e4cf3da73df16ccd50f5ab609", "resolved_config_sha256": "cee25e052d2ef8719caffa6a46b6284e5122ea127156a1a708157dcd8cdc2cfe", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.3279308},
    {"run_dir": "runs/shared_reserve_commitment/1786507980", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "8945853d4af806cf13b79c32f3c79c80ee88a8f4734a96de6a412a4eec515e96", "resolved_config_sha256": "cee25e052d2ef8719caffa6a46b6284e5122ea127156a1a708157dcd8cdc2cfe", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.36961350000000004},
    {"run_dir": "runs/shared_reserve_commitment/1786508049", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "ffc2df58ea7574cdec6c1129894b364be807b94e5d82711dd73d6812a7cef201", "resolved_config_sha256": "cee25e052d2ef8719caffa6a46b6284e5122ea127156a1a708157dcd8cdc2cfe", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 74, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.4306323}
  ],
  "schema_version": 2,
  "study_id": "STUDY-012",
  "worktree_dirty": true
}
-->

## Question

Under a system prompt that no longer discloses that conditions are being
compared, does the EXP-038/EXP-039 world produce provider defection, and does
the four-arm ladder reproduce the ordering that batch recorded?

## Expected decision

A defecting baseline restores the headroom every batch since EXP-040 has
lacked, and licenses the mechanisms the collaboration has asked for but that
this instrument has never carried: loss of membership, and probing why agents
cooperate. A baseline that stays at zero refutes prompt disclosure as the
explanation for the flatness and leaves model drift as the remaining candidate,
to be tested separately by re-running the original code.

## Design

The world is byte-for-byte the batch-1 world. The four bundled configs are
exact copies of the EXP-038 and EXP-039 launch inputs and carry identical
SHA-256 hashes, so the knobs are not merely equivalent but the same files: two
providers, 21-unit endowment, 21 units per active round, `contribute` (7 to the
reserve, keep 14) or `retain` (keep 21), 17 rounds with an undisclosed ending,
and deterministic 42-unit claims after rounds 7 and 12. The disclosure knobs
added in EXP-043 sit at their defaults — `ledger_visibility: full`,
`free_form_messages_enabled: true`, reserve balance and claim amount both
disclosed — which reproduces the batch-1 behaviour exactly.

Six independent trajectories per arm, against three in batch 1. The trajectory
is the unit; the sixteen decision rounds inside one are repeated interaction,
not sixteen observations.

| Condition | Exposure |
|---|---|
| `no_group` | none |
| `group` | a public registry lists both providers as Shared Service Group members |
| `pledge` | group plus a public affirm/decline of a commitment to contribute every round |
| `costly_pledge` | pledge plus a real one-time 2.1-unit deduction on affirming (10% of the round payment) |

### The one deliberate difference

Both prompt templates were rewritten in `070a494`. The rendered system prompt
for a given arm goes from 274 words to 177, every sentence is reworded, and one
sentence is deleted outright:

> The same hidden claim schedule is used in every condition.

That sentence told providers they were inside an experiment whose conditions
are being compared. A model that knows it is being compared across arms has
reason to behave consistently across arms, which is the exact null this program
recorded in EXP-040, EXP-041, EXP-042, and EXP-043. Removing it is the
motivated hypothesis this replication tests.

This is therefore **not** a test of model drift. The prompt change is a known,
intended difference from batch 1, declared here rather than discovered later.
Separating drift from prompt requires re-running the original templates at
commit `e393852`, which this record does not do.

### Reference values from batch 1

Per arm, 96 opportunities across three trajectories:

| Arm | contribute | retain | no_decision |
|---|---|---|---|
| `no_group` (EXP-038) | 84 | 12 | 0 |
| `group` (EXP-039) | 66 | 27 | 3 |
| `pledge` (EXP-039) | 95 | 0 | 1 |
| `costly_pledge` (EXP-039) | 95 | 0 | 1 |

Every batch since — EXP-040, EXP-041, EXP-042, EXP-043, 48 trajectories — has
recorded a combined three retentions, none of them in a `no_group` arm.

## Outcomes inspected

- **Defection (primary):** `retain` actions over decision opportunities per arm,
  and the count of trajectories carrying at least one retention.
- **Service continuity:** coverage of each claim and any termination.
- **Pledge uptake and cost exposure:** affirm/decline counts and 2.1-unit
  deductions actually recorded.
- **Missed decisions:** `no_decision` settlements, counted separately from
  retentions and never merged into them.
- **Coordination talk:** free-form messages on the shared record, qualitative
  only, since this arm re-enables them.

### Preregistered gates

1. **Gate A — baseline activation.** At least one `retain` in the `no_group`
   arm across its six trajectories.
2. **Gate B — ladder ordering.** Evaluated only if Gate A passes. Batch 1 is
   reproduced when trajectories-with-defection satisfy both `group ≥ no_group`
   and `pledge < group` and `costly_pledge < group`. Report the arm contrast
   only under this gate.
3. **Gate C — prompt hypothesis refuted.** If Gate A fails, record that
   correcting the prompt does not restore variance, that design disclosure is
   not the explanation for the ceiling, and that the batch-1 versus later-batch
   divergence remains unexplained by any manipulation attempted in EXP-041
   through EXP-044. The authorized next step then becomes the verbatim re-run at
   `e393852`, which isolates model drift.

Gates are not revised after results are seen. Gate C is a real outcome, not a
failure to be worked around.

## Provenance

- Base commit: `070a4949f3b805d66a9db4421ad2efb0a2a641f3`
- Worktree dirty at planning: `true`, but only from two untracked non-code
  artifacts predating this work (`.claude/worktrees/` and a stray file under
  `experiments/2026-06-19_veyru_channel_noise/`). `src/` is fully committed at
  the base commit, so the code that produces these runs is reproducible from it.
- Exact command: see `commands` in the machine-readable block
- Config: the four bundled `configs/*-claim42.json`, hashed above and identical
  to the EXP-038 and EXP-039 launch inputs
- Model/provider: `claude-sonnet-5` / `anthropic`
- Seed: 74 in every config, and inert — this scenario reads no seed and has no
  RNG. This is not a fresh-seed replication and no seed-sensitivity claim
  follows from it.
- Rounds: 17 configured; claims at rounds 7 and 12
- Source/fork boundary: none; these are fresh runs

## Result

All 24 runs ended with `simulation_ended` at round 17. All 48 claims were
covered and no service terminated. Derived by
[`analysis/summarize_ladder.py`](analysis/summarize_ladder.py).

| Arm | trajs | opps | retain | rate | slack | exposed | trajs with retention | batch-1 rate |
|---|---|---|---|---|---|---|---|---|
| `no_group` | 6 | 192 | 15 | 7.8% | 15 | **0** | 3/6 | 12.5% |
| `group` | 6 | 192 | 17 | 8.9% | 17 | **0** | 2/6 | 28.1% |
| `pledge` | 6 | 192 | 0 | 0.0% | 0 | 0 | 0/6 | 0.0% |
| `costly_pledge` | 6 | 192 | 0 | 0.0% | 0 | 0 | 0/6 | 0.0% |

Pledge uptake was unanimous in both pledge arms — 12 affirmations, 0 declines,
12 entry costs paid in `costly_pledge`.

**Retention returned.** After 48 trajectories across EXP-040 through EXP-043
producing three retentions in total and none in a `no_group` arm, this batch
recorded 32 across the two untreated arms. On that narrow point the batch is
decisive: the batch-1 world does produce retention, and EXP-040 was the outlier
rather than batch 1.

**Every retention was slack harvesting.** Not one of the 32 left the reserve
unable to absorb a claim. The per-round sequences show a single stable strategy
in both untreated arms: contribute until the reserve covers the 42-unit claim,
stop while it remains covered, resume after a claim drains it. A representative
`group` trajectory, `*` marking claim rounds:

```
r2  r3  r4  r5  r6  r7* r8  r9  r10 r11 r12* r13 r14 r15 r16 r17
CC  CC  CC  CR  RR  RR  CC  CC  CC  RR  RR   CC  CC  CC  RR  R-
```

Free-form messages carry the negotiation explicitly. One provider proposes
alternating so that "the reserve stable-to-growing while halving our individual
costs"; the other agrees and they execute it. This is coordinated cost-sharing
under a computable sufficiency condition, not free-riding.

The batch-1 sequences are the same shape. Re-reading the three EXP-039 `group`
trajectories confirms the identical build-hold-rebuild pattern, so the 27
retentions recorded there were also slack harvesting.

## Outcome

**Mixed, and the ladder contrast is not reported.**

Gate A passes on its literal terms: `no_group` produced 15 retentions. It does
not pass on the construct it was written for. The gate was meant to establish a
defection baseline comparable to the human study's 21% non-contribution rate,
and zero of this batch's 32 retentions carried any risk to the service. Reading
this pass as a defection baseline would be wrong.

Gate B fails. Batch 1 had `group` above `no_group` on defection, 28.1% against
12.5%; here the two are indistinguishable, 8.9% against 7.8%, and on the
trajectory measure `group` is lower, 2/6 against 3/6. With three trajectories
per arm in batch 1, that ordering was within noise.

The one effect that replicates cleanly is the pledge: 0 retentions in 384
opportunities across the two pledge arms, against 32 in 384 in the untreated
arms. But since every untreated retention was risk-free optimisation, the effect
is that the pledge **suppresses efficient cost-sharing**, not that it prevents
defection. Agents follow the pledge text literally — contribute 7 every active
round — and the extra contribution buys nothing: all 48 claims were covered in
every arm, including the arms that harvested slack.

This is the same shape as the warehouse result recorded in the collaboration's
channel, where the covenant condition increased effort through duplicated work
without improving service accuracy.

**The instrument is retired for the reason the ladder cannot fix.** Contributing
costs 7; an uncovered claim costs 21 per round for every remaining round, which
at the first decision is roughly 45 to 1 against retaining, and the horizon is
undisclosed so no endgame exists. No state in this world makes retention both
tempting and risky. Five batches have now confirmed it, and a sixth
manipulation of the same world is not licensed.

## Validity limitations

- **The comparison to batch 1 carries a deliberate prompt change.** Both
  templates were rewritten in `070a494`: 274 words to 177, every sentence
  reworded, and the sentence disclosing that conditions are compared removed.
  Retention returning is therefore consistent with the prompt hypothesis but
  does not establish it, because sampling variance across batches is an equally
  live explanation and this batch cannot separate them. The verbatim re-run at
  `e393852` remains the only design that would.
- **Batch 1 had three trajectories per arm.** Its `group` versus `no_group`
  ordering did not survive doubling to six, so it should not have been treated
  as an established direction in the first place.
- **`slack` versus `exposed` is a coverage classification, not a motive.** It
  records whether the reserve could still absorb a claim when the round settled.
  It does not establish what the agent believed, though in this batch the
  free-form negotiation makes the intent unusually legible.
- **Worktree dirty at launch, but only from untracked non-code artifacts.**
  `src/` was fully committed at `070a494`, so the code is reproducible from the
  base commit. This is the first experiment in the EXP-041–044 sequence for
  which that holds.
- **One model, one scenario.** Every run is `claude-sonnet-5` on
  `shared_reserve_commitment`.
- **`seed` is inert.** Recorded for provenance only; no seed-sensitivity claim
  follows.

## What it changed

- Resolves which batch was anomalous: batch 1 reproduces, EXP-040 was the
  outlier. EXP-041, EXP-042, and EXP-043 were built on the premise that the
  ceiling was the instrument's normal behaviour, and that premise was wrong.
- Reclassifies the entire program's primary outcome. `retain` was read as
  defection in every prior record. It is not: in the disclosed world every
  retention observed, in this batch and in batch 1, is risk-free optimisation.
  The parallel drawn to the human study's 21% non-contribution rate does not
  hold, because those are different constructs.
- Retires `shared_reserve_commitment` on a payoff argument rather than an
  information one. The three earlier retirement rationales — claim magnitude,
  computable sufficiency, mutual observability — were all downstream of the
  real cause, which is that contributing dominates by roughly 45 to 1.
- Redirects the program to [STUDY-007](../../studies/STUDY-007-repeated-trust-game.md).
  EXP-026 is the only instrument in this program where the covenant moved
  behaviour (7.17 against 6.00 sent, matching the human +1.46 in direction and
  approximate magnitude) and it stalled on a localised instrument fault: the
  trustee returned 10/21 in all 144 decisions because the received offer is held
  constant at 21. Constant input, constant output.

## Traps found

- **A classifier that reads exposure from the post-claim balance flags every
  claim round as exposed.** The first version of the analysis used
  `reserve_after_claim`, which drops legitimately when a covered claim is paid,
  and reported 6 exposed retentions. Reading from `reserve_before_claim` — the
  reserve as the round's decisions left it — gives the correct 0. The wrong
  number was reported before it was checked against the per-round sequences.
- **Counting actions by grepping the JSONL for `"action":"retain"` overcounts
  fourfold.** The literal appears in `tool_call_invoked`,
  `shared_reserve_decision_recorded`, `tool_result_received`, and
  `llm_response_received` for each decision. Verified against an EXP-039 log
  with a known count of 9, where the grep returned 36. Parse the JSONL and
  filter on `event_type`.
- **"Relaunch the archived configs" is not a verbatim replication when the code
  has moved.** The configs here are byte-identical to batch 1, same SHA-256,
  which makes the knobs verbatim and says nothing about the prompt the agent
  reads. Config identity and stimulus identity are different claims.
- **A four-arm ladder answers nothing when the outcome variable is the wrong
  construct.** Five batches on this world varied the treatment, the claim size,
  and the information regime while never checking whether `retain` meant what
  the records assumed. The per-round sequence and the agents' own messages
  answered it in minutes once inspected.
