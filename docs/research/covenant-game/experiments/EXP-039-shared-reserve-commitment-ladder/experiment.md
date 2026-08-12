# EXP-039 — Shared reserve commitment ladder

**Status:** planned
**Date opened:** 2026-08-11
**Date closed:** —
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
  "runs": []
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

Pending. The treatment trajectories have not been launched.

## Outcome

Pending.

## Validity limitations

Pending. A matched same-seed pilot cannot establish a model-general or
between-seed result.

## What it changed

Pending.

## Traps found

Pending.
