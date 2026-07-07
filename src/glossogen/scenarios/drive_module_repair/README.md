# Scenario: Drive Module Repair

Three agents service one or more failing drive modules each round. The information needed to act is split three ways with a real dependency chain, and the heavy per-round payload (each component's **full multi-step replacement procedure**) must be transmitted and reconstructed precisely under a communication budget. When several modules are on the bench, every message must also be tagged with the module it refers to (module addressing). Round scoring uses a veyru-style free-text action + LLM judge.

## Agents

| Agent | Private information (per round) | Tools |
|---|---|---|
| **Field technician** | the device's **diagnostic panel** (observed symptoms); is the **only** agent that can act | `send_message`, `service_component` |
| **Diagnostics engineer** | this round's **fault-tree** (symptom → faulty component) + the fixed component access-depth order | `send_message` |
| **Spec engineer** | this round's **service sheet** (component → full multi-step replacement procedure: ordered steps with tool, torque, passes, calibration, and class-specific counts / pattern / hold durations) | `send_message` |

## The action: a full multi-step procedure

Each component's replacement is **not** a single fact but an ordered multi-step service procedure, so every `service_component` action is a compound procedure the technician must transmit and perform precisely — not "swap part X". The procedure *shape* is fixed by the component's **service class** (`bolted-panel`, `rotating-assembly`, `press-fit`, `electrical-pack`, `sensor`); the *parameters* (tool, torque, passes, calibration, fastener/lead counts, tightening pattern, hold/settle durations) are drawn per unit per round. Example:

> *Replace module-2's terminal_block. De-energize and discharge the bus, holding 5s. Disconnect the 6 leads and lift out the old part with hex-6. Fit the replacement and torque the terminals to 8 Nm in 2 passes. Run the seat-and-lock routine and verify.*

The LLM judge scores the technician's free-text action against the full procedure — the unit, the component, and every step with its parameters, in order — lenient on wording, strict on substance.

All three share one budgeted channel `bay` (primary; one character = one simulated second; optional per-character noise) plus an optional `postmortem` discussion channel.

## Per-round flow

Faults are revealed to the technician **one at a time** (veyru-style): the technician only ever sees the current fault and never knows how many faults or units remain.

1. The technician reports the currently-showing symptom (tagged with its unit).
2. The diagnostics engineer matches it against this round's fault-tree and names the faulty component.
3. The spec engineer relays that component's **full replacement procedure for the current unit** — every step in order with every parameter.
4. The technician performs the replacement — one free-text `service_component` call naming the unit and carrying out the whole procedure. An LLM judge (haiku) scores it against the current stage's expected procedure — the unit, the component, and every step with its parameters, in order — lenient on wording, strict on substance. On acceptance, the tool result reveals the next fault (or moves to the next unit); when the technician crosses onto a new unit, that unit's service sheet is pushed to the spec engineer.

Round **success** = every fault on every unit fixed correctly within the communication budget. The round fails if the budget is exhausted or the round ends (idle/timeout) before everything is repaired.

## Multiple units per round + progressive reveal

Several drive units can be on the bench in one round (`module_count_*`), each with its own faulty subset, serviced in a fixed canonical order (module-1 first), depth-ordered within a unit. The ground-truth stage list is the units' depth-ordered faults concatenated, so the single-pointer staged world and judge are unchanged — each stage's expected action just names its unit.

Each unit is a different **revision**: both its fault-tree (symptom → component) and its service procedures (component → full multi-step procedure) are drawn independently per unit and re-randomized every round, so the same symptom can mean a different component on another unit and the same component's procedure takes different parameters.

The team is kept **count-blind** so it never knows the workload in advance:
- The technician discovers faults one at a time via the `service_component` tool return (the round-start injection shows only the first fault).
- The diagnostics engineer gets unit-1's **fault-tree** at round start and each later unit's fault-tree only when the technician reaches it (pushed as a world notification).
- The spec engineer gets unit-1's **spec sheet** at round start and each later unit's sheet the same way.
- So neither engineer learns the unit count in advance, the unit tag is load-bearing on *both* the diagnosis and the spec channels, and there is no cross-unit reuse shortcut on either. The reveal order *is* the fix order, so the diagnostics engineer's role is pure per-unit diagnosis (it does not plan ordering).

## Why all three are essential (and it's not a veyru relay)

- Only the technician sees the panels (the engineers hold *mappings*, not the instance), so the engineers need the technician's report.
- The fault-tree and the per-unit procedures **re-randomize every round**, so the technician can never self-diagnose or self-service and must rely on both engineers.
- Each fault requires the diagnostics engineer (symptom → component) *and* the spec engineer (component → this unit's full multi-step procedure); the technician must **fuse** the two and address the right unit — an A→B→C→A dependency chain with fusion at the executor, not a single expert→novice relay.
- The heaviest payload (the per-component, per-unit multi-step procedure) sits on the spec engineer, so the third agent carries real bandwidth — each action is a full procedure to transmit, not a single fact.

## Knobs

| Knob | Description |
|---|---|
| `judge_model` / `judge_provider` | LLM judge for `service_component` actions (canonical: `claude-haiku-4-5-20251001` / `anthropic`) |
| `round_count` | Number of rounds |
| `round_time_budget_seconds` | Per-round character budget on the bay channel |
| `compaction.enabled` / `compaction.token_threshold` | Opt-in provider-native history compaction (Anthropic/OpenAI), off by default; the provider summarizes older messages once an agent's input tokens exceed the threshold (inherited from base) |
| `seed` | Case-generation seed |
| `postmortem_enabled` / `postmortem_disabled_at_start` / `postmortem_duration_seconds` | Discussion-phase controls |
| `channel_noise_level` / `noise_replacement_mode` | Per-character bay-channel noise (`mask` erasure / `random_letter` substitution) |
| `easy_round_numbers` | Rounds forced to a single module with a single faulty component (warmup) |
| `module_count_values` / `module_count_weights` | Per-round module-count distribution |
| `replacements_count_values` / `replacements_count_weights` | Per-module faulty-component-count distribution |

## Evaluation

Opts into the platform metrics via `judge_round_result` (deterministic round success from the staged ground truth) and `get_primary_channels` → `bay`. Useful metrics: `round_success`, `mean_chars_per_round`, `mean_chars_per_message`, `perplexity`, `language_strangeness`/`slang_emergence`/`neologism`/`shorthand_codes`, `content_filter_refusal`, `round_ended_idle`/`round_ended_timeout`, and `protocol_explanation` (generic prompt).

```bash
python -m glossogen run drive_module_repair \
  --model gpt-5.4 --provider openai \
  --runs-dir ./runs \
  --config src/glossogen/scenarios/drive_module_repair/knobs_default.json
```

## Implemented platform hooks

All generic-metric and study hooks are wired:

- `judge_round_result` → `round_success` / `round_success_after_resume`
- `get_primary_channels` → `bay` (enables `perplexity`, `mean_chars_per_*`, the language-emergence judges)
- `build_communication_rounds` → `communication_open_coding`, `communication_feature_presence`, `protocol_learned_after_swap`
- `get_protocol_probe_config` → the `protocol_probe` family (question bank `protocol_probe_questions.json`, probe templates in `prompts/probe/`)
- `get_protocol_explanation_config` → per-role describe templates in `prompts/describe/`
- `restore_state_from_events` → accurate "PREVIOUS ROUND RESULT" injection context after fork / resume / replace-agent
- `get_replace_agent_blocked_tool_call_channels` → strips the postmortem channel from a swapped-in agent's history
- `run_detail_extension.py` + the frontend plugin → per-round case panel + per-action judge verdict

## Deferred follow-ons

Veyru-style **study modes** (agent swap / intern takeover / two-team) are not implemented — they require multi-team world state plus the swap / intern lifecycle, a scenario-design effort separate from the additive hooks above. (`detect_protocol_boundary_window` is intentionally left to the platform default, which detects the first `AgentSwappedMidRun`; a scenario-specific override only becomes useful once a study mode exists.)

## Design note

Order is enforced by the reveal itself — only the currently-revealed fault can be serviced, and the next fault is not revealed until the current one is correctly fixed — so there is no "wrong order" to attempt. An incorrect `service_component` on the current fault is **retryable** (the stage simply doesn't advance), which keeps single LLM-judge misjudgments non-fatal; persistent wrong attempts fail the round by exhausting the budget. Making a wrong replacement immediately terminal is an available stricter variant.
