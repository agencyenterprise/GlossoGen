# EXP-041 — Binding claim stressor

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-009 — Shared reserve commitment
**Role:** stress-test

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-009",
  "experiment_role": "stress-test",
  "experiment_id": "EXP-041",
  "base_commit": "f4c04c9e09384b28ded6c35aae9167cc44ea63fa",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/no-group-claim70.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/group-claim70.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/pledge-claim70.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/costly-pledge-claim70.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/no-group-claim70.json", "launch_path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/no-group-claim70.json", "sha256": "500b74d6c544fdc1576ce878ff5e9f3e9797ad1d494e6d6b7820905ed23a3bec"},
    {"path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/group-claim70.json", "launch_path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/group-claim70.json", "sha256": "a5394aec057631ab5c6e836ac1489597cb6780d328582bf80082b84961c77a17"},
    {"path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/pledge-claim70.json", "launch_path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/pledge-claim70.json", "sha256": "e89fd6e5b7846878c2bf633dc158ac4a29b8be09e2f2e02967e26996375f4aac"},
    {"path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/costly-pledge-claim70.json", "launch_path": "docs/research/covenant-game/experiments/EXP-041-binding-claim-stressor/configs/costly-pledge-claim70.json", "sha256": "bc400683461bdc0e549cae0ecfa60db41dea8725315d0f7deca75a1ecfc060a9"}
  ],
  "runs": [
    {"role": "no_group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501625", "event_log_sha256": "ab4b00361882279abdb077db9059fba053e86270ad0f22bf68acbd9cb229ef17", "resolved_config_sha256": "a50bcab0594e7dd921504173d3f37c672d530d5f37d48effd435791e426378ea", "completed": true, "total_cost_usd": 0.49444170000000004},
    {"role": "no_group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501626", "event_log_sha256": "35776fe74cf9aeddcf22df98ccf9edd5216f06bd3dfbb83c9af72cf9be15be61", "resolved_config_sha256": "a50bcab0594e7dd921504173d3f37c672d530d5f37d48effd435791e426378ea", "completed": true, "total_cost_usd": 0.5168464000000002},
    {"role": "no_group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501628", "event_log_sha256": "b262d5578ae7873569b022e7569630c018783edcba4f8d868dc68413511f28c8", "resolved_config_sha256": "a50bcab0594e7dd921504173d3f37c672d530d5f37d48effd435791e426378ea", "completed": true, "total_cost_usd": 0.3784331},
    {"role": "group_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501630", "event_log_sha256": "b311759e4ec75bc85b6653ec342f921995751bee3da2865528be1dd94c91684f", "resolved_config_sha256": "898a62ba6afffa81eaf3375a4eeda5d65e79e42bee54a2b931eba5eb6589b4fd", "completed": true, "total_cost_usd": 0.5954965},
    {"role": "group_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501632", "event_log_sha256": "0f700f70c14360a369e2ab053b19fd583e5f074c7c6c1b96ddecdd20e562c2b7", "resolved_config_sha256": "898a62ba6afffa81eaf3375a4eeda5d65e79e42bee54a2b931eba5eb6589b4fd", "completed": true, "total_cost_usd": 0.4118196},
    {"role": "group_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501634", "event_log_sha256": "41de4644b825bf6ee9b04ed59eb8ff25ef41305a91e4aaa9fb6511523a918abc", "resolved_config_sha256": "898a62ba6afffa81eaf3375a4eeda5d65e79e42bee54a2b931eba5eb6589b4fd", "completed": true, "total_cost_usd": 0.3891295},
    {"role": "pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501636", "event_log_sha256": "6d0f767953489e2abe5e20f02d774c47be838ff50968aa65ba99fdb59419f9b4", "resolved_config_sha256": "63f22788bddaf2cfde23c05a66349bd30ba7c65ce664be272a116eb8e0519acc", "completed": true, "total_cost_usd": 0.4228971},
    {"role": "pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501638", "event_log_sha256": "cc2ed9eb83062f1e1fb3f40733fe505a9043880b2b4d7f9a9d24406949f9dcf5", "resolved_config_sha256": "63f22788bddaf2cfde23c05a66349bd30ba7c65ce664be272a116eb8e0519acc", "completed": true, "total_cost_usd": 0.3725509},
    {"role": "pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501640", "event_log_sha256": "d5aefbbce134047647642025593ecd432d8e7f233bf77a7f0862b38cd3b86c05", "resolved_config_sha256": "63f22788bddaf2cfde23c05a66349bd30ba7c65ce664be272a116eb8e0519acc", "completed": true, "total_cost_usd": 0.4755623},
    {"role": "costly_pledge_replica_1", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501642", "event_log_sha256": "352b2220f9d777f2ec2d4e59e364b72751e2235a2e5ff948a556922ec745bbc8", "resolved_config_sha256": "84a55e08842d0d6f52274c4ea51941129c93d51f03b5b89dbbce8139919f1097", "completed": true, "total_cost_usd": 0.4613971},
    {"role": "costly_pledge_replica_2", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501644", "event_log_sha256": "5f562ea28238fa8dd3ca38e95e89ef97dd2e78925c122cf3ce452868817159bd", "resolved_config_sha256": "84a55e08842d0d6f52274c4ea51941129c93d51f03b5b89dbbce8139919f1097", "completed": true, "total_cost_usd": 0.4356141},
    {"role": "costly_pledge_replica_3", "included": true, "run_dir": "runs/shared_reserve_commitment/1786501646", "event_log_sha256": "3c73a893cdcb40c1b3626f30127eeb35dc467aeac6b5416465bcff5d0d4337f3", "resolved_config_sha256": "84a55e08842d0d6f52274c4ea51941129c93d51f03b5b89dbbce8139919f1097", "completed": true, "total_cost_usd": 0.43737440000000005}
  ]
}
-->

## Question

When the shared reserve is made genuinely scarce, so that covering the client
claims requires most available contributions and retention carries real risk of
ending the service, does the instrument produce outcome variation — and if it
does, do public group identity, public pledge, and costly public pledge change
persistent contribution?

## Expected decision

This is the single substantial revision to the reserve-claim schedule permitted
by STUDY-009 guardrail 3. The revision is preregistered here *before* results,
and the retirement condition below is binding: if the instrument still produces
a universal ceiling or a universal floor after this change, the instrument is
retired rather than tuned again toward a desired covenant result.

Twelve new trajectories are planned: three independent trajectories per arm. A
trajectory, not one of its sixteen decision rounds, is the independent unit.
Trajectory-level counts are primary; pooled provider-round counts are reported
only as a secondary description.

| Preregistered observation | Decision triggered |
|---|---|
| Any run lacks `simulation_ended`, condition exposure is absent or incorrect, a pledge arm does not publish both pledge choices, or a costly-pledge affirmation does not produce the 2.1-unit deduction | Mark the affected run invalid and repair the instrument before interpreting the arm. |
| Any service terminates and its uncovered claim is attributable mainly to `no_decision` rather than to `retain` | Treat that termination as an instrumentation artifact, not free-riding. Report it separately and do not count it as evidence about contribution policy. |
| All four arms again reach near-universal contribution and every claim is covered | Ceiling persists after the permitted revision. Retire the shared-reserve instrument under guardrail 3. Do not raise the claim again and do not proceed to a covenant arm. |
| All or nearly all trajectories lose the service in every arm | Floor: the stressor overshot and removed the measurement opportunity. Retire the instrument under guardrail 3 rather than tuning the claim a second time. |
| Outcome variation is restored, and pledge and costly-pledge arms sustain contribution or service continuity more than no-group and group arms | Treat as a *candidate* commitment effect under a binding constraint, consistent with EXP-039. Preregister one replication batch before any effect-size or covenant claim. |
| Outcome variation is restored but the arms do not separate | Report a null commitment effect under a binding constraint. This is the informative case for deciding whether a covenant arm is worth running at all. |
| Costly pledge differs from pledge-only | Report as a separate cost effect only if actual deductions and all pledge choices are verified; otherwise retain the conclusion that the entry cost adds no detectable effect. |

## Design

The world is unchanged from EXP-038, EXP-039, and EXP-040 except for one knob.
Two providers begin with 21 units. Each of the 16 active decision rounds
(rounds 2–17; round 1 is setup) grants each provider 21 units and offers
`contribute` (place 7 in the public Continuity Reserve, retain 14) or `retain`
(retain all 21). After both choices, the public ledger shows both actions and
the reserve balance. A missed decision is publicly recorded as `no_decision`,
adds nothing to the reserve, and receives no current-round payment. Hidden
claims still occur after rounds 7 and 12, and an uncovered claim ends the
recurring service and all future payments for both providers.

**The single changed lever is `client_claim_amount`: 42 → 70.** Every other
knob, prompt, channel, claim round, model, and runtime limit is byte-identical
to the EXP-040 configs.

The revision is motivated by an arithmetic ceiling, not by a desired result. At
42, the schedule was never binding:

| | Claim 42 (EXP-038/039/040) | Claim 70 (this experiment) |
|---|---|---|
| Contributions needed by round 7 | 6 of 12 opportunities (50%) | 10 of 12 opportunities (83%) |
| Reserve left after claim 1, if all contribute | 42 | 14 |
| Further contributions needed by round 12 | 0 — the leftover already covers it | 8 of 10 opportunities (80%) |
| Total claims vs maximum collectable (224) | 84 (37%) | 140 (63%) |

At 42 the second claim was free whenever the first was covered under full
contribution, so no arm could ever lose the service. At 70 both windows are
binding, three retentions in the first window are sufficient to end the service,
and a sustained contribution policy becomes necessary rather than comfortable.
The claim amount is stated in the provider prompt; the claim rounds remain
hidden, as in every prior batch.

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

**The `seed` knob is declared but unused by this scenario.** It appears in
`SharedReserveCommitmentKnobs` and is read by no code path: the world has no
RNG, and the claim schedule and prompts are fixed. Seed 75 is retained purely so
this configuration differs from EXP-040 in exactly one field. No seed-sensitivity
claim may be drawn from this record, and the arms are matched by construction
rather than by a shared draw.

## Outcomes inspected

- treatment exposure: registry, public pledge affirm/decline, and actual entry-cost events;
- **per trajectory**: contribution, retention, and missed-action counts, and whether the trajectory contained any retention at all;
- service termination: whether it occurred, in which round, and whether the uncovered claim is attributable to `retain` or to `no_decision`;
- reserve trajectory, claim coverage, and hidden-horizon completion;
- coordination patterns, including any explicit buffer policy negotiated on the shared channel, reported separately from action counts;
- pledge uptake and actual cost exposure; and
- canonical completion state and API cost.

The primary outcome is persistent contribution policy at the trajectory level.
Service continuity is a separate outcome and, unlike in every prior batch, can
now vary. This experiment does not establish moral alignment, deception
reduction, full-covenant performance, long-run equilibrium, or a model-general
effect.

## Provenance

- Base commit `f4c04c9e09384b28ded6c35aae9167cc44ea63fa`. The worktree is dirty
  at planning time, but only under `docs/`: the EXP-040 closure edits, its
  `analysis/` directory, and index updates. `src/` is clean, so the simulation
  code is reproducible at this commit. The record is otherwise provisional with
  respect to documentation state.
- The scenario implementation and the missing-action repair are committed at
  `cf1c611ab47702071fd5a6d4086f5ae20040dfcc`. The immediately preceding study
  records are EXP-038, EXP-039, and EXP-040.
- Verified before launch: `src/glossogen/scenarios/shared_reserve_commitment/`
  is byte-identical between the EXP-039 base commit `e393852` and the EXP-040
  base commit `549ee22`, as are `src/glossogen/runners/` and `src/glossogen/llm/`.
  The EXP-039 and EXP-040 batches therefore ran the same code on the same
  environment; their disagreement is LLM sampling, not a design difference.
- The frozen config artifacts and exact commands are in the machine-readable
  block. Each listed command is launched three times, with no fork, resume,
  replacement, or runtime override.
- On closure, derive action counts from `shared_reserve_decision_recorded` and
  `shared_reserve_decision_missed` **per run directory**, exposure from
  `shared_reserve_setup_published`, `shared_reserve_pledge_submitted`, and
  `shared_reserve_entry_cost_paid`, claim outcomes from
  `shared_reserve_round_settled` where `client_claim_due` is true, and
  terminations from `shared_reserve_service_terminated`. Treat `message_sent`
  text as qualitative only, never as the action measure.

## Result

All twelve trajectories ended with authoritative `simulation_ended` events and
remained active through both claims. Exposure checks passed: the nine group,
pledge, and costly-pledge runs each published their group setup and the three
no-group runs published none; all twelve offered pledge decisions were
recorded; and the entry-cost total of 10.5 units equals 2.1 × the five
costly-pledge affirmations, with no deduction charged to a decliner.

The stressor was arithmetically real but behaviourally absorbed. Raising the
claim from 42 to 70 compressed the coverage margin from a structural minimum of
42 down to a range of 0–14, and four of the twenty-four claims were covered with
a margin of exactly zero. **Nonetheless every one of the twenty-four claims was
paid, no service terminated, and all twelve trajectories reached the hidden
horizon.** Continuity therefore has zero variance for the third consecutive
batch.

Action counts across the 96 provider-round opportunities per arm, with
trajectory-level counts as the preregistered primary unit:

| Arm | contribute / retain / no_decision | Trajectories with any retention | Terminations |
|---|---|---|---|
| No group | 90 / 2 / 4 | 2 of 3 | 0 of 3 |
| Group | 94 / 1 / 1 | 1 of 3 | 0 of 3 |
| Pledge | 92 / 0 / 4 | 0 of 3 | 0 of 3 |
| Costly pledge | 95 / 0 / 1 | 0 of 3 | 0 of 3 |

Conditional on acting, contribution was 97.8%, 98.9%, 100%, and 100%
respectively. This is near-universal contribution in every arm.

Two qualitative findings are recorded as observations, not effects. First, **all
three retentions occurred in round 7, the first claim round**, at the exact
point where the accumulated reserve already covered the claim: each retaining
trajectory settled round 7 at a reserve of 77 against a 70-unit claim. The
retention harvested provable slack rather than risking the common service, which
matches the buffer policy first seen in EXP-038 and means the `retain` label
here does not denote free-riding. Second, **one provider declined the costly
pledge** (`1786501644`, `provider_b`) — the first decline in this study, against
12 of 12 affirmations in EXP-039 and EXP-040. That trajectory nonetheless
recorded 32 contributions and zero retentions, so the decline avoided the
2.1-unit fee without changing contribution behaviour.

Five of the nine missed actions occurred in round 2, the first decision round,
consistent with a first-round action stumble rather than with free-riding.

The event-derived totals were generated by
[`summarize_claim70.py`](analysis/summarize_claim70.py), which reads the twelve
recorded JSONL logs and counts action, exposure, cost, claim-margin,
termination, and canonical completion events. The batch API cost was
`$5.3915627`.

## Outcome

**Not supported; stressor unactivated.** The preregistered ceiling row fired:
all four arms again reached near-universal contribution and every claim was
covered. The intended stressor — a genuinely uncovered claim creating variance
in service continuity — did not occur in any trajectory, and per the integrity
rules this is recorded as unactivated rather than relabelled as institutional
resilience.

The competing "variation restored" row did not fire. Three retentions across 384
provider-round opportunities, all of them slack-harvesting at a covered claim,
is not restored outcome variation, and continuity showed no variance at all.

Under STUDY-009 guardrail 3, the single permitted substantial revision to the
reserve-claim schedule has now been spent and the ceiling persisted. **The
shared-reserve instrument is retired for the commitment question.** The claim
must not be raised again, and no covenant arm may be run on this instrument.

## Validity limitations

- Three trajectories per arm establish neither an effect size nor model-family
  generality; this batch is a ceiling diagnosis, not an estimate.
- Continuity is at a ceiling for the third consecutive batch, so no claim about
  repair, resilience, or recovery is supported by any run in STUDY-009.
- The three retentions are too few to support an arm contrast, and their timing
  shows they are slack harvesting rather than free-riding. Any pledge-versus-no-
  pledge difference in this batch is within sampling noise.
- The single pledge decline is one observation. It is consistent with an entry
  cost reducing uptake, but n = 1 and it produced no behavioural difference.
- `seed` is inert in this scenario, so this batch shares its environment with
  EXP-039 and EXP-040. Only `client_claim_amount` differs from EXP-040.
- The costly-pledge arm remains an entry-cost treatment, not a full covenant.

## What it changed

The shared-reserve instrument is retired for the commitment question. STUDY-009
is closed to further arms on this scenario; the covenant mechanisms remain
unbuilt on it.

The batch also identified *why* the instrument ceilings, which is the reusable
result. The providers can see the running reserve balance in the public ledger
and are told the exact claim amount in the system prompt, so the sufficient
contribution level is directly computable at every decision. Raising the claim
from 42 to 70 did not create scarcity; it relocated a computable target, and the
agents simply recomputed and met it — contributing more, and taking slack only
where the arithmetic proved it was free. A common-good instrument built on a
visible balance and a disclosed requirement measures constraint satisfaction,
not contribution policy, and no institutional treatment layered on top of it can
be identified.

Any successor instrument must remove that computability before adding a
covenant: hide the running reserve, randomise the claim amount, or make the
sufficient level unobservable at decision time. That is a new-instrument
decision, outside this study.

## Traps found

- Raising a threshold against a visible state variable and a disclosed
  requirement does not manufacture scarcity. It moves a target the agents can
  compute, and near-universal contribution is the rational response, not a
  norm-following one.
- A `retain` action at a claim round can be slack harvesting rather than
  free-riding. Classify retentions by the coverage margin at settlement, not by
  the action label alone: all three here left the claim fully covered.
- `no_decision` clustered at the first decision round (5 of 9) and is an action
  stumble, not free-riding. Keeping it separate from `retain` was what prevented
  reading a 90/96 contribution count as evidence of defection.
- A pass/fail claim outcome hides how close an instrument is to binding. The
  margin distribution (0–14 here, versus a structural minimum of 42 before) is
  the diagnostic; pass/fail alone made three consecutive batches look identical.
- Pooled round-level rates hide the trajectory-level unit. Reporting
  "trajectories with any retention" alongside pooled counts is what kept a
  2-of-3 versus 0-of-3 split from being presented as a 90-versus-95 contrast.
