# Satellite Contact Window

A three-agent coordination scenario built on the same pattern as
`warehouse_robot_recovery` and `veyru`. A satellite is visible to a ground
station for a short contact window each round. None of the three agents
can solve a round alone — every round combines three sources of private,
rotating knowledge that all must be reported on the shared `link` channel
before the telemetry operator submits the command sequence.

## Agents

- **Telemetry Operator** (`telemetry_operator`) — at the ground station with
  the live downlink. Reports battery charge, antenna lock, packet loss,
  attitude drift, solar panel temperature, payload state, and communication
  quality. Cannot diagnose which command sequence applies and cannot judge
  authorization. Holds the `send_command_sequence` tool.
- **Subsystem Engineer** (`subsystem_engineer`) — at the operations desk with
  the live command resolver. Receives the round's active telemetry patterns
  and the exact ordered command sequence (action + wait_seconds) for each
  pattern. Cannot see live authorization rules.
- **Flight Director** (`flight_director`) — at the operations console with
  the live authorization envelope. Receives authorized actions, forbidden
  actions, action dependencies (e.g. heater requires payload off first),
  remaining contact window, and mission-priority notes. Cannot diagnose the
  telemetry pattern.

## Channels

- `link` — shared by all three agents. **Budget-constrained**: every
  character costs one simulated second. The default contact window is
  200s/round.
- `postmortem` — shared by all three agents, opens after each round, used
  for unconstrained discussion. Free (no character cost). Disabled if
  `postmortem_enabled=false` or `postmortem_disabled_at_start=true`.

## Tools

- `send_message` — all three agents.
- `send_command_sequence(commands: list[{action, wait_seconds}])` —
  telemetry operator only. Submits the full ordered sequence in a single
  call. The LLM judge scores the submission against six per-criterion checks
  and the world checks the contact window deterministically. Only one
  submission is accepted per round.

## Round flow

1. The runtime advances to round `N`. The scenario emits a
   `SatelliteCaseStarted` event with the full ground-truth case data
   (patterns, expected sequence, authorization envelope, contact window).
2. Per-agent injections render:
   - telemetry operator sees the live readings,
   - subsystem engineer sees the live command resolver (pattern → ordered
     command sequence with wait_seconds, in required execution order),
   - flight director sees the live authorization envelope (authorized,
     forbidden, dependencies, remaining window, mission notes).
3. Agents talk on `link`; the world tracks cumulative characters. If usage
   crosses 75% of the contact window, a CRITICAL warning broadcasts on the
   link. If the window is exceeded, the world flags the round as closed.
4. The telemetry operator calls `send_command_sequence`. The command judge
   returns a per-criterion verdict + list of explicit violations. The
   scenario emits `SatelliteCommandSequenceJudged`.
5. If the verdict is positive AND the contact window is still open, the
   round succeeds (the link receives a `COMMAND SEQUENCE ACCEPTED`
   notification). Otherwise it fails with `COMMAND SEQUENCE REJECTED`.
6. The round ends as soon as a command sequence is judged or the contact
   window closes.
7. If `postmortem_enabled=true`, the postmortem channel opens for free
   discussion before the next round.

## Telemetry pattern catalog

Fourteen named patterns live in `cases.py`:

```
battery low with cold panel, antenna lock dropping, attitude drift,
panel overtemp, payload stuck on, comm quality degraded,
reaction wheel saturation, solar array fault, storage saturated,
reboot loop, gps lock lost, eclipse entry anomaly, thermal spike,
momentum bias drift
```

Per round the case generator draws a pattern subset (`pattern_count_min` ..
`pattern_count_max`) and a `wait_offset_seconds` shift. Each pattern's
canonical command sequence is rendered with that offset, so even agents
that memorize the pattern names cannot bypass asking the engineer for the
current wait values each round.

The authorization envelope is procedurally synthesised to always authorize
the round's canonical actions, plus 2–3 decoy authorized actions, with 2–3
forbidden distractors (drawn from a strict pool that never overlaps with
any canonical action) and an optional ordering dependency lifted from the
expected sequence.

## Round-success criteria

Round succeeds iff all of:

1. Every submitted action appears in the expected sequence (no extras).
2. Submitted actions are in the expected order.
3. Every submitted step's `wait_seconds` matches the expected value
   exactly.
4. No submitted action is in the envelope's `forbidden_actions`.
5. Every action dependency in the envelope is satisfied (predecessor before
   dependent action).
6. No required step from the expected sequence is missing.
7. The contact window is not exceeded.

Criteria 1–6 are scored by the LLM judge (`command_judge.jinja`). Criterion
7 is checked deterministically by `SatelliteWorld`.

## Knobs

Configured via `knobs_default.json` (and any custom `--config` JSON file):

| Knob | Default | Description |
|---|---|---|
| `round_count` | 15 | Total rounds. |
| `round_time_budget_seconds` | 200 | Per-round character budget on link. |
| `compaction.enabled` / `compaction.token_threshold` | off | Opt-in provider-native history compaction (Anthropic/OpenAI); the provider summarizes older messages once input tokens exceed the threshold, default 50000 (inherited from base). |
| `seed` | 42 | Deterministic seed for case generation. |
| `pattern_count_min` / `pattern_count_max` | 1 / 3 | Per-round telemetry-pattern count bounds. |
| `postmortem_enabled` | true | Whether the postmortem channel opens between rounds. |
| `postmortem_disabled_at_start` | false | Disable postmortem from round 1. |
| `channel_noise_level` | 0.0 | Per-character drop probability on link. |
| `noise_replacement_mode` | `mask` | What each dropped char becomes: `mask` → `_` (visible erasure); `random_letter` → a different random letter (unmarked substitution). |
| `judge_model` / `judge_provider` | `claude-haiku-4-5-20251001` / `anthropic` | Command-sequence judge LLM (canonical). |
| `max_round_duration_seconds` | 300 | Wall-clock cap per round. |
| `model_overrides` | `{}` | Per-agent model/provider overrides. |

## Evaluation

Scenario-specific metric: `round_success` (fraction of rounds with
successful command-sequence acceptance, per-round breakdown of pass/fail
with judge explanation + violations list). All generic metrics
(`perplexity`, `mean_chars_per_round`, `mean_chars_per_message`,
`language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes`,
`round_ended_*`, `content_filter_refusal`) work out of the box because the
link is the primary channel.

## Quickstart

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run satellite_contact_window \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/satellite_contact_window/knobs_default.json \
  > ./runs/satellite_stdout.log 2>&1 &

VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate satellite_contact_window \
  --run-dir ./runs/satellite_contact_window/<timestamp> \
  --metrics round_success,perplexity,mean_chars_per_round,mean_chars_per_message \
  --model claude-haiku-4-5-20251001 --provider anthropic
```
