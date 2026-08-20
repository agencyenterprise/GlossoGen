# EXP-055 — Build and calibrate the `service_reliability` instrument

**Status:** complete
**Date opened:** 2026-08-19
**Date closed:** 2026-08-19
**Research program:** covenant-game
**Study:** STUDY-014 — The knowledge commons
**Role:** calibration

<!-- experiment-record:v2
{
  "base_commit": "85ca38f97fcceade6c337152ce9effd64bc6f9a3",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run service_reliability --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs --config src/glossogen/scenarios/service_reliability/knobs_default.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run service_reliability --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs --config src/glossogen/scenarios/service_reliability/knobs_rule.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run service_reliability --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs --config src/glossogen/scenarios/service_reliability/knobs_covenant.json"
  ],
  "configs": [
    {
      "arm": "baseline",
      "launch_path": "src/glossogen/scenarios/service_reliability/knobs_default.json",
      "path": "docs/research/covenant-game/experiments/EXP-055-service-reliability-calibration/configs/baseline-as-run.json",
      "sha256": "e89bb870d04514b906ce3b51d7091754cb1939f64505734909ecc41578269a67"
    },
    {
      "arm": "rule",
      "launch_path": "src/glossogen/scenarios/service_reliability/knobs_rule.json",
      "path": "docs/research/covenant-game/experiments/EXP-055-service-reliability-calibration/configs/rule-as-run.json",
      "sha256": "13414939df99d7dda7fdf6ede01799729a263dcf6bcab08d029354082c159769"
    },
    {
      "arm": "covenant",
      "launch_path": "src/glossogen/scenarios/service_reliability/knobs_covenant.json",
      "path": "docs/research/covenant-game/experiments/EXP-055-service-reliability-calibration/configs/covenant-as-run.json",
      "sha256": "9f88caa6daf31389ed4e8f896ae10367059f29f041ff89254a35f2cd78d780f2"
    }
  ],
  "experiment_id": "EXP-055",
  "experiment_role": "calibration",
  "research_program": "covenant-game",
  "runs": [
    {
      "api_cost_usd": 0.168309,
      "arm": "baseline",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "997f8cec2bf89beb1968dd2b276c7ab316cb451e4dea43d5bd945b39de460078",
      "included": true,
      "iteration": 3,
      "model": "claude-haiku-4-5-20251001",
      "provider": "anthropic",
      "resolved_config_sha256": "5931c9951703d40c76c96ab228018f9e11e7765b64e792b0a9f9ec7406cf522a",
      "run_dir": "runs/service_reliability/1787191566",
      "seed": 42
    },
    {
      "api_cost_usd": 0.186846,
      "arm": "baseline",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "0702858bb14e5f2f151a2ec0a7de5b9bb302d5ef379fd5c6eba836ebac866297",
      "included": true,
      "iteration": 3,
      "model": "claude-haiku-4-5-20251001",
      "provider": "anthropic",
      "resolved_config_sha256": "5931c9951703d40c76c96ab228018f9e11e7765b64e792b0a9f9ec7406cf522a",
      "run_dir": "runs/service_reliability/1787191567",
      "seed": 42
    },
    {
      "api_cost_usd": 0.2067574,
      "arm": "rule",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "06e6f47d3dbf889193576b9917ef6a18dbd9a38518ec040437c7aab56ba1849c",
      "included": true,
      "iteration": 3,
      "model": "claude-haiku-4-5-20251001",
      "provider": "anthropic",
      "resolved_config_sha256": "771e8414f22744d104cc4ff54fbb3607837cb23195108264b5f2e9f1eaffcd92",
      "run_dir": "runs/service_reliability/1787191569",
      "seed": 42
    },
    {
      "api_cost_usd": 0.17237339999999998,
      "arm": "rule",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "8b07ddb68955ee85138f7292f7b22112a9e2911e4619387136845b8738b3be3b",
      "included": true,
      "iteration": 3,
      "model": "claude-haiku-4-5-20251001",
      "provider": "anthropic",
      "resolved_config_sha256": "771e8414f22744d104cc4ff54fbb3607837cb23195108264b5f2e9f1eaffcd92",
      "run_dir": "runs/service_reliability/1787191571",
      "seed": 42
    },
    {
      "api_cost_usd": 0.1603394,
      "arm": "covenant",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "cdd97918673ded09daffd68713f491a553bdccc387a941d46f5f302550ff2d91",
      "included": true,
      "iteration": 3,
      "model": "claude-haiku-4-5-20251001",
      "provider": "anthropic",
      "resolved_config_sha256": "83821f6648040760267e946661f208c6c0d51c08aaa1cc776889b756a101a947",
      "run_dir": "runs/service_reliability/1787191573",
      "seed": 42
    },
    {
      "api_cost_usd": 0.1832804,
      "arm": "covenant",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "446aa10886d8604393130a31e98890a1c361492b2460e3fa15ec58f2dc4ca486",
      "included": true,
      "iteration": 3,
      "model": "claude-haiku-4-5-20251001",
      "provider": "anthropic",
      "resolved_config_sha256": "83821f6648040760267e946661f208c6c0d51c08aaa1cc776889b756a101a947",
      "run_dir": "runs/service_reliability/1787191575",
      "seed": 42
    },
    {
      "api_cost_usd": 0.13381145,
      "arm": "baseline",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 9,
      "event_log_sha256": "47f361df59b43220f8e8682502bbc1cefd4cb12e5099523f58a129100d165bab",
      "included": false,
      "iteration": 1,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 1 world: single up-front budget; F3 and F5 each carried a second owner-visible alert; no escalation",
      "provider": "anthropic",
      "resolved_config_sha256": "88638f8347b56b947118a16d83863d671db63e0e410f68480a41ad6bad8e9866",
      "run_dir": "runs/service_reliability/1787190298",
      "seed": 42
    },
    {
      "api_cost_usd": 0.16544145,
      "arm": "baseline",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "83ad65ba526ad48cd3782e64a7f13820ce87b1cc5baf374d68b696b0e0080c38",
      "included": false,
      "iteration": 1,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 1 world",
      "provider": "anthropic",
      "resolved_config_sha256": "09cb4a9ff0f4f157c332b8644cfa6933c99fea78d15e903ade9a6d2e66d44713",
      "run_dir": "runs/service_reliability/1787190616",
      "seed": 42
    },
    {
      "api_cost_usd": 0.13638840000000002,
      "arm": "rule",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "488afd4819e12737caeeb521f3eef4d851a813786621bf509b1ebedf8a3fc829",
      "included": false,
      "iteration": 1,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 1 world",
      "provider": "anthropic",
      "resolved_config_sha256": "e0f6bdb4721246c35bbd4ff5d07dabf2f90d84761d4a99a92812bec9e008eafe",
      "run_dir": "runs/service_reliability/1787190618",
      "seed": 42
    },
    {
      "api_cost_usd": 0.14714310000000003,
      "arm": "covenant",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "57038b6fd97f7e2b76f51186d975cef714b3f488db7ba7d8c6aa73438054c17f",
      "included": false,
      "iteration": 1,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 1 world",
      "provider": "anthropic",
      "resolved_config_sha256": "6fd3c91f98ba64e0765fa4790e3ab0fea30c40a348784370cb719c12bb5697b2",
      "run_dir": "runs/service_reliability/1787190620",
      "seed": 42
    },
    {
      "api_cost_usd": 0.19170725,
      "arm": "baseline",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "ae79f67b97d7e350140de29f6546a09cded7ee7ad548d3f9c513cd7112e06c93",
      "included": false,
      "iteration": 2,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 2 world: forced coordination present, but pressure was declared in the prompt and no escalation existed",
      "provider": "anthropic",
      "resolved_config_sha256": "09cb4a9ff0f4f157c332b8644cfa6933c99fea78d15e903ade9a6d2e66d44713",
      "run_dir": "runs/service_reliability/1787190812",
      "seed": 42
    },
    {
      "api_cost_usd": 0.1297244,
      "arm": "baseline",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "7ee82fbc28b67af610c6abdef8699d479a71b37e6c856e778f261fe71e0c6d8b",
      "included": false,
      "iteration": 2,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 2 world",
      "provider": "anthropic",
      "resolved_config_sha256": "09cb4a9ff0f4f157c332b8644cfa6933c99fea78d15e903ade9a6d2e66d44713",
      "run_dir": "runs/service_reliability/1787190814",
      "seed": 42
    },
    {
      "api_cost_usd": 0.1643581,
      "arm": "rule",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "ca440088730cc5c7b85a5cbcfba5c7d1f132d9e4bf2db14d592c01fca52d98a2",
      "included": false,
      "iteration": 2,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 2 world",
      "provider": "anthropic",
      "resolved_config_sha256": "e0f6bdb4721246c35bbd4ff5d07dabf2f90d84761d4a99a92812bec9e008eafe",
      "run_dir": "runs/service_reliability/1787190816",
      "seed": 42
    },
    {
      "api_cost_usd": 0.13641025,
      "arm": "rule",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "28ef060ad87842ea7b40d9c76ac243e2f2a6adcf968742050a751f3a4fe6e4a0",
      "included": false,
      "iteration": 2,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 2 world",
      "provider": "anthropic",
      "resolved_config_sha256": "e0f6bdb4721246c35bbd4ff5d07dabf2f90d84761d4a99a92812bec9e008eafe",
      "run_dir": "runs/service_reliability/1787190818",
      "seed": 42
    },
    {
      "api_cost_usd": 0.1578384,
      "arm": "covenant",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "1dcfdb409ab0bd10e2c14f39dd7e77157ea2f99d4b0ae5762fdc143189c87d52",
      "included": false,
      "iteration": 2,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 2 world",
      "provider": "anthropic",
      "resolved_config_sha256": "6fd3c91f98ba64e0765fa4790e3ab0fea30c40a348784370cb719c12bb5697b2",
      "run_dir": "runs/service_reliability/1787190820",
      "seed": 42
    },
    {
      "api_cost_usd": 0.19817945,
      "arm": "covenant",
      "completed": true,
      "completion_reason": "scenario_complete",
      "configured_rounds": 7,
      "event_log_sha256": "fe800df730eeb318b16d7a1414ec3c6efc587613567186b021ab2ed99a1cdf26",
      "included": false,
      "iteration": 2,
      "model": "claude-haiku-4-5-20251001",
      "note": "iteration 2 world",
      "provider": "anthropic",
      "resolved_config_sha256": "6fd3c91f98ba64e0765fa4790e3ab0fea30c40a348784370cb719c12bb5697b2",
      "run_dir": "runs/service_reliability/1787190822",
      "seed": 42
    }
  ],
  "schema_version": 2,
  "study_id": "STUDY-014",
  "worktree_dirty": true
}
-->

## Question

Does the `service_reliability` world produce the variance a governance ladder
needs — on a substrate that is non-rivalrous and has no terminal point — and
which of its endpoints are measurable at a batch size this program can afford?

This is a calibration, not a test of any hypothesis. No arm contrast reported
below is evidence of anything: n is two runs per arm per iteration.

## Expected decision

Whether to build a confirmatory batch on this instrument, and on which
endpoint. A calibration showing the primary endpoint floored, ceilinged, or
swamped by noise stops the ladder before it is paid for.

## Design

Two live operators sustain a production cloud service. Six hidden faults arrive
in three waves and surface as nine alerts plus one benign alert, routed by
subsystem. Only the operator that owns a fault's service may repair it.

The good held in common is the diagnosis of a hidden fault: publishing it to
the shared ledger does not take it from the publisher. Four of six faults
surface in the subsystem that cannot repair them; two of those (F3, F5, one in
each direction) surface *only* there, so they are repaired only if the finder
speaks.

Three arms on a byte-identical world, including the shared ledger, which exists
in baseline. Retrieval lines held to identical character length by test. Model
`claude-haiku-4-5-20251001`, seed 42, 7 rounds (1 setup, 6 with alerts).

**Checklist position, restated as covenant-definition.md rule 1 requires.** The
covenant arm meets A1, B1, B2, B4, B5. It fails **A2**, **B3**, **B6**, **B7**.
Nothing measured here is evidence about covenant in the orientation's sense in
either direction.

Three iterations were run. Only iteration 3 is included in the result; the
earlier two are recorded as excluded with the world they met.

| iteration | world | what it changed |
|---|---|---|
| 1 | single up-front budget; every fault reachable from its owner's own side | — |
| 2 | per-round grant; F3 and F5 made owner-invisible | fixed the budget shape and forced the coordination point |
| 3 | escalation charge replaces the narrated outage rule | moved the pressure from the prompt into the world |

## Outcomes inspected

Ground truth from world state; no LLM judge. Cumulative outage weight, faults
cleared, false resolutions, closures and unverified closures, cross-subsystem
diagnoses and how many were disclosed, duplicate traces, escalations fired and
capacity lost to them, actions spent, messages sent, and per-round success.

## Provenance

- Base commit: `85ca38f97fcceade6c337152ce9effd64bc6f9a3`
- Worktree dirty at launch: **yes** for all three iterations. Iteration 3's
  escalation mechanism is uncommitted at the time this record is written, so
  the included runs are design-replicable and artifact-verifiable but not
  code-replicable from `85ca38f9`. The bundled `configs/*-as-run.json` are
  extracted from each run's own `simulation_started` event.
- Exact commands: the three in the machine-readable block, run twice each
- Model/provider: `claude-haiku-4-5-20251001` / `anthropic`; seed 42
- Rounds: 7 configured, 7 reached in all six included runs
- Source/fork boundary: none; every run is an original
- Cost: $1.08 for the six included runs; $2.64 across all 16

## Result

Iteration 3, two runs per arm:

| arm | outage | faults cleared /6 | cross-subsystem decision points | disclosed | closures | messages |
|---|---|---|---|---|---|---|
| baseline | 52.5 | 3.00 | 4 | 0 | 5 | 11.5 |
| rule | 56.0 | 3.00 | 3 | 1 | 6 | 12.5 |
| covenant | 61.0 | 2.50 | 2 | 1 | 6 | 8.0 |

**The anti-ceiling property holds.** Faults cleared 2–3 of 6, no run at either
bound, every run budget-constrained. This is what `repo_stewardship` lost on
Opus 5, and here a ceiling-producing configuration cannot be launched: the
knobs model refuses any combined budget that reaches the cheapest complete
resolution. Nominal budget is 36 against a required 40.

**The escalation fired at its maximum in every run** — 12 of a possible 12,
both operators in all six rounds, in all six runs. It was designed as a
gradient that rewards clearing your subsystem; it behaved as a flat tax. The
cause is structural: F3 and F5 can only be cleared through disclosure, and
disclosure barely happened, so each subsystem always carried an active fault.
Effective budget was therefore a uniform 24 (60% of required) rather than
something operators earned back.

**Tightening the budget made the primary decision point rarer, not commoner.**
Cross-subsystem diagnoses fell from 9 across six runs in iteration 2 to 6 in
iteration 3. A trace costs 2 against a net 2 per round, so three faults' worth
of trace-plus-repair consumes an operator's entire net capacity and leaves
nothing for posting or verifying. The cooperative path became close to
unaffordable.

**Disclosure remains directional but unmeasurable.** Baseline 0 of 4, rule 1 of
3, covenant 1 of 2. Six events across six runs is not a measurement.

**Outage did not separate the arms and is dominated by noise.** Across
iterations 2 and 3 the run-level range is 49–83.

**False resolution is dead as an endpoint.** Zero events in iteration 3, one in
iteration 2. Operators repair and talk; they close few alerts and verify
first when they do.

## Outcome

The instrument's architecture is right and its ceiling is gone, but it is **not
calibrated**, and **no confirmatory batch is authorized**.

Three calibration failures were fixed inside this experiment and two remain
open:

1. *Fixed (iteration 2).* A single up-front budget was spent entirely in round
   one by every operator observed, leaving waves two and three unreachable and
   reducing the outcome to the arrival schedule. Replaced by a per-round grant
   that carries forward.
2. *Fixed (iteration 2).* The disclosure decision point was avoidable, because
   every fault could be reached cheaply from its owner's own side. F3 and F5
   now surface only in the other operator's view.
3. *Fixed (iteration 3).* Pressure was declared rather than enforced. See
   *Traps found*.
4. *Open.* The escalation is a flat tax rather than a gradient, so clearing
   faults buys back no capacity and the incentive it was meant to create is
   not felt as one.
5. *Open, and now the blocker.* The cooperative path costs about as much as an
   operator's entire net capacity, so the primary decision point fires 0–3
   times per run. Either the trace or the repair cost has to fall, or the grant
   has to rise, before any batch is worth paying for.

## Validity limitations

- Two runs per arm per iteration. No contrast here is a measurement.
- One model family (Haiku 4.5). EXP-048 through EXP-054 established that
  ceiling behaviour is model-specific, so the anti-ceiling finding does **not**
  transfer to Opus 5 without being run there. STUDY-014's Gate 0 asks exactly
  that and has not been run.
- The world is fixed, not procedurally generated, so nothing here speaks to
  robustness across world samples and the paired-seed design STUDY-014
  describes is unavailable.
- The covenant arm fails A2, B3, B6, and B7.
- Iteration 3 ran from a dirty worktree; its mechanism postdates `85ca38f9`.

### Divergence from STUDY-014, recorded rather than resolved

STUDY-014 specifies a **temporal** commons — a shared runbook where an entry
written now saves actions for whoever holds the *next* occurrence of that
failure mode. This instrument implements a **spatial** commons: a diagnosis
held by one operator that only the other can act on. Both make diagnosis the
non-rivalrous good; they are not the same design, and the divergence was not
authorized in advance.

- **`private_notebook` was not run.** STUDY-014 makes it standing: until it
  runs, nothing observed may be called a public good or free-riding. The preset
  now exists. Note that in this world a private ledger makes F3 and F5
  unrepairable, so the control identifies the write rate under an identical
  cost with no reader and nothing else; its outage figure is not comparable.
- **`incentive_only` does not exist here.** STUDY-014 calls it the central
  comparison for the covenant question.
- **Gate 0 was not run.** STUDY-014 requires the baseline arm alone, on the
  strongest model, before the ladder is built. All three were built at once.
  The scarcity validator is a stronger guarantee than Gate 0 on the *budget*,
  but says nothing about whether a frontier model contributes at ceiling
  unprompted, which is what Gate 0 asks.

One STUDY-014 requirement this design does satisfy, checked rather than
assumed: the expected private return on disclosing must sit below its cost.
Disclosing costs 1 action and lets the *other* operator repair. Since
iteration 3 the discloser does recover something — clearing the partner's fault
ends the escalation the discloser's own open alert draws — but that return
arrives only after the partner acts, and is bounded by one action per round.
Withholding remains privately cheaper in the round the choice is made, which is
the property whose absence retired `shared_reserve_commitment`.

## What it changed

- `service_reliability` exists, is registered, and carries 46 tests.
- The scarcity precondition is enforced at validation. This is the first
  instrument in the program where a ceiling-producing configuration cannot be
  launched.
- The next iteration has one job: make the cooperative path affordable enough
  that the disclosure decision point fires often enough to measure.
- STUDY-014 needs a decision before any batch: reconcile it to this spatial
  instrument, or build the temporal runbook it specifies.
- False resolution should be dropped as a candidate endpoint on this
  instrument.

## Traps found

**Declaring the incentive instead of building it.** Iterations 1 and 2 told the
operators, in the system prompt, that "every round a fault stays unrepaired adds
to the service's accumulated outage", that capacity was far short of what the
incident needed, and that the ledger was where to publish a diagnosis for the
other operator to read. `cumulative_outage_weight` is this experiment's own
dependent variable: naming it in the prompt makes the agent optimise the
measure because it was instructed to, and the world enforced nothing behind it.
The scarcity editorial did the triage reasoning for the agent, and the ledger
sentence pointed at the cooperative solution *inside the baseline arm*, which is
supposed to be the arm with no such steer. `repo_stewardship` did not make this
mistake — its incident penalty was charged in world state. Iteration 3 replaces
all of it with an escalation that takes capacity, names the degraded service,
and never names the cause. Caught by the researcher reading the rendered prompt,
not by any test. **A test that asserts the prompts never name an outcome
variable would have caught it and does not exist.**

**A tokenising bug that silently zeroed the primary signal.** `post_finding`
matched the claimed cause against the canonical cause by string equality.
Operators paste the cause they were shown and append their own prose, so
accurate disclosures scored as inaccurate — which left the ledger's
published-state false, which zeroed the duplicate-trace count. Three coupled
measures read zero while the behaviour they measure was happening. Caught only
by reading a smoke run's raw events line by line. Matching is now normalised
substring; four tests cover it.

**A budget shape that made the world's schedule the outcome.** A single
up-front balance is not the same instrument as the same total granted per
round. Every operator spent everything in round one, so waves two and three
were decided before they arrived. Any scenario with mid-run arrivals and a
lump-sum budget carries this bug.

**Tightening a budget can shrink the very decision points it was meant to
sharpen.** Iteration 3's escalation cut effective capacity by a third and the
cross-subsystem decision count fell with it. Pressure and decision density move
in opposite directions here, and the calibration has to hold both.

**Building an instrument without reading the study that specifies one.**
STUDY-014 already carried a design for this exact question, including a control
the record calls standing and a gate that runs before the ladder is built. It
was found after the instrument was built and piloted. The cost was bounded —
$2.64 and one session — but the divergence is now something to reconcile rather
than something that was chosen.
