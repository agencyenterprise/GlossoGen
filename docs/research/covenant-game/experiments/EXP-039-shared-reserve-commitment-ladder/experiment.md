# EXP-039 — Shared reserve commitment ladder

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-009 — Shared reserve commitment
**Role:** pilot

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-009",
  "experiment_role": "pilot",
  "experiment_id": "EXP-039",
  "base_commit": "e393852d693754e21af05160c1e25fc393ecec61",
  "worktree_dirty": false,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/group-seed74.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/pledge-seed74.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/costly-pledge-seed74.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/group-seed74.json", "launch_path": "docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/group-seed74.json", "sha256": "36ec11eb069c74e7d5f4c9458688f22274b34dfe85df9149a8fabb5c064afc08"},
    {"path": "docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/pledge-seed74.json", "launch_path": "docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/pledge-seed74.json", "sha256": "9f014e28d694990daccd43fb74ed8af273dc38a383f1510f7a3d379dd6247a0e"},
    {"path": "docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/costly-pledge-seed74.json", "launch_path": "docs/research/covenant-game/experiments/EXP-039-shared-reserve-commitment-ladder/configs/costly-pledge-seed74.json", "sha256": "0643fedb5ff00838ecfcb38fd488bc32d0e862bf3b9628ada754adb0265e7a6b"}
  ],
  "runs": [
    {"role": "group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493976", "event_log_sha256": "9b4dd4b6cb29dfb1a74c328e60b72cd538317ba4008d6004313bb2570939155a", "resolved_config_sha256": "7523ea7f17b0f58ffe74c27d41ce780cd99bf33a545df414c2ace55254e04c60", "completed": true, "total_cost_usd": 0.6260047},
    {"role": "group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493977", "event_log_sha256": "4826a574ebb2d2ee34e48c5e6de49618734d937f779d10fb07451d786e72e3e0", "resolved_config_sha256": "7523ea7f17b0f58ffe74c27d41ce780cd99bf33a545df414c2ace55254e04c60", "completed": true, "total_cost_usd": 0.6461998},
    {"role": "group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493978", "event_log_sha256": "59828bf77b256f60739b82aa877e86da864211904c23d16849040c485e1f5548", "resolved_config_sha256": "7523ea7f17b0f58ffe74c27d41ce780cd99bf33a545df414c2ace55254e04c60", "completed": true, "total_cost_usd": 0.5655951},
    {"role": "pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493974", "event_log_sha256": "ab88f50612bc981579f8f2507a044321cdb9023f81118d24cbd9bf0e0ac8a611", "resolved_config_sha256": "e97f7a3ccde564e00e942656e3dbcc1d778338afc6105aa5723c0443244df96f", "completed": true, "total_cost_usd": 0.4525705},
    {"role": "pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493975", "event_log_sha256": "7748ab97334d69542749e3a841f1e3121355b31ab79ddd4d148ab21cac212bbd", "resolved_config_sha256": "e97f7a3ccde564e00e942656e3dbcc1d778338afc6105aa5723c0443244df96f", "completed": true, "total_cost_usd": 0.4370421},
    {"role": "pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493979", "event_log_sha256": "9084624a7aeca9369f54dfc309da3fc51c4f6d6ae2e49d33737e61e0ea9ac2d2", "resolved_config_sha256": "e97f7a3ccde564e00e942656e3dbcc1d778338afc6105aa5723c0443244df96f", "completed": true, "total_cost_usd": 0.4188996},
    {"role": "costly_pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493980", "event_log_sha256": "86c9fded8278178b57c78db53eb53ee533d3106bfdd5b4e1e4818df22b46677d", "resolved_config_sha256": "4cb99c2ca43b74993028a5fb17a1478aee9fe04e65b4167b901e13da94f4bd83", "completed": true, "total_cost_usd": 0.47466070000000005},
    {"role": "costly_pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493981", "event_log_sha256": "485b70b907755694f53e667f3ed55c6e625e2f3843084fb1976c09f6b67d3e85", "resolved_config_sha256": "4cb99c2ca43b74993028a5fb17a1478aee9fe04e65b4167b901e13da94f4bd83", "completed": true, "total_cost_usd": 0.4364283},
    {"role": "costly_pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786493982", "event_log_sha256": "e8b4696b3ea075ca41bae95b2757e493c9dffabde23b8fc8abe45b788c28d06b", "resolved_config_sha256": "4cb99c2ca43b74993028a5fb17a1478aee9fe04e65b4167b901e13da94f4bd83", "completed": true, "total_cost_usd": 0.4241314}
  ]
}
-->

## Question

In the same repeated common-good world, do public group identity, a public
voluntary pledge, and a real 10% cost on pledge affirmation change contribution
policy or client-service continuity relative to the completed no-group baseline?

## Expected decision

EXP-038 supplies the three no-group trajectories. This record runs each of the
three institutional exposures three independent times with the same model,
environmental seed, claim schedule, and all non-treatment configuration. A
full trajectory is the independent unit; its sixteen decision rounds are not
sixteen independent samples.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`; omits a public group registry in the group arms; omits either public pledge decision in a pledge arm; fails to record a 2.1-unit deduction after costly-pledge affirmation; or exposes a condition-specific rule in the no-group record | Close affected run as invalid and repair the instrument before interpreting conditions. |
| All twelve trajectories retain in every active opportunity, contribute in every active opportunity, or have indistinguishable contribution policies and service continuity | Report the null or ceiling result. Do not add unchanged same-seed replicas; choose a separate stressor or research question. |
| At least two of three trajectories in an exposure show the same directional change in contribution policy, missed actions, or service continuity relative to the three no-group trajectories, with treatment exposure verified | Register a fresh-seed matched replication before claiming a stable effect. |
| Pledge uptake differs substantially across the pledge and costly-pledge arms | Report uptake, refusal, and paid costs separately. Do not condition the contribution estimate only on affirmers. |

## Design

The common world is unchanged from EXP-038. Two providers begin with 21 units;
each active round grants 21 units and offers `contribute` (place 7 in the public
Continuity Reserve and retain 14) or `retain` (retain 21). After both decisions,
a public ledger reports the actions and reserve balance. Identical hidden claims
of 42 are due after rounds 7 and 12. An uncovered claim ends the recurring
service and future payments for both providers. A missing action is recorded as
public `no_decision`, contributes zero, and receives no current-round payment.

The no-group baseline consists of the three included EXP-038 trajectories,
which used the same model (`claude-sonnet-5`), provider, environmental seed
(74), 17-round hidden horizon, channel, claims, balances, and allocation. This
record adds three fresh trajectories for each treatment below; it does not fork
or resume any baseline history.

| Condition | Changed exposure | What does not change |
|---|---|---|
| No group (EXP-038) | no shared group identity or pledge | common reserve, channel, ledger, claims, actions, and payments |
| Group | a public registry lists both providers as members of the Shared Service Group | all common-world mechanics and earnings |
| Pledge | group plus each provider publicly affirms or declines a statement to contribute 7 in every active round | all common-world mechanics and earnings |
| Costly pledge | pledge plus a real one-time 2.1-unit deduction after an affirmation | all common-world mechanics; declining remains possible and does not remove the provider |

The costly-pledge arm is the human-parallel 10% commitment condition, not a
full covenant. It deliberately adds no audit, bond forfeiture, fine, expulsion,
replacement, or repair rule. Thus the progression isolates public group,
commitment language, and the unconditional entry cost more cleanly than the
earlier warehouse institutional bundle.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Environmental seed / replicas per exposure | 74 / 3 |
| Total trajectories | 12 (3 reused no-group + 9 new) |
| Rounds / horizon | 17 total; round 1 setup; ending point undisclosed |
| Agents | 2 symmetric providers |
| Individual allocation | 21 received; 7 contributed and 14 retained, or 21 retained |
| Client claims | 42 after rounds 7 and 12; hidden timing, identical in every arm |
| Channels | one common writable service record plus public post-decision ledger |
| Fork / resume / replacement | none |

## Outcomes inspected

- condition exposure: registry, pledge affirm/decline, and actual entry-cost events;
- contribution, retention, and missed-action rate per provider and trajectory;
- coordinated versus unilateral retention, reported separately from free-riding;
- reserve trajectory, claim coverage, service termination, and hidden-horizon completion;
- optional messages as qualitative coordination evidence only;
- actual cost and all canonical completion states.

The primary outcome is contribution policy under a common consequence; client
continuity is a separate outcome. This pilot does not establish moral alignment,
deception reduction, a full-covenant effect, long-run equilibrium, or a
component-level causal effect beyond the specified exposure comparisons.

## Provenance

- The source implementation and missing-action repair are committed at
  `cf1c611ab47702071fd5a6d4086f5ae20040dfcc`. The no-group source runs,
  exact hashes, and action summary are closed in EXP-038.
- This record's frozen config artifacts and exact launch commands appear in the
  machine-readable block and are committed before launch. Run each listed
  command three independent times without fork, resume, replacement, or overrides.
- The same seed matches the hidden claim environment but does not make LLM
  trajectories deterministic. Fresh-seed replication is required for any stable
  treatment claim.

## Result

All nine treatment trajectories ended with authoritative `simulation_ended`
events and kept the service active through both scheduled claims. The group
registry appeared in every run. In the pledge and costly-pledge arms, all six
providers publicly affirmed. Each costly-pledge affirmation generated its real
2.1-unit deduction, for 12.6 units of recorded enrollment cost in total.

Across 96 possible provider-round actions per condition, the completed group
runs recorded 66 contributions, 27 retentions, and 3 public `no_decision`
outcomes. The pledge runs recorded 95 contributions, zero retentions, and one
`no_decision`; costly pledge produced the same 95/0/1 pattern. The completed
no-group baseline from EXP-038 recorded 84 contributions, 12 retentions, and
zero missed actions. All claims were paid in all twelve trajectories, so there
is no client-continuity contrast in this batch.

The same-seed directional pattern is therefore: group identity alone had less
contribution than the completed no-group baseline, while public pledge and
costly public pledge had near-universal contribution. The costly entry cost did
not visibly add to the pledge-only pattern in these three trajectories.

Analysis rule: count `shared_reserve_decision_recorded.action` and
`shared_reserve_decision_missed` per available action opportunity; verify group
and pledge exposure from `shared_reserve_setup_published` and
`shared_reserve_pledge_submitted`; verify the actual cost from
`shared_reserve_entry_cost_paid`; and select claim outcomes from
`shared_reserve_round_settled` where `client_claim_due` is true. The no-group
comparison values are reproduced from the closed EXP-038 record; its raw runs
and cost remain attributed there. Optional free-text messages are qualitative
only.

The nine newly launched trajectories cost `$4.4815322` in total.

## Outcome

**Supported as a same-seed directional mechanism result, not as a stable
effect.** The prespecified exposure checks passed, and all three pledge and all
three costly-pledge trajectories moved to near-universal contribution. The
group-only trajectories instead used substantial retention while still covering
claims. The next required decision is a fresh-seed matched replication before
claiming that public pledge, or its cost, changes behavior reliably.

## Validity limitations

- The same seed fixes the claim environment, not the LLM trajectory. Three
  replicas per arm are a pilot and cannot establish a between-seed,
  model-general, or statistical result.
- Client continuity is at a ceiling: all claims were covered in every arm.
  This batch distinguishes contribution policy but not recovery after failure
  or a continuity advantage.
- Pledge uptake was universal. The costly-pledge contrast estimates the effect
  of being offered a costly pledge, not an effect conditional on affirming.
- The costly-pledge arm is still not a full covenant: it has no enforcement,
  forfeiture, expulsion, replacement, or repair mechanism.

## What it changed

The experiment supplies a clean candidate mechanism contrast. A fresh-seed
replication should retain the frozen common world and run the same three
replicas per arm before any statement about a pledge effect. If the contrast
does not repeat, report it as seed- or trajectory-specific; if it repeats,
design a separate stress test for free-riding, failed claims, and repair.

## Traps found

- A public group label is not necessarily a weaker form of a pledge. In this
  batch it coincided with more retention, not less.
- Do not equate full client continuity with full contribution: group providers
  retained in 27 available actions while every claim remained covered.
- Do not claim that the 10% cost improved contribution beyond pledge from these
  data; the pledge-only and costly-pledge patterns were the same here.
