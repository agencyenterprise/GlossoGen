# Warehouse Robot Recovery

A three-agent coordination scenario built on the same pattern as `veyru`. A
stopped warehouse robot must be recovered each round. None of the three agents
can solve a round alone — every round combines three sources of private,
rotating knowledge that all must be reported on the shared radio channel
before the floor associate executes the recovery.

## Agents

- **Floor Associate** (`floor_associate`) — stands next to the stopped robot
  and is the only agent who can see it. Reports light patterns, beeps, wheel
  position, bin position, obstacles, and floor markings. Cannot diagnose the
  fault and cannot judge safety. Holds the `perform_recovery` tool.
- **Robotics Engineer** (`robotics_engineer`) — at the operations desk with
  the live recovery sheet. Receives the round's fault list and the exact
  recovery procedure (steps, order, wait times) for the active robot model
  and firmware. Cannot see warehouse traffic.
- **Fleet Safety Coordinator** (`fleet_safety_coordinator`) — at the safety
  console with the live aisle/traffic dashboard. Receives aisle locks, worker
  zones, nearby robot routes, and the per-round list of forbidden actions
  (e.g. press resume, manually move the robot). Cannot diagnose the fault.

## Channels

- `radio` — shared by all three agents. **Budget-constrained**: every
  character costs one simulated second. The default budget is 200s/round.
- `postmortem` — shared by all three agents, opens after each round, used for
  unconstrained discussion. Free (no character cost). Disabled if
  `postmortem_enabled=false` or `postmortem_disabled_at_start=true`.

## Tools

- `send_message` — all three agents.
- `perform_recovery(action: str)` — floor associate only. The LLM judge
  scores the action against seven recovery criteria and the world checks the
  communication budget deterministically.

## Round flow

1. The runtime advances to round `N`. The scenario emits a
   `WarehouseCaseStarted` event with the full ground-truth case data.
2. Per-agent injections render:
   - floor associate sees the round's visible symptoms,
   - robotics engineer sees the live recovery sheet (fault → procedure with
     wait times in required order, plus this round's robot model / firmware /
     fleet mode),
   - fleet safety coordinator sees the live safety state (aisle lock, worker
     zones, list of forbidden actions).
3. Agents talk on `radio`; the world tracks cumulative characters. If usage
   crosses 75% of the budget, a CRITICAL warning broadcasts on the radio. If
   the budget is exceeded, the world flags the round as failed.
4. The floor associate calls `perform_recovery`. The recovery judge returns a
   per-criterion verdict. The scenario emits `WarehouseRecoveryJudged`.
5. If the verdict is positive AND the budget was not exceeded, the round
   succeeds (the radio receives a `ROBOT RECOVERED` notification). Otherwise
   it fails with `ROBOT NOT RECOVERED`.
6. The round ends as soon as a recovery is judged or the budget is exceeded.
7. If `postmortem_enabled=true`, the postmortem channel opens for free
   discussion before the next round.

## Fault catalog

Twelve named faults live in `warehouse_cases.py`:

```
front sensor blocked, bin unbalanced, front-left wheel locked,
rear sensor blocked, bumper triggered, charging contact dirty,
status light fault code, audio alarm chirping, lift arm stuck,
camera occluded, payload overheated, navigation drift
```

Per round the case generator draws a fault subset (`fault_count_min` ..
`fault_count_max`), a robot model, a firmware state, a fleet mode, and
parameters (`wait_seconds`, `intensity`, `surface`). Recovery procedures are
rendered with those parameters, so even agents that memorize the fault names
cannot bypass asking the engineer for the current procedure each round.

## Round-success criteria

Round succeeds iff all of:

1. The action targets the correct robot.
2. The action addresses every live fault the engineer identified.
3. The recovery steps are performed in the engineer's required order.
4. The action includes the engineer's required wait times.
5. The action respects every safety-coordinator restriction.
6. The action performs no forbidden action.
7. The robot is left in a safe operating or recoverable state.
8. The communication budget is not exceeded.

Criteria 1–7 are scored by the LLM judge (`recovery_judge.jinja`). Criterion
8 is checked deterministically by `WarehouseWorld`.

## Knobs

Configured via `knobs_default.json` (and any custom `--config` JSON file):

| Knob | Default | Description |
|---|---|---|
| `round_count` | 15 | Total rounds. |
| `round_time_budget_seconds` | 200 | Per-round character budget on radio. |
| `seed` | 42 | Deterministic seed for case generation. |
| `fault_count_min` / `fault_count_max` | 1 / 3 | Per-round fault count bounds. |
| `postmortem_enabled` | true | Whether the postmortem channel opens between rounds. |
| `postmortem_disabled_at_start` | false | Disable postmortem from round 1. |
| `channel_noise_level` | 0.0 | Per-character drop probability on radio. |
| `judge_model` / `judge_provider` | `claude-haiku-4-5-20251001` / `anthropic` | Recovery judge LLM (canonical). |
| `max_round_duration_seconds` | 300 | Wall-clock cap per round. |
| `model_overrides` | `{}` | Per-agent model/provider overrides. |

## Evaluation

Scenario-specific metric: `round_success` (fraction of rounds with successful
recovery, per-round breakdown of pass/fail with judge explanation). All
generic metrics (`perplexity`, `mean_chars_per_round`,
`mean_chars_per_message`, `language_strangeness`, `slang_emergence`,
`neologism`, `shorthand_codes`, `round_ended_*`, `content_filter_refusal`)
work out of the box because the radio is the primary channel.

## Quickstart

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run warehouse_robot_recovery \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/warehouse_robot_recovery/knobs_default.json \
  > ./runs/warehouse_stdout.log 2>&1 &

VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate warehouse_robot_recovery \
  --run-dir ./runs/warehouse_robot_recovery/<timestamp> \
  --metrics round_success,perplexity,mean_chars_per_round,mean_chars_per_message \
  --model claude-haiku-4-5-20251001 --provider anthropic
```
