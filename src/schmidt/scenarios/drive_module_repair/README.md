# Scenario: Drive Module Repair

Three agents service one or more failing drive modules each round. The information needed to act is split three ways with a real dependency chain, and the heavy per-round payload (the per-component specs) must be transmitted and reconstructed precisely under a communication budget. When several modules are on the bench, every message must also be tagged with the module it refers to (module addressing). Round scoring uses a veyru-style free-text action + LLM judge.

## Agents

| Agent | Private information (per round) | Tools |
|---|---|---|
| **Field technician** | the device's **diagnostic panel** (observed symptoms); is the **only** agent that can act | `send_message`, `replace_component` |
| **Diagnostics engineer** | this round's **fault-tree** (symptom → faulty component) + the fixed component access-depth order | `send_message` |
| **Spec engineer** | this round's **service-spec table** (component → tool, torque, calibration) | `send_message` |

All three share one budgeted channel `bay` (primary; one character = one simulated second; optional per-character noise) plus an optional `postmortem` discussion channel.

## Per-round flow

1. The technician inspects the panel and reports the observed symptoms.
2. The diagnostics engineer matches the symptoms against this round's fault-tree, identifies the faulty components, and transmits them **in access-depth order** (outermost first — a unique correct order).
3. The spec engineer looks up the named components in this round's spec table and transmits each one's tool / torque / calibration.
4. The technician performs the replacements **in order** — working module by module (module-1 first), components within a module in access-depth order — one free-text `replace_component` call each, naming the module. An LLM judge (haiku) scores each action against the current stage's expected (module, component, tool, torque, calibration) — lenient on wording, strict on the five facts. Only the current required replacement is accepted, which hard-enforces the order.

Round **success** = every component on every module replaced correctly, in order, within the communication budget. The round fails if the budget is exhausted or the round ends (idle/timeout) before all modules are fully repaired.

## Multiple modules per round

Several drive modules can be on the bench in one round (`module_count_*`), each with its own faulty subset. The fault-tree and the service spec are **shared** across the round's modules (a component's spec is module-independent — so the spec engineer specs each *distinct* faulty component once and the team reuses it), but each module has its own fault set, so the protocol must tag every symptom, plan, and spec with the module it refers to. Modules are serviced in a fixed canonical order (module-1 first); the ground-truth stage list is simply the modules' depth-ordered replacements concatenated, so the single-pointer staged world and LLM judge are unchanged — each stage's expected action just names its module.

## Why all three are essential (and it's not a veyru relay)

- Only the technician sees the panel (the engineers hold *mappings*, not the instance), so the engineers need the technician's report.
- The fault-tree and the spec table **re-randomize every round**, so the technician can never self-diagnose or self-spec and must rely on both engineers.
- The spec engineer depends on the diagnostics engineer (specs are keyed to the chosen components), and the technician must **fuse** the ordered plan with the per-component specs — an A→B→C→A dependency chain with fusion at the executor, not a single expert→novice relay.
- The heaviest payload (the per-component tool/torque/calibration) sits on the spec engineer, so the third agent carries real bandwidth.

## Knobs

| Knob | Description |
|---|---|
| `judge_model` / `judge_provider` | LLM judge for `replace_component` actions (canonical: `claude-haiku-4-5-20251001` / `anthropic`) |
| `round_count` | Number of rounds |
| `round_time_budget_seconds` | Per-round character budget on the bay channel |
| `seed` | Case-generation seed |
| `postmortem_enabled` / `postmortem_disabled_at_start` / `postmortem_duration_seconds` | Discussion-phase controls |
| `channel_noise_level` / `noise_replacement_mode` | Per-character bay-channel noise (`mask` erasure / `random_letter` substitution) |
| `easy_round_numbers` | Rounds forced to a single module with a single faulty component (warmup) |
| `module_count_values` / `module_count_weights` | Per-round module-count distribution |
| `replacements_count_values` / `replacements_count_weights` | Per-module faulty-component-count distribution |

## Evaluation

Opts into the platform metrics via `judge_round_result` (deterministic round success from the staged ground truth) and `get_primary_channel_id` → `bay`. Useful metrics: `round_success`, `mean_chars_per_round`, `mean_chars_per_message`, `perplexity`, `language_strangeness`/`slang_emergence`/`neologism`/`shorthand_codes`, `content_filter_refusal`, `round_ended_idle`/`round_ended_timeout`, and `protocol_explanation` (generic prompt).

```bash
python -m schmidt run drive_module_repair \
  --model gpt-5.4 --provider openai \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/drive_module_repair/knobs_default.json
```

## Deferred follow-ons

Not implemented in v1 (all additive): the `protocol_probe` family (needs a bespoke 3-role question bank + probe/describe templates), `communication_open_coding`/`communication_feature_presence` (needs `build_communication_rounds`), a `run_detail_extension.py` + frontend plugin, and veyru-style study modes (swap / intern / two-team).

## Design note

An incorrect or out-of-order `replace_component` is **retryable** (the current required replacement is simply not advanced), which keeps single LLM-judge misjudgments non-fatal; the order is still hard-enforced (you cannot progress past a component until you correctly replace it), and persistent wrong attempts fail the round by exhausting the budget. Making a wrong replacement immediately terminal is an available stricter variant.
