# EXP-042 — Non-computable sufficiency calibration

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-12
**Research program:** covenant-game
**Study:** STUDY-010 — Commitment under non-computable sufficiency
**Role:** calibration

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-010",
  "experiment_role": "calibration",
  "experiment_id": "EXP-042",
  "base_commit": "f4c04c9e09384b28ded6c35aae9167cc44ea63fa",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/no-group-hidden.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/group-hidden.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/pledge-hidden.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/costly-pledge-hidden.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/no-group-hidden.json", "launch_path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/no-group-hidden.json", "sha256": "67a1cadb260e183bbb2e26a731f5ad80c06fe91b7ef6d49bfb430027c0809c5e"},
    {"path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/group-hidden.json", "launch_path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/group-hidden.json", "sha256": "b90905b4537ac3701dffbce7b4983f45bce4148406577bd98f76d0469cf4f452"},
    {"path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/pledge-hidden.json", "launch_path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/pledge-hidden.json", "sha256": "c0603a59b09caca9cf30aa40166d0e38489f81c954f308671b291dc59a8002f3"},
    {"path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/costly-pledge-hidden.json", "launch_path": "docs/research/covenant-game/experiments/EXP-042-non-computable-sufficiency/configs/costly-pledge-hidden.json", "sha256": "75965c94f7a03ee3a7fe2d8425d1bc6d48671e42685a82179019d2c9bc964be2"}
  ],
  "runs": [
    {"role": "no_group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503394", "event_log_sha256": "30f991b3fb305de98e641914c0fe099cfce411be6957e222c66a68d4896f38c2", "resolved_config_sha256": "b8befebc55747b033dad7db2c26797786d233316e3d9d9f1cba6ff36b580d5cc", "completed": true, "total_cost_usd": 0.3674992},
    {"role": "no_group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503395", "event_log_sha256": "bed3f5e65fd5c6f70cf1b6d0fd4270000f9b0362521aa680ed2803097bfc39c3", "resolved_config_sha256": "b8befebc55747b033dad7db2c26797786d233316e3d9d9f1cba6ff36b580d5cc", "completed": true, "total_cost_usd": 0.389382},
    {"role": "no_group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503397", "event_log_sha256": "bbe0be294f96919c30e1424186466f2505c9c30c1a7078fea3b4a1e92843e7d0", "resolved_config_sha256": "b8befebc55747b033dad7db2c26797786d233316e3d9d9f1cba6ff36b580d5cc", "completed": true, "total_cost_usd": 0.3325715},
    {"role": "group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503396", "event_log_sha256": "bbcd805102b0f1d9533d5683a7d4c3407339f450fce3f1912dadc47601a98e8e", "resolved_config_sha256": "aa34f40b6ff5ad025e95f414c146fb9db870f16f03b52bdb356375a3711ff4ce", "completed": true, "total_cost_usd": 0.3630779},
    {"role": "group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503398", "event_log_sha256": "d205c65ce6686f084c63b95a456161cd7b37a627045548c06c232188cf47c154", "resolved_config_sha256": "aa34f40b6ff5ad025e95f414c146fb9db870f16f03b52bdb356375a3711ff4ce", "completed": true, "total_cost_usd": 0.3460957},
    {"role": "group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503400", "event_log_sha256": "924a373ae5f42a21ab753890d218831ae5026d476a544542d28d0d466f345f7e", "resolved_config_sha256": "aa34f40b6ff5ad025e95f414c146fb9db870f16f03b52bdb356375a3711ff4ce", "completed": true, "total_cost_usd": 0.3507112},
    {"role": "pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503402", "event_log_sha256": "9e622862fbfc536a6528a3e860dfa0c7fa1a6c978136ad43952eb9c24fe8f7e9", "resolved_config_sha256": "2bae98be3a3aaf079fccffb154221861e4dfe1dac46882b39641b04db6284f54", "completed": true, "total_cost_usd": 0.4107535},
    {"role": "pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503404", "event_log_sha256": "2e11335d620c48aa409be266be96ec4f42c270e50f80e3a661750f204790832b", "resolved_config_sha256": "2bae98be3a3aaf079fccffb154221861e4dfe1dac46882b39641b04db6284f54", "completed": true, "total_cost_usd": 0.387826},
    {"role": "pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503406", "event_log_sha256": "ffb6ac5c799581b20ceb299d9ea8083be9834c0bfc1c84e1cfaef1f0104dffad", "resolved_config_sha256": "2bae98be3a3aaf079fccffb154221861e4dfe1dac46882b39641b04db6284f54", "completed": true, "total_cost_usd": 0.4110458},
    {"role": "costly_pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503408", "event_log_sha256": "0ac920b860f09b1cc8c1d6d56d254ff28adb0abaef284c8bb003258a9da5ef9a", "resolved_config_sha256": "3304eb93a6266c89fb3e06bb7a2f750ea54b03b6c84a36ace1773142eaa699d5", "completed": true, "total_cost_usd": 0.45017680000000004},
    {"role": "costly_pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503410", "event_log_sha256": "6695362ef3c7d6b806adb45d62db0c6bf7791aaae7e82f38a3e795962f40d32d", "resolved_config_sha256": "3304eb93a6266c89fb3e06bb7a2f750ea54b03b6c84a36ace1773142eaa699d5", "completed": true, "total_cost_usd": 0.45414829999999995},
    {"role": "costly_pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786503412", "event_log_sha256": "fedbe1d3e588b6ed8667e138e0b8134e29d7eeda27afa155fa7c12f0dc480586", "resolved_config_sha256": "3304eb93a6266c89fb3e06bb7a2f750ea54b03b6c84a36ace1773142eaa699d5", "completed": true, "total_cost_usd": 0.479156}
  ]
}
-->

## Question

When the running reserve and the required claim size are both withheld, so that
providers cannot compute whether their accumulated contributions are sufficient,
does the four-arm commitment ladder produce outcome variation — and if it does,
do public group identity, public pledge, and costly public pledge change
persistent contribution?

## Expected decision

This is the calibration for STUDY-010. The instrument gate is primary: this
batch must first demonstrate that the ladder can vary at all under
non-disclosure. Arm contrasts are secondary and must not be interpreted unless
the gate passes.

Twelve trajectories are planned: three independent trajectories per arm. A
trajectory, not one of its sixteen decision rounds, is the independent unit.
Trajectory-level counts are primary; pooled provider-round counts are secondary.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`, condition exposure is absent or incorrect, a pledge arm does not publish both pledge choices, or a costly-pledge affirmation does not produce the 2.1-unit deduction | Mark the affected run invalid and repair the instrument before interpreting the arm. |
| Any provider-visible text still contains the reserve balance or the claim amount | Instrumentation failure: the non-disclosure did not take effect. Mark the batch invalid and repair the templates before re-running. |
| All four arms again reach near-universal contribution and every claim is covered | The ceiling survives non-disclosure, so computability was not the binding cause. Abandon this instrument family for the commitment question rather than revising it again. |
| All or nearly all trajectories lose the service in every arm | Floor: withholding sufficiency removed the measurement opportunity instead of creating it. Abandon rather than tune, and record that the providers could not form a workable contribution norm without a computable target. |
| Outcome variation is restored, and pledge and costly-pledge arms sustain contribution or service continuity more than no-group and group arms | Treat as a *candidate* commitment effect under non-computable sufficiency. Preregister one replication batch before any effect-size claim, and only then consider a covenant arm. |
| Outcome variation is restored but the arms do not separate | Report a null commitment effect under non-computable sufficiency. This is an informative result: it would indicate that public pledges do not change contribution once agents cannot verify sufficiency. |
| Costly pledge differs from pledge-only in uptake or contribution | Report as a separate cost effect only if actual deductions and all pledge choices are verified. EXP-041 recorded one decline in this arm; a second would make declines worth tracking as an outcome rather than an anomaly. |

## Design

The world is unchanged from EXP-041 except for the two disclosure knobs. Two
providers begin with 21 units. Each of the 16 active decision rounds (rounds
2–17; round 1 is setup) grants each provider 21 units and offers `contribute`
(place 7 in the public Continuity Reserve, retain 14) or `retain` (retain all
21). A missed decision is publicly recorded as `no_decision`, adds nothing, and
receives no current-round payment. Fixed 70-unit claims still occur after rounds
7 and 12, and an uncovered claim ends the recurring service and all future
payments for both providers.

**The single changed lever is disclosure**, holding the claim amount at the
binding value EXP-041 established:

| | EXP-041 | This experiment |
|---|---|---|
| `client_claim_amount` | 70 | 70 (unchanged) |
| `reserve_balance_disclosed` | true | **false** |
| `claim_amount_disclosed` | true | **false** |

The world remains fully deterministic. The claim amount and claim rounds are
fixed in configuration and are identical in every arm; they are simply withheld
from the providers, exactly as the 17-round horizon has always been fixed but
undisclosed. No value is randomised, and `seed` reads no code path in this
scenario.

What the providers still observe is unchanged from every prior batch: the public
ledger reports **both providers' actions and contributed amounts every round**,
whether a claim was paid, and whether the service is still active. The shared
consequence therefore remains fully observable. Only the arithmetic answer to
"is what we have accumulated enough?" is removed. This matters because hiding
the balance alone would not suffice — the ledger's per-round contributions let
any agent reconstruct the running total — so it is the withheld *threshold* that
makes sufficiency non-computable.

All four arms use `claude-sonnet-5` through Anthropic, a 17-round undisclosed
horizon, the same two providers, common channel, ledger, payments, claim rounds,
and runtime limits. Each config is launched three times independently, without
fork, resume, replacement, or runtime override.

| Condition | Implemented exposure |
|---|---|
| No group | no group identity and no pledge |
| Group | public registry lists both providers as Shared Service Group members |
| Pledge | group plus a public voluntary affirm-or-decline pledge to contribute 7 in every active round |
| Costly pledge | pledge plus a real one-time 2.1-unit (10%) deduction after affirmation |

The costly-pledge arm remains an entry-cost treatment, not a full covenant. It
introduces no audit, fine, forfeiture, expulsion, replacement, or repair rule.

## Outcomes inspected

- **Non-disclosure verification**: that no provider-visible injection, system
  prompt, or ledger line contains the reserve balance or the claim amount;
- treatment exposure: registry, public pledge affirm/decline, and actual
  entry-cost events;
- **per trajectory**: contribution, retention, and missed-action counts, and
  whether the trajectory contained any retention at all;
- service termination: whether it occurred, in which round, and whether the
  uncovered claim is attributable to `retain` or to `no_decision`;
- coverage margin at each settled claim, as the diagnostic for how close the
  instrument came to binding;
- coordination under uncertainty: whether providers negotiate an explicit
  contribution norm on the shared channel in the absence of a computable target,
  reported separately from action counts;
- pledge uptake and actual cost exposure; and
- canonical completion state and API cost.

The primary outcome is persistent contribution policy at the trajectory level.
This experiment does not establish moral alignment, deception reduction,
full-covenant performance, long-run equilibrium, or a model-general effect.

## Provenance

- Base commit `f4c04c9e09384b28ded6c35aae9167cc44ea63fa`.
- **The worktree is dirty in `src/` for this batch, so the base commit alone
  cannot reproduce the code.** The two disclosure knobs, the two prompt
  conditionals, and the conditional ledger rendering were uncommitted at launch
  time. This record is therefore design-replicable and artifact-verifiable but
  **not code-replicable** until the scenario change is committed. The affected
  files are `knobs.py`, `world.py`, `scenario.py`,
  `prompts/provider_system.jinja`, and `prompts/provider_injection.jinja` under
  `src/glossogen/scenarios/shared_reserve_commitment/`.
- Both new knobs default to `true`, so every STUDY-009 configuration revalidates
  and reproduces its original disclosed behaviour. The six existing scenario
  tests pass unchanged.
- The predecessor record is
  [EXP-041](../EXP-041-binding-claim-stressor/experiment.md), whose analysis
  established the claim value of 70 and identified computable sufficiency as the
  cause of the ceiling.
- The frozen config artifacts and exact commands are in the machine-readable
  block. Each listed command is launched three times, with no fork, resume,
  replacement, or runtime override.
- On closure, derive action counts from `shared_reserve_decision_recorded` and
  `shared_reserve_decision_missed` **per run directory**, exposure from
  `shared_reserve_setup_published`, `shared_reserve_pledge_submitted`, and
  `shared_reserve_entry_cost_paid`, claim outcomes and margins from
  `shared_reserve_round_settled` where `client_claim_due` is true, and
  terminations from `shared_reserve_service_terminated`. Verify non-disclosure
  directly against the recorded agent-visible text. Treat `message_sent` text as
  qualitative only, never as the action measure.

## Result

All twelve trajectories ended with authoritative `simulation_ended` events and
remained active through both claims. Exposure checks passed: the nine group,
pledge, and costly-pledge runs each published their group setup and the three
no-group runs published none; all twelve offered pledge decisions were public
affirmations; and the entry-cost total of 12.6 units equals 2.1 × the six
costly-pledge affirmations.

The non-disclosure gate passed. No provider-visible system prompt, per-round
task, or ledger line in any of the twelve logs contained the running reserve
balance or the 70-unit claim size. The ledger continued to publish both
providers' actions and contributed amounts every round, along with claim
payment and service status.

**The ceiling did not break. It hardened.** Across the 96 provider-round
opportunities per arm:

| Arm | contribute / retain / no_decision | Trajectories with any retention | Terminations |
|---|---|---|---|
| No group | 95 / **0** / 1 | 0 of 3 | 0 of 3 |
| Group | 96 / **0** / 0 | 0 of 3 | 0 of 3 |
| Pledge | 90 / **0** / 6 | 0 of 3 | 0 of 3 |
| Costly pledge | 93 / **0** / 3 | 0 of 3 | 0 of 3 |

There were **zero `retain` actions in the entire batch** — 0 of 384 provider-round
opportunities — so contribution conditional on acting was 100% in all four arms.
The group arm contributed on all 96 opportunities without a single missed action.
EXP-041, under full disclosure, recorded three retentions; withholding
sufficiency removed even those. All 24 claims were paid, no service terminated,
and all twelve trajectories reached the hidden horizon.

The coverage margins show the instrument came close without ever crossing. All
three pledge trajectories settled **both** claims at a reserve of exactly 70
against a 70-unit claim — a margin of zero, twice each, reached without any
ability to verify it. One more missed action in either window would have ended
those services. Margins elsewhere were 7 or 14.

The single pledge decline observed in EXP-041 did not recur: uptake was 6 of 6
in the pledge arm and 6 of 6 in the costly-pledge arm.

Non-contribution was entirely `no_decision` (10 events), concentrated in the
pledge arms (6 and 3), which carry the extra setup-round pledge action.

The event-derived totals were generated by
[`summarize_hidden.py`](analysis/summarize_hidden.py). The batch API cost was
`$4.7424439`.

## Outcome

**Not supported.** The preregistered ceiling row fired: all four arms reached
near-universal contribution and every claim was covered. Per that row's
predeclared decision, computability was **not** the binding cause of the
ceiling, and this instrument family is abandoned for the commitment question
rather than revised again.

This refutes the diagnosis EXP-041 proposed. That record inferred from the
slack-harvesting pattern that a visible balance and a disclosed threshold were
what held the outcome at a ceiling. Removing both — the one intervention that
diagnosis licensed — produced strictly *less* behavioural variation, not more.
The mechanism proposed in EXP-041 is therefore rejected by its own follow-up.

## Validity limitations

- Three trajectories per arm establish neither an effect size nor model-family
  generality; this batch is a ceiling diagnosis, not an estimate.
- A single model (`claude-sonnet-5`) has been used throughout STUDY-009 and
  STUDY-010. The saturation reported here is a property of this model in this
  task and framing, and no model-general claim is supported.
- Zero retentions means no arm contrast is estimable at all. The apparent
  contribution differences (90 to 96 of 96) are differences in missed actions,
  not in policy.
- Withholding the threshold plausibly *increases* conservative contribution,
  since a provider who cannot verify sufficiency has no safe moment to retain.
  This batch cannot separate that mechanism from an unconditional contribution
  prior; both predict what was observed.
- The world is deterministic and `seed` is inert, so this batch shares its
  environment with EXP-041. Only the two disclosure knobs differ.
- The scenario change was uncommitted at launch, so these runs are not
  code-replicable from the base commit alone.

## What it changed

The instrument family is abandoned for the commitment question and STUDY-010 is
closed after one batch. No covenant arm will be run on this world.

The deeper result is about the study series, not this batch. Across four batches
and 48 trajectories on this world, **the entire behavioural signal came from the
first batch**: EXP-038 and EXP-039 produced 39 retentions, and EXP-040, EXP-041,
and EXP-042 produced 3, 0 combined across 36 trajectories. Two successive
mechanistic explanations for the flatness — a non-binding claim schedule
(EXP-041) and computable sufficiency (EXP-042) — were each preregistered, tested,
and refuted. The parsimonious remaining reading is that this model contributes to
an observable common good under essentially any institutional exposure and
information regime here, and that the batch-1 retention was the anomaly rather
than the baseline.

That makes the productive next question a different one: not "which institution
raises contribution?" but "what makes this model retain at all?" Any successor
instrument should first demonstrate, in a no-treatment baseline, that retention
occurs at a usable rate. Building a treatment ladder on top of an outcome that
has not been shown to vary is what consumed four batches here.

## Traps found

- A mechanism inferred from a behavioural pattern is a hypothesis, not a
  finding. EXP-041's slack-harvesting observation was real and its inference was
  reasonable, and testing that inference directly still refuted it. Recording
  the diagnosis as a preregistered gate rather than as a conclusion is what made
  the refutation legible.
- Removing information can suppress variance rather than create it. Withholding
  the threshold left providers with no verifiable moment to retain safely, so
  the conservative action dominated everywhere.
- A margin of exactly zero, reached repeatedly without any termination, is the
  signature of an instrument that is tight but not stochastic. Three pledge
  trajectories sat on the boundary twice each; a deterministic world gives such
  a near miss no chance to become a failure.
- Check whether the outcome varies in a no-treatment baseline *before* building
  a treatment ladder. Four batches and roughly $17 were spent measuring
  institutional exposures against an outcome that turned out not to vary.
- Pooling arms hides that a difference is composed of missed actions rather than
  chosen ones. Here 90 versus 96 contributions is entirely `no_decision`, and
  reporting retention separately is what prevented reading it as a pledge cost.
