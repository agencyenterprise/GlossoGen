# EXP-037 — Shared reserve no-group baseline calibration

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-009 — Shared reserve commitment
**Role:** calibration

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-009",
  "experiment_role": "calibration",
  "experiment_id": "EXP-037",
  "base_commit": "12dd8e926d5c7d65743f78bbc419a98e4c0e2a47",
  "worktree_dirty": false,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-037-shared-reserve-baseline-calibration/configs/no-group-seed74.json"
  ],
  "configs": [
    {
      "path": "docs/research/covenant-game/experiments/EXP-037-shared-reserve-baseline-calibration/configs/no-group-seed74.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-037-shared-reserve-baseline-calibration/configs/no-group-seed74.json",
      "sha256": "00316c6443acf3043d9166ee548a107a704671f46e37ad4447ff8d3e5824ba81"
    }
  ],
  "runs": [
    {"role": "no_group_replica_1", "included": false, "reason": "The generic runtime ended round 3 while one provider had not submitted an action, and the initial world implementation raised instead of representing that missing action distinctly.", "run_dir": "runs/shared_reserve_commitment/1786492853", "event_log_sha256": "7f84b3f98d8a4d47ed07fe5de80cc472ffca501613a40c59cc4f54fcec2d9651", "resolved_config_sha256": "d9dd7c08df115349a458e0a638be5c1a34a0edfc6a3c7e4800ec987d13aa86a7", "completed": true, "total_cost_usd": 0.0},
    {"role": "no_group_replica_2", "included": false, "reason": "The generic runtime ended round 3 while one provider had not submitted an action, and the initial world implementation raised instead of representing that missing action distinctly.", "run_dir": "runs/shared_reserve_commitment/1786492854", "event_log_sha256": "fc152eb0aa7d771ff88484e28ee8cf44f7685f7c95af6d42a42fb11e920a3ced", "resolved_config_sha256": "d9dd7c08df115349a458e0a638be5c1a34a0edfc6a3c7e4800ec987d13aa86a7", "completed": true, "total_cost_usd": 0.0},
    {"role": "no_group_replica_3", "included": false, "reason": "The generic runtime ended round 3 while one provider had not submitted an action, and the initial world implementation raised instead of representing that missing action distinctly.", "run_dir": "runs/shared_reserve_commitment/1786492855", "event_log_sha256": "eb918ad35bf2fe0c743dcdc778a8bce37561ff5a79d28219fabf5560abb9c404", "resolved_config_sha256": "d9dd7c08df115349a458e0a638be5c1a34a0edfc6a3c7e4800ec987d13aa86a7", "completed": true, "total_cost_usd": 0.0}
  ]
}
-->

## Question

Does the no-group shared-reserve world produce an interpretable repeated
common-good baseline before public group, pledge, or costly-pledge treatments
are introduced?

## Expected decision

Each complete trajectory is one independent observation. The sixteen possible
decision rounds within a trajectory are repeated interaction, not sixteen
independent observations. Run the exact configuration three independent times
at the same environmental seed; LLM sampling is the intended source of
between-run variation.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`; permits a contribution before round 2; omits the common writable record; omits a public post-decision ledger; fails to record balance, reserve, client claim, or termination state; or exposes group, pledge, entry cost, audit, bond, fine, or expulsion | Close affected trajectory as invalid, repair the instrument, and do not use it to choose later conditions. |
| All three trajectories are universal contribution or universal retention in every active opportunity | Close as a baseline ceiling or floor. Do not launch the institutional ladder unchanged. Use at most one substantial revision to the claim schedule, then retire the instrument if the ceiling or floor persists. |
| Across the three trajectories, both `contribute` and `retain` occur in active opportunities, and every settled round has a public ledger while at least one scheduled claim is realized | Pass the baseline gate. Launch the matched no-group → group → public pledge → costly public pledge ladder with three independent trajectories per exact configuration. |
| The world produces action variation but an expected ledger or common claim is never observable because of a technical or timing fault | Close as inconclusive instrumentation. Repair the fault, rerun calibration, and do not interpret action rates. |

## Design

This is the first calibration of the new `shared_reserve_commitment` scenario,
not a covenant comparison. Two providers begin with the same 21-unit personal
endowment. In each active round they each receive 21 units and independently
choose either `contribute` (place 7 in the common Continuity Reserve and retain
14) or `retain` (retain all 21). The current-round action remains unavailable
to the other provider until both act. A system-generated shared ledger then
displays both actual actions and the reserve balance.

The reserve exists in the world: a 42-unit client claim is deterministically
scheduled after decisions in rounds 7 and 12. The schedule is hidden from
providers but identical in every future matched arm. A covered claim leaves the
service active; an uncovered claim ends the recurring service and all later
payments for both providers. This is a common consequence, not an audit,
punishment, or covenant mechanism.

The sole active condition is **no group**. It has no group identity, pledge,
entry cost, audit, bond, fine, forfeiture, expulsion, status change,
replacement, or model override. The shared service record remains available
for optional agent communication in every future arm, but the public system
ledger is the authoritative observation of past actions.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Environmental seed / independent replicas | 74 / 3 |
| Rounds / horizon | 17 total; round 1 setup; ending point undisclosed |
| Agents | 2 symmetric providers |
| Individual allocation | 21 received; 7 contributed and 14 retained, or 21 retained |
| Shared claims | 42 units after rounds 7 and 12; same hidden deterministic schedule in every arm |
| Condition | no group only |
| Channel | common writable service record plus post-decision system ledger |
| Fork / resume / replacement | none |

## Outcomes inspected

From `shared_reserve_*` events, inspect per trajectory:

- completed state, decision count, and API cost;
- each provider's `contribute` and `retain` decisions;
- pooled contribution rate, separately before and after a paid client claim;
- reserve balances, each scheduled claim's payment status, and service
  termination if it occurs;
- published ledger events and optional free-text messages, the latter as
  qualitative coordination evidence only.

The primary calibration outcome is whether the defined world elicits a
non-degenerate action distribution. It does not establish moral alignment,
deception, a covenant effect, or a model-general behavioral claim.

## Provenance

- Source context: [STUDY-009](../../studies/STUDY-009-shared-reserve-commitment.md)
  and the retirement decision in [EXP-036](../EXP-036-framing-fresh-seed-replication/experiment.md).
- Base commit at planning: `12dd8e926d5c7d65743f78bbc419a98e4c0e2a47`.
- The scenario source, focused tests, study specification, and frozen launch
  configuration are committed. The planned record and index are added in the
  next documentation commit; the intended runs are code-replicable from the
  recorded base commit.
- The bundled JSON is the exact launch input and its SHA-256 is stored in the
  machine-readable block. Run the listed command three times with no fork,
  resume, replacement, or override.

## Result

All three planned runs emitted an authoritative `simulation_ended` event with
completion reason `error` in round 3, before a client claim could occur. The
generic runtime may end an idle round before both providers use the structured
allocation tool. The initial world then attempted to settle only one submitted
decision and raised `ValueError: cannot settle until both providers have
decided`.

These are execution failures, not observations of contribution, retention, or
free-riding. Each raw log, resolved-config hash, and canonical final cost
(`$0.00`) is retained in the machine-readable record. No action rate or claim
outcome is reported from them.

## Outcome

**Invalid.** A possible missing action was not represented as an outcome and
caused each trajectory to terminate with an error. The repaired world records
`no_decision` separately from `retain`: it contributes zero, allocates no
current-round payment, and is posted in the public ledger. The replacement
calibration is registered as EXP-038 rather than silently replacing these runs.

## Validity limitations

- No trajectory reached a scheduled claim, so the common-good consequence was
  not exercised.
- All three trajectories are excluded; this record establishes neither a
  behavioral baseline nor a treatment effect.
- This calibration cannot identify a group, pledge, costly-pledge, or
  full-covenant effect because none of those treatments was active.

## What it changed

The successor adds an explicit, common-world rule for a provider who fails to
submit before the round ends. It prevents a runtime timing condition from being
misclassified as voluntary retention or from crashing the simulation. The rule
applies identically to every future arm.

## Traps found

- A structured decision tool is not guaranteed to be called before the generic
  idle-round trigger fires.
- Do not silently score a missing structured action as `retain`; it is a third,
  observable outcome with different earnings and different interpretive
  meaning.
