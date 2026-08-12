# EXP-043 — Sealed observation with the pledge as the sole social signal

**Status:** complete
**Date opened:** 2026-08-12
**Date closed:** 2026-08-12
**Research program:** covenant-game
**Study:** STUDY-011 — Public pledge as the sole social signal
**Role:** calibration

<!-- experiment-record:v2
{
  "base_commit": "f4c04c9e09384b28ded6c35aae9167cc44ea63fa",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/no-group-sealed.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/group-sealed.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/pledge-sealed.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/costly-pledge-sealed.json"
  ],
  "configs": [
    {
      "path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/no-group-sealed.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/no-group-sealed.json",
      "sha256": "c2df3cf73aabb6be98dbf2ad87ea912c2eaee072370fc1e18c950efef4b0c1af"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/group-sealed.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/group-sealed.json",
      "sha256": "d84a86c3f8215454930f1015e5b5f3e773de7c14e809238a65a4ce8c32a90de8"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/pledge-sealed.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/pledge-sealed.json",
      "sha256": "8461e6277bfbbc74f040362069d51dfffb31e8f3227d73322b3005ee9aa239df"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/costly-pledge-sealed.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-043-sealed-observation-pledge/configs/costly-pledge-sealed.json",
      "sha256": "c606af3d9c0cfc0422ca8e1775c6c7fce58c92c68a395c82b0007b684c6987f2"
    }
  ],
  "experiment_id": "EXP-043",
  "experiment_role": "calibration",
  "research_program": "covenant-game",
  "runs": [
    {"run_dir": "runs/shared_reserve_commitment/1786505339", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "20288cab259ac2a066e96e57fea4d46a4ccf5d6cec632c9e96799d0e47dd7d11", "resolved_config_sha256": "e43385ba71de5b988e5bf3d0af85feb64d863f3817a58b9c2883c94a5f4aa5cf", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.0956825},
    {"run_dir": "runs/shared_reserve_commitment/1786505340", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "f5e0759ecfb671af1b579ccb6cbfdb6e23aa1ca7436350065dfb0adf103a1308", "resolved_config_sha256": "e43385ba71de5b988e5bf3d0af85feb64d863f3817a58b9c2883c94a5f4aa5cf", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.09482750000000001},
    {"run_dir": "runs/shared_reserve_commitment/1786505342", "role": "no_group", "included": true, "completed": true, "event_log_sha256": "9fc9ddf420231b768f48c18d8b932400a5de8b6165c535122ee3ea1692e3a941", "resolved_config_sha256": "e43385ba71de5b988e5bf3d0af85feb64d863f3817a58b9c2883c94a5f4aa5cf", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.09003420000000001},
    {"run_dir": "runs/shared_reserve_commitment/1786505344", "role": "group", "included": true, "completed": true, "event_log_sha256": "4452d1960eafdd800e72c2cf77c78ba431882b7b59be72a3ae47f31824c32f25", "resolved_config_sha256": "f7b612436a1d58cfe529816c5ee095e30017255afa998dd339a03fb9b35ac8b3", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.1080323},
    {"run_dir": "runs/shared_reserve_commitment/1786505346", "role": "group", "included": true, "completed": true, "event_log_sha256": "6b0be25e19d7d4ea3f10475bf42e05ad35509167b045f595dd6b8e0c6da3e4a4", "resolved_config_sha256": "f7b612436a1d58cfe529816c5ee095e30017255afa998dd339a03fb9b35ac8b3", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.09187110000000001},
    {"run_dir": "runs/shared_reserve_commitment/1786505348", "role": "group", "included": true, "completed": true, "event_log_sha256": "9649bd6c1890024c14cc50901b42697439028ab7677e77b6e05a89d13b2a5626", "resolved_config_sha256": "f7b612436a1d58cfe529816c5ee095e30017255afa998dd339a03fb9b35ac8b3", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.095696},
    {"run_dir": "runs/shared_reserve_commitment/1786505350", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "4c6722dca28d12b079f170d69abfa47dba87db33c577d52e0142b77c53612c71", "resolved_config_sha256": "91741bc496f4636ce72b310198ab882a77d4508e01600cd661c7e2aa4c11b2c8", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.1113385},
    {"run_dir": "runs/shared_reserve_commitment/1786505352", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "56b8fb70f30cda553457e7eb50889356a4095a9e17303e57c7080d74f4b4e1ab", "resolved_config_sha256": "91741bc496f4636ce72b310198ab882a77d4508e01600cd661c7e2aa4c11b2c8", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.1048529},
    {"run_dir": "runs/shared_reserve_commitment/1786505355", "role": "pledge", "included": true, "completed": true, "event_log_sha256": "6afac953915b92d831610a3f723b274dac964a4ef38a981140e928a18e39ef80", "resolved_config_sha256": "91741bc496f4636ce72b310198ab882a77d4508e01600cd661c7e2aa4c11b2c8", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.10551340000000001},
    {"run_dir": "runs/shared_reserve_commitment/1786505357", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "f230a0ac6b3cf0603e7c319251ddc93d97ad4f2ccd2ffb14759300c650c6f32a", "resolved_config_sha256": "7d4822caf292c00042b0aaa9c8769bfb30a50b3207fce875c4068c0a49c4b2a7", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.1166296},
    {"run_dir": "runs/shared_reserve_commitment/1786505359", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "829e1de059030f7b2a67fc7efd988e55b8bbdd981652ef218c5670a52f37d59d", "resolved_config_sha256": "7d4822caf292c00042b0aaa9c8769bfb30a50b3207fce875c4068c0a49c4b2a7", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.1163047},
    {"run_dir": "runs/shared_reserve_commitment/1786505361", "role": "costly_pledge", "included": true, "completed": true, "event_log_sha256": "543d729ab95dcb022aed470b1cdabbd779b638f7d0d0bcd889b5048172c9c366", "resolved_config_sha256": "7d4822caf292c00042b0aaa9c8769bfb30a50b3207fce875c4068c0a49c4b2a7", "model": "claude-sonnet-5", "provider": "anthropic", "seed": 75, "configured_rounds": 17, "completion_reason": "scenario_complete", "total_cost_usd": 0.11173430000000001}
  ],
  "schema_version": 2,
  "study_id": "STUDY-011",
  "worktree_dirty": true
}
-->

## Question

When every observation channel except a public pledge is removed, does providers'
contribution to a shared continuity reserve stop being unconditional?

## Expected decision

A non-zero retention floor licenses building a treatment ladder — including a
covenant arm — on this world. A floor that stays at zero retires
`shared_reserve_commitment` as an instrument for institutional-treatment
questions, and the program stops asking which institution raises contribution
and starts asking what makes this model retain at all.

## Design

Four arms — `no_group`, `group`, `pledge`, `costly_pledge` — three independent
trajectories each, twelve runs, `claude-sonnet-5` / `anthropic`. The trajectory
is the unit; rounds within one trajectory are not independent replications.

The control is [EXP-042](../EXP-042-non-computable-sufficiency/experiment.md),
not EXP-041. Every knob is inherited from EXP-042's configs — claim 70, claim
amount undisclosed, reserve balance undisclosed, 17 rounds, claims at rounds 7
and 12 — and exactly two knobs change:

| Knob | EXP-042 | EXP-043 |
|---|---|---|
| `ledger_visibility` | `full` | `none` |
| `free_form_messages_enabled` | `true` | `false` |

Together these remove the public continuity ledger and withhold the runtime's
communication tools, so a provider cannot publish anything and cannot read the
shared record. The pledge remains, and in the pledge arms the other provider's
pledge choice is delivered **in the per-round injection** rather than left in the
record, since a provider without `read_channel` could not otherwise observe it.

**Why the control cannot be EXP-041.** In this world the running reserve balance
*is* an observation channel: a provider who sees the reserve and knows its own
contribution derives the other's action by subtraction. Partner observability
therefore cannot be removed while the balance stays visible. The knobs model now
rejects that combination outright rather than allowing a sealed arm that seals
nothing.

**What a provider can observe after this change:** its own cumulative balance,
its own past actions, whether the service is still active, and — in the pledge
arms — both standing pledge choices. Nothing else.

## Outcomes inspected

- **Retention floor (primary):** `retain` actions over total decision
  opportunities, per arm, with trajectories carrying at least one retention
  reported alongside the raw count.
- **Service continuity:** whether each of the two claims was covered and whether
  the service reached round 17.
- **Pledge uptake and cost exposure:** affirm/decline counts and actual 2.1-unit
  deductions.
- **Missed decisions:** `no_decision` settlements, which are not retentions and
  are counted separately.

**Manipulation checks (run before any outcome is read).** A run is excluded if
either fails: no `shared_reserve_ledger_published` event may appear in its JSONL,
and no provider-authored message may appear on the shared record.

### Preregistered gates

1. **Gate A — floor activation.** The `no_group` arm must produce at least one
   `retain` action across its three trajectories. This is the only gate whose
   failure is decisive on its own.
2. **Gate B — ladder interpretability.** Evaluated only if Gate A passes.
   Treatment arms are compared to `no_group` on trajectories-with-retention.
   If Gate A fails, no arm-versus-arm contrast is reported, because a saturated
   outcome leaves no headroom for any treatment to move.
3. **Gate C — retirement.** If Gate A fails and pooled retention across all four
   arms is at or below the EXP-041 level of three actions, `shared_reserve_commitment`
   is retired as an instrument for institutional-treatment questions and STUDY-011
   closes with it. No further arm — including covenant — is run on this world.

Gate C firing is a real outcome, not a null to be worked around. It is recorded
as such and the gates above are not revised after results are seen.

## Provenance

- Base commit: `f4c04c9e09384b28ded6c35aae9167cc44ea63fa`
- Worktree dirty at planning: `true`
- Exact command: see `commands` in the machine-readable block
- Config: the four bundled `configs/*-sealed.json`, hashed above
- Model/provider: `claude-sonnet-5` / `anthropic`
- Seed: 75 in every config, and inert — this scenario reads no seed and has no
  RNG. This is not a fresh-seed replication and no seed-sensitivity claim follows
  from it.
- Rounds: 17 configured; claims at rounds 7 and 12
- Source/fork boundary: none; these are fresh runs

## Result

All twelve runs completed with `simulation_ended` and reached round 17. Both
manipulation checks passed on every run: zero `shared_reserve_ledger_published`
events and zero provider-authored messages on the shared record. Derived by
`analysis/summarize_sealed.py` from the run logs.

**The batch contains no behavioural variance of any kind.**

| Arm | Trajectories | contribute | retain | no_decision | Trajectories with retention | Terminations | affirm/decline |
|---|---|---|---|---|---|---|---|
| `no_group` | 3 | 96 | **0** | 0 | 0 | 0 | — |
| `group` | 3 | 96 | **0** | 0 | 0 | 0 | — |
| `pledge` | 3 | 96 | **0** | 0 | 0 | 0 | 6/0 |
| `costly_pledge` | 3 | 96 | **0** | 0 | 0 | 0 | 6/0 |

Every provider contributed in every one of the 16 decision rounds of all twelve
trajectories: **384 contributions in 384 opportunities.** Every run recorded 32
contributions. Not one retention and not one missed decision occurred.

Because contribution was total and uniform, the world produced a single
trajectory twelve times. All 24 claim settlements are identical: reserve 84
against a claim of 70, margin 14, paid, at both round 7 and round 12 in every
run. `round_success` is 16/16 on every run; `content_filter_refusal` and
`round_ended_timeout` are 0 everywhere.

Pledge uptake was unanimous: 6 affirmations and 0 declines in each pledge arm,
with all six entry costs paid in `costly_pledge`. The single decline seen in
EXP-041 did not recur.

Total API cost: **$1.2425**, roughly a quarter of EXP-042's $4.74. The trimmed
prompts, the absent ledger, and the withheld communication tools together cut
token consumption sharply.

### Across the program

| Batch | Manipulation | Retentions in 12 trajectories |
|---|---|---|
| EXP-038 + EXP-039 | baseline ladder | 39 |
| EXP-040 | repeat of the ladder | 0 |
| EXP-041 | client claim 42 → 70 | 3 |
| EXP-042 | reserve balance and claim amount withheld | 0 |
| EXP-043 | observation sealed; pledge sole social signal | **0** |

## Outcome

**Not supported. Gate A failed and Gate C fired.**

Gate A required at least one `retain` in the `no_group` arm; the arm produced
none. Under the preregistered rule no arm-versus-arm contrast is reported from
this batch, so nothing is claimed about whether group identity, a public pledge,
or a costly pledge changes contribution here.

Gate C required pooled retention at or below three actions; pooled retention was
zero. `shared_reserve_commitment` is therefore retired as an instrument for
institutional-treatment questions, and STUDY-011 closes with it. No covenant arm
was run, and the condition for running one was never met.

Three preregistered mechanistic explanations for the ceiling have now been
tested and all three are refuted: claim magnitude (EXP-041), computable
sufficiency (EXP-042), and mutual observability (EXP-043). The parsimonious
reading left standing is that this model contributes in this world under every
institutional exposure and every information regime tried, and that the 39
retentions of the first batch are the anomaly rather than the baseline.

## Validity limitations

- **The contrast against EXP-042 is confounded at the artifact level.** The two
  knobs were introduced in the same change that rewrote both prompt templates —
  removing a sentence that told providers the claim schedule is shared across
  conditions, deleting statements that the sealed design would have made false,
  and cutting the per-round injection by roughly two thirds. EXP-043 therefore
  differs from EXP-042 by more than `ledger_visibility` and
  `free_form_messages_enabled`. This does not touch the conclusion, because Gate
  A is an absolute test of whether retention occurs at all rather than a
  comparison; but no claim of the form "sealing observation caused X relative to
  EXP-042" is supported by this batch.
- **The drop in missed decisions is not interpreted as a behavioural change.**
  EXP-042 recorded 10 `no_decision` settlements and EXP-043 none. A shorter
  prompt and a smaller toolset plausibly reduce the chance of a provider failing
  to act within the round, so this is read as an artifact of the instrument, not
  as increased commitment.
- **Not code-replicable.** The runs were launched from a dirty worktree: the
  scenario changes that make this design possible — the two knobs, the knobs
  validator, the deterministic pledge delivery, and both prompt templates — were
  uncommitted at launch. The recorded base commit does not reproduce the code
  that produced these logs. The event logs and resolved configs are hashed and
  artifact-verifiable.
- **One model, one scenario.** Every run is `claude-sonnet-5` on
  `shared_reserve_commitment`. Nothing here generalises to other models, and the
  retirement applies to this instrument rather than to the research question.
- **`seed` is inert.** It is recorded for provenance only; this scenario has no
  RNG. Runs differing only in `seed` are the same environment, and no
  seed-sensitivity claim follows.
- **Channel metrics were excluded, not run and found empty.** With free-form
  messages withheld the shared record carries only scenario-authored text, so
  throughput, perplexity, and the language-emergence judges have no valid input.

## What it changed

- `shared_reserve_commitment` is retired as an instrument for
  institutional-treatment questions. STUDY-011 closes after one batch, as
  STUDY-010 did.
- The program's question changes. After five batches, 60 trajectories, and
  roughly $18, the productive question is no longer which institution raises
  contribution but what makes this model retain at all. Any successor instrument
  must demonstrate a usable retention rate in a no-treatment baseline before a
  treatment ladder — covenant included — is built on it.
- The scenario gained two reusable knobs and one structural guard. The knobs
  model now rejects `ledger_visibility` other than `full` combined with
  `reserve_balance_disclosed`, so no future arm can hide the ledger while
  publishing the balance and believe it has sealed observation.
- `ledger_visibility` retains an unused `outcome_only` setting that separates
  loss of partner observability from loss of outcome feedback. It was never
  needed here because the floor never activated.

## Traps found

- **Withholding communication also withholds reading.** Setting
  `communication_enabled=False` removes `send_message` and `read_channel`
  together, since both live in `BASE_TOOL_NAMES`. The pledge announcement is
  delivered as a pointer — the runtime pushes a "new messages" notification and
  the content is only retrievable through `read_channel` — so a sealed provider
  would have been told something was published and been unable to read it,
  silently voiding the treatment it was meant to carry.
- **Discretionary reading is unreliable and asymmetric.** A smoke run under the
  discretionary design recorded `provider_b` calling `read_channel` once and
  `provider_a` never calling it. The pledge would have been observed on one side
  only, and nothing in the event log would have flagged it. Delivery is now
  deterministic through the per-round injection.
- **The reserve balance is an observation channel.** A provider who sees the
  running reserve and knows its own contribution derives the other's action by
  subtraction, so partner observability cannot be removed while the balance
  stays visible. Encoded as a knobs validator rather than left to reviewer
  vigilance.
- **The prompt told providers they were in an experiment.** The system prompt
  carried "The same hidden claim schedule is used in every condition", which
  discloses that conditions are being compared. A model that knows it is being
  compared across arms has reason to behave consistently across arms — the
  precise null this program kept recording. It was present in EXP-037 through
  EXP-042 and removed here. Its removal did **not** produce retention, so it is
  not on its own the explanation for the earlier flatness; what this batch cannot
  do is isolate how much it contributed, since it was removed in the same change
  as everything else.
- **`declare -A` is unavailable in the bash on this host.** An associative-array
  lookup in the hash-collection script degraded to an indexed array and happened
  to produce correct output only because the run ids are numeric. Verified
  against the analysis table rather than trusted.
