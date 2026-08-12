# EXP-038 — Repaired shared reserve no-group baseline calibration

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
  "experiment_id": "EXP-038",
  "base_commit": "cf1c611ab47702071fd5a6d4086f5ae20040dfcc",
  "worktree_dirty": false,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-038-shared-reserve-baseline-repair/configs/no-group-seed74.json"
  ],
  "configs": [
    {
      "path": "docs/research/covenant-game/experiments/EXP-038-shared-reserve-baseline-repair/configs/no-group-seed74.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-038-shared-reserve-baseline-repair/configs/no-group-seed74.json",
      "sha256": "00316c6443acf3043d9166ee548a107a704671f46e37ad4447ff8d3e5824ba81"
    }
  ],
  "runs": [
    {"role": "no_group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493295", "event_log_sha256": "2c5c346bd394d80133c3733c050fec5b2ee916acfa27432aaf5f9311496f6a36", "resolved_config_sha256": "d9dd7c08df115349a458e0a638be5c1a34a0edfc6a3c7e4800ec987d13aa86a7", "completed": true, "total_cost_usd": 0.47659190000000007},
    {"role": "no_group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493296", "event_log_sha256": "fbccf1d846c2ee98e163196bebb612fb481a8c15532b77c1b789c62e0cccbe2b", "resolved_config_sha256": "d9dd7c08df115349a458e0a638be5c1a34a0edfc6a3c7e4800ec987d13aa86a7", "completed": true, "total_cost_usd": 0.4377653},
    {"role": "no_group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493297", "event_log_sha256": "19b0c7e6a55d5f18988c7a6e2c8b5e825c66b5d9fbe7ed7aa20a44fad8f2d179", "resolved_config_sha256": "d9dd7c08df115349a458e0a638be5c1a34a0edfc6a3c7e4800ec987d13aa86a7", "completed": true, "total_cost_usd": 0.5139556000000001}
  ]
}
-->

## Question

Does the repaired no-group shared-reserve world produce an interpretable
repeated common-good baseline before public group, pledge, or costly-pledge
treatments are introduced?

## Expected decision

Each complete trajectory is one independent observation. The sixteen possible
decision rounds within a trajectory are repeated interaction, not sixteen
independent observations. Run the exact configuration three independent times
at the same environmental seed; LLM sampling is the intended source of
between-run variation.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`; permits a contribution before round 2; omits the common writable record; omits a public post-decision ledger; fails to record balance, reserve, client claim, termination state, or a distinct `no_decision`; or exposes group, pledge, entry cost, audit, bond, fine, or expulsion | Close affected trajectory as invalid, repair the instrument, and do not use it to choose later conditions. |
| All three trajectories are universal contribution or universal retention in every active opportunity | Close as a baseline ceiling or floor. Do not launch the institutional ladder unchanged. Use at most one substantial revision to the claim schedule, then retire the instrument if the ceiling or floor persists. |
| Across the three trajectories, both `contribute` and `retain` occur in active opportunities, no unresolved missing action remains, every settled round has a public ledger, and at least one scheduled claim is realized | Pass the baseline gate. Launch the matched no-group → group → public pledge → costly public pledge ladder with three independent trajectories per exact configuration. |
| The world produces action variation but an expected ledger or common claim is never observable because of a technical or timing fault | Close as inconclusive instrumentation. Repair the fault, rerun calibration, and do not interpret action rates. |

## Design

This is the repaired calibration of the new `shared_reserve_commitment`
scenario, not a covenant comparison. Two providers begin with the same 21-unit
personal endowment. In each active round they each receive 21 units and
independently choose either `contribute` (place 7 in the common Continuity
Reserve and retain 14) or `retain` (retain all 21). The current-round action
remains unavailable to the other provider until the round settles. A
system-generated shared ledger then displays both actual actions and the reserve
balance.

If the runtime ends an active round before a provider submits either action,
the world now records `no_decision`: that provider contributes zero, receives no
current-round payment, and is shown distinctly in the public ledger. It is not
silently scored as `retain`. This execution rule is shared by every future
condition and does not introduce a group, pledge, audit, or sanction.

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
| Missing action | zero contribution, zero current-round allocation, public `no_decision` |
| Shared claims | 42 units after rounds 7 and 12; same hidden deterministic schedule in every arm |
| Condition | no group only |
| Channel | common writable service record plus post-decision system ledger |
| Fork / resume / replacement | none |

## Outcomes inspected

From `shared_reserve_*` events, inspect per trajectory:

- completed state, decision count, missed-action count, and API cost;
- each provider's `contribute`, `retain`, and `no_decision` outcomes;
- pooled contribution rate, separately before and after a paid client claim;
- reserve balances, each scheduled claim's payment status, and service
  termination if it occurs;
- published ledger events and optional free-text messages, the latter as
  qualitative coordination evidence only.

The primary calibration outcome is whether the defined world elicits a
non-degenerate action distribution. It does not establish moral alignment,
deception, a covenant effect, or a model-general behavioral claim.

## Provenance

- This record succeeds the invalid EXP-037 attempt. The source repair is
  committed at `cf1c611ab47702071fd5a6d4086f5ae20040dfcc`; the planned record
  and frozen configuration are committed immediately before launch.
- The bundled JSON is the exact launch input and its SHA-256 is stored in the
  machine-readable block. Run the listed command three times with no fork,
  resume, replacement, or override.
- Closure will include each event-log and resolved-config hash, completion
  state, and final API cost from the authoritative `simulation_ended` event.

## Result

All three independent no-group trajectories ended with authoritative
`simulation_ended` events (`scenario_complete`). Every active round settled
and published a public ledger: 48 settled decision rounds total, zero
`no_decision` events, and six scheduled client claims, all covered. The service
therefore reached the hidden horizon in all three trajectories.

Two trajectories recorded 32/32 contributions each. The third recorded 20
contributions and 12 retentions, six by each provider. In that trajectory the
providers used the visible reserve balance to coordinate a buffer policy: they
contributed until it reached 56, jointly retained while it remained above the
known 42-unit claim amount, and rebuilt it after each paid claim. It therefore
retained 12 allocations without abandoning the common service.

The pooled action count is 84 contributions and 12 retentions out of 96
submitted actions. Total canonical API cost was `$1.4283128`.

Analysis rule: from each canonical JSONL log, count
`shared_reserve_decision_recorded.action`; count
`shared_reserve_decision_missed`; count
`shared_reserve_round_settled` and select records where `client_claim_due` is
true; and use `shared_reserve_ledger_published` for ledger coverage. Treat
`message_sent` text only as qualitative explanation, never as the action
measure.

## Outcome

**Supported.** The repaired no-group instrument passed its prespecified
instrumentation and variation gates. It produced both contribute and retain
actions, a genuine observable common consequence, and complete public ledgers
without a universal contribution or retention outcome across all trajectories.
This licenses the matched group → public pledge → costly public pledge ladder.

## Validity limitations

- Two of three trajectories contributed in every active opportunity, and none
  showed unilateral free-riding or an uncovered claim. The baseline is viable,
  but these three runs do not establish that informal coordination fails.
- The two claims were known in amount but hidden in timing. The buffer strategy
  may depend on this particular claim amount and schedule.
- Same-seed replicas estimate LLM sampling variation at this environment; they
  do not establish a between-seed or model-general pattern.
- This calibration cannot identify a group, pledge, costly-pledge, or
  full-covenant effect because none of those treatments was active.

## What it changed

The instrument is sufficiently implemented and non-degenerate to use the three
completed no-group trajectories as the matched baseline in the planned
institutional ladder. The next record changes only the documented group and
pledge exposures while retaining this model, seed, claim schedule, channel,
horizon, endowment, and allocation.

## Traps found

- Do not equate retention with free-riding. In one trajectory both providers
  retained symmetrically under a public, reserve-sustaining buffer rule.
- Service continuity alone is not enough: the same outcome occurred under full
  contribution and under the less costly coordinated buffer policy.
- A missed tool action is distinct from retention and must remain separately
  visible in both the event log and public ledger.
