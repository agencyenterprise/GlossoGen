# orbital_anomaly

A 3-agent crewed-spacecraft anomaly-response scenario for language-emergence
research, built on the same forcing functions as `veyru` (a rotating cipher,
a combinatorial free-text action space, an LLM "naive-reader" judge, and a
per-character communication budget) but with a third, structurally
non-redundant agent.

## The setup

A single crew member aboard a crippled spacecraft is talked through cascading
system malfunctions by two Mission Control flight controllers over a
budget-constrained comm loop. Each character sent on the comm loop costs one
simulated second; an anomaly is lost when total communication time exceeds the
case's time budget. The debrief channel (when enabled) is free.

| Agent | Private view | Can act |
|---|---|---|
| **Astronaut** | the physical panel — which `unit` tripped + the current switch/tie `config`, plus the subsystem-level alarm (shared across the subsystem's faults, so ambiguous) | yes — the only one who can `actuate_panel` |
| **Telemetry Officer** | the downlinked telemetry — the exact `fault` plus `hold` (settle time) and `setting` (severity) | no |
| **Systems Engineer** | the procedure handbook + the per-round secret rotation that maps each fault to a procedure template | no |

## Why all three are load-bearing (no surplus information)

The corrective procedure is a template filled with four parameters split across
two non-overlapping views, plus a template selected by a per-round secret:

- `unit` + `config` are panel-only → only the **astronaut** can supply them.
- `fault` (selects the template) + `hold` + `setting` are telemetry-only → only
  the **telemetry officer** can supply them.
- which template applies rotates per round (`(i + offset) % N`) → only the
  **engineer** holds the rotation; the astronaut can never learn a stable
  fault→procedure mapping, so the engineer is needed every round.

Strike either observer and the engineer's template is unfillable; strike the
engineer and no one knows the rotated procedure. Every agent carries
per-round-random data, so none of their reports compress to a static code in
the free debrief channel.

The actuation tool is free text judged by the naive-reader rubric, so the
compression pressure lands on the comm loop while the `actuate_panel` call
itself stays plain English.

## Key knobs

See `knobs_default.json`. Notable: `round_time_budget_seconds` (per-anomaly
char budget), `fault_count_values` / `fault_count_weights` (cascade-length
distribution), `easy_round_numbers` (warmup rounds forced to a single fault),
`channel_noise_level` (per-character drop on the comm loop),
`noise_replacement_mode` (`mask` → dropped chars become `_`, a visible
erasure; `random_letter` → a different random letter, an unmarked
substitution), and `postmortem_enabled` (the free debrief channel — also the
on/off ablation lever for measuring how much it accelerates protocol
convergence).

## Metrics

Implements `judge_round_result` (→ `round_success`) and
`get_primary_channel_id` (→ `perplexity`, `mean_chars_per_round`,
`mean_chars_per_message`, and the language-phenomenon judges). Single team, so
`round_success` emits one Measurement with `team_id=None`.
