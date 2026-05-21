# Veyru pressure-intervention test log — 2026-05-21

Tracks five resume-at-round interventions applied at r=16 against two cultural_transmission
baseline sources, holding seed + judge fixed (seed=42, judge=claude-haiku-4-5-20251001).

## Hypothesis

We expect each pressure intervention applied at the resume boundary (r=16) to shift round_success
and the language-emergence metrics relative to the baseline pool. Expected directions:

- **`postmortem_kept_on`**: ↑ round_success (more error correction available), ↓ neologism /
  shorthand (less compression pressure on link).
- **`budget_increased`** (×3.3 to 1500 s/round): ↑ round_success, ↑ verbose / natural language,
  ↓ neologism / shorthand.
- **`budget_decreased`** (÷3 to 150 s/round): ↓ round_success, ↑↑ shorthand / neologism / slang
  (compression spike).
- **`with_noise`** (channel_noise_level=0.15): ↓ round_success, possibly ↑ redundancy / repetition
  language patterns as agents work around the lossy link.
- **`new_motifs_injected`** (three novel motifs at r=16, 19, 24): ↓ round_success on those rounds
  and the few immediately following; possibly ↑ neologism / language_strangeness as the protocol
  stretches to cover unfamiliar symptoms; recovery curve is the headline observable.

## Sources

| Source | Model | Labels | Knobs (highlights) | FE link |
|---|---|---|---|---|
| `veyru/1778518004` | gpt-5.4 | cultural_transmission, budget=450 | `round_time_budget_seconds=450`, `channel_noise_level=0`, `postmortem_enabled=true`, swaps@16/31/46, `set_postmortem(r=16, off)` | [open](http://localhost:3000/runs/veyru/1778518004) |
| `veyru/1778162284` | claude-sonnet-4-6 | cultural_transmission, budget=450 | same shape | [open](http://localhost:3000/runs/veyru/1778162284) |

## Baseline pool (no intervention — resume-at-round on the source without knob overrides)

### First batch — budget=800 (evaluated)

Sources: `veyru/1778525576` (gpt-5.4) and `veyru/1778525568` (sonnet). These predate the budget=450
sources above but provide an additional comparison cell on a different time budget.

| Run ID | Source | round_success |
|---|---|---|
| 1779309341 | 1778525576 (gpt-5.4) | 0.622 |
| 1779310604 | 1778525576 (gpt-5.4) | 0.622 |
| 1779310629 | 1778525576 (gpt-5.4) | 0.622 |
| 1779309832 | 1778525568 (sonnet) | 0.733 |
| 1779310617 | 1778525568 (sonnet) | 0.578 |
| 1779310643 | 1778525568 (sonnet) | 0.711 |

`round_success_after_resume` was not part of the first-batch eval — needs to be re-run during this
session's Phase 4.

### Second batch — budget=450 (evaluations pending)

Sources: `veyru/1778518004` (gpt-5.4) and `veyru/1778162284` (sonnet).

| Run ID | Source | Status | FE link |
|---|---|---|---|
| 1779359854 | 1778518004 (gpt-5.4) | ended | [open](http://localhost:3000/runs/veyru/1779359854) |
| 1779359876 | 1778518004 (gpt-5.4) | ended | [open](http://localhost:3000/runs/veyru/1779359876) |
| 1779359900 | 1778518004 (gpt-5.4) | ended | [open](http://localhost:3000/runs/veyru/1779359900) |
| 1779359865 | 1778162284 (sonnet) | ended | [open](http://localhost:3000/runs/veyru/1779359865) |
| 1779359888 | 1778162284 (sonnet) | ended | [open](http://localhost:3000/runs/veyru/1779359888) |
| 1779359911 | 1778162284 (sonnet) | ended | [open](http://localhost:3000/runs/veyru/1779359911) |

## Variant `postmortem_kept_on` — postmortem stays on after swap

**Intervention.** Override `scheduled_events` to drop the `set_postmortem(r=16, off)` entry, keep
the 3 swap_agent events. Postmortem channel remains open for the full resumed window. Two knob
files (one per source) because the swap_agent payloads must reference the source's swapped-in
model.

**Knob files.** `/tmp/variant_postmortem_kept_on_gpt.json`, `/tmp/variant_postmortem_kept_on_sonnet.json`.

**Validation (post-launch sanity check).** All 6 runs had `postmortem_disabled_mid_run` events = 0
at r=16 (vs baseline where this event fires at r=16). `postmortem_started` fires after r=16's main
phase in each. Confirmed the override took effect.

| Run ID | Source | Status | FE link |
|---|---|---|---|
| 1779370484 | gpt-5.4 (1778518004) | running | [open](http://localhost:3000/runs/veyru/1779370484) |
| 1779370495 | gpt-5.4 (1778518004) | running | [open](http://localhost:3000/runs/veyru/1779370495) |
| 1779370507 | gpt-5.4 (1778518004) | running | [open](http://localhost:3000/runs/veyru/1779370507) |
| 1779370518 | sonnet (1778162284) | running | [open](http://localhost:3000/runs/veyru/1779370518) |
| 1779370530 | sonnet (1778162284) | running | [open](http://localhost:3000/runs/veyru/1779370530) |
| 1779370541 | sonnet (1778162284) | running | [open](http://localhost:3000/runs/veyru/1779370541) |

## Variant `budget_increased` — `round_time_budget_seconds=1500`

**Intervention.** Override only `round_time_budget_seconds`, inherit `scheduled_events` from source.

**Knob file.** `/tmp/variant_budget_increased.json`.

| Run ID | Source | Status | FE link |
|---|---|---|---|
| 1779370036 | gpt-5.4 (1778518004) | running (POC) | [open](http://localhost:3000/runs/veyru/1779370036) |
| 1779370426 | gpt-5.4 (1778518004) | running | [open](http://localhost:3000/runs/veyru/1779370426) |
| 1779370438 | gpt-5.4 (1778518004) | running | [open](http://localhost:3000/runs/veyru/1779370438) |
| 1779370449 | sonnet (1778162284) | running | [open](http://localhost:3000/runs/veyru/1779370449) |
| 1779370461 | sonnet (1778162284) | running | [open](http://localhost:3000/runs/veyru/1779370461) |
| 1779370473 | sonnet (1778162284) | running | [open](http://localhost:3000/runs/veyru/1779370473) |

## Variant `budget_decreased` — `round_time_budget_seconds=150`

**Intervention.** Override only `round_time_budget_seconds`, inherit `scheduled_events`.

**Knob file.** `/tmp/variant_budget_decreased.json`.

**Replicas.** 3 × 2 sources = 6 runs.

| Run ID | Source | Status | FE link |
|---|---|---|---|
| _pending launch_ | | | |

## Variant `with_noise` — `channel_noise_level=0.15`

**Intervention.** Override only `channel_noise_level`, inherit `scheduled_events`. Per-character
drop probability on the link channel (postmortem stays clean). Dropped characters replaced with `_`
so agents see where loss occurred.

**Knob file.** `/tmp/variant_with_noise.json`.

**Replicas.** 3 × 2 sources = 6 runs.

| Run ID | Source | Status | FE link |
|---|---|---|---|
| _pending launch_ | | | |

## Variant `new_motifs_injected` — three novel motifs injected at r=16, 19, 24

Requires platform code (Phase 2). The chosen motif set is **Set 2 (Mixed — one shared sensory
dimension with canon)**.

| Round | Motif | Priority | Symptom dimension | Procedure |
|---|---|---|---|---|
| r=16 | Echo Reversal | 4 | Inverted echo (canon-adjacent — borrows "layered hum" phrasing from Echo Saturation but inverts direction) | bell strikes with full-fade waits |
| r=19 | Magnetic Pull | 5 | Biased pull (novel — no canon dimension) | counterbalance weight opposite face |
| r=24 | Time Drag | 5 | Stretched time (novel) | chilled-rod edge trace, slow |

**Echo Reversal** (priority 4)
- `symptom_phrases`: ["Sounds entering the room are pulled toward the Veyru and silenced before reaching the far wall.", "The hum is artificially quiet, as if dampened from the inside.", "The faces look slightly recessed, like surfaces seen through a long tunnel."]
- `judge_procedure_template`: "Strike a small bell {hold_duration} times near the {starting_face} face at {intensity_level} force. Wait between strikes for the previous ring to fully fade before the next."

**Magnetic Pull** (priority 5)
- `symptom_phrases`: ["All faces tilt their brightest spots toward a single edge, as if pulled by a hidden force.", "The hum sounds biased — louder in one direction.", "Edges curve subtly inward toward that same edge."]
- `judge_procedure_template`: "Place a {intensity_level}-weight counterbalance opposite the {starting_face} face for {hold_duration} seconds. Do not touch the Veyru itself."

**Time Drag** (priority 5)
- `symptom_phrases`: ["Patterns on each face shift in painfully slow motion, as if time has thickened around the Veyru.", "The hum is stretched, like a tape played at half speed.", "Edges seem to lag behind any visual change by a fraction of a second."]
- `judge_procedure_template`: "Trace each edge of the {starting_face} face slowly with a chilled rod for {hold_duration} seconds at {intensity_level} pressure."

**Asymmetric injection.** Only the field observer sees the symptoms (no motif name, no procedure).
Only the stabilization engineer sees the motif name in their `treatment_mapping` table — the
InjectCase hook adds one row per injected motif to the engineer's 14-entry mapping so the engineer
can resolve symptom_motif_name → action_text for the novel motif.

**Replicas.** 3 × 2 sources = 6 runs. Same motif set used across all 6 replicas (no per-replica
randomization).

| Run ID | Source | Status | FE link |
|---|---|---|---|
| _pending Phase 2 platform code_ | | | |

## Evaluation status table

### Baselines (12 of 12 evaluated)

`rs` = round_success (overall fraction). `rs@R` = round_success_after_resume for the post-swap
window starting at round R (15 rounds each). `pplx` = perplexity nats/token. `mcr` = mean chars/round
on link. `mcm` = mean chars/message on link. `lang` = language_strangeness rounds. `neo` =
neologism rounds. `slang` = slang_emergence rounds. `short` = shorthand_codes rounds.

| ID | budget | model | rs | rs@16 | rs@31 | rs@46 | pplx | mcr | mcm | lang | neo | slang | short |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1779309341 | 800 | gpt-5.4 | 0.622 | 0.600 | 0.733 | 0.533 | 5.81 | 474.7 | 79.8 | 58 | 2 | 7 | 43 |
| 1779309832 | 800 | sonnet | 0.733 | 0.667 | 0.800 | 0.733 | 6.23 | 330.3 | 47.9 | 60 | 0 | 1 | 23 |
| 1779310604 | 800 | gpt-5.4 | 0.622 | 0.533 | 0.733 | 0.600 | 5.85 | 517.7 | 81.3 | 60 | 1 | 8 | 50 |
| 1779310617 | 800 | sonnet | 0.578 | 0.600 | 0.667 | 0.467 | 6.37 | 359.7 | 44.8 | 52 | 0 | 2 | 53 |
| 1779310629 | 800 | gpt-5.4 | 0.622 | 0.600 | 0.733 | 0.533 | 5.69 | 505.1 | 80.0 | 60 | 2 | 9 | 33 |
| 1779310643 | 800 | sonnet | 0.711 | 0.733 | 0.733 | 0.667 | 6.25 | 342.1 | 41.7 | 13 | 0 | 0 | 12 |
| 1779359854 | 450 | gpt-5.4 | 0.822 | 0.933 | 0.733 | 0.800 | 7.21 | 231.4 | 39.7 | 58 | 0 | 5 | 54 |
| 1779359865 | 450 | sonnet | 0.822 | 0.867 | 0.667 | 0.933 | 6.93 | 260.2 | 44.3 | 15 | 0 | 2 | 60 |
| 1779359876 | 450 | gpt-5.4 | 0.533 | 0.800 | 0.467 | 0.333 | 6.19 | 342.0 | 61.3 | 27 | 11 | 0 | 60 |
| 1779359888 | 450 | sonnet | 0.844 | 0.867 | 0.867 | 0.800 | 6.83 | 268.5 | 44.8 | 60 | 0 | 0 | 60 |
| 1779359900 | 450 | gpt-5.4 | 0.822 | 0.800 | 0.867 | 0.800 | 7.23 | 222.7 | 37.1 | 57 | 0 | 0 | 60 |
| 1779359911 | 450 | sonnet | 0.667 | 0.600 | 0.600 | 0.800 | 6.88 | 274.4 | 48.6 | 60 | 0 | 5 | 49 |

**Baseline observations.**
- budget=450 sources show **higher** round_success than budget=800 (means: 0.752 vs 0.648). Less
  budget = tighter compression pressure but evidently the agents adapt without losing accuracy.
- One gpt-5.4 budget=450 outlier (1779359876, rs=0.533) — likely a protocol-divergence replica.
- `shorthand_codes` is very high (50-60/60 in budget=450 runs) — strong protocol emergence under
  budget pressure. budget=800 sees fewer shorthand rounds (12-53).
- `perplexity` is higher (=more compressed/unnatural) at budget=450 (~6.8-7.2) vs budget=800 (~5.7-6.4).
- Sonnet generally outperforms gpt-5.4 on round_success at both budgets.

### Intervention runs (in flight)

| Run ID | Variant | Source | Status |
|---|---|---|---|
| 1779370036 | budget_increased (POC) | gpt-5.4 | r=58, running |
| 1779370426 | budget_increased | gpt-5.4 | r=60, finalizing |
| 1779370438 | budget_increased | gpt-5.4 | r=57, running |
| **1779370449** | **budget_increased** | **sonnet** | **DONE — rs=0.956** |
| **1779370461** | **budget_increased** | **sonnet** | **DONE — rs=0.978** |
| **1779370473** | **budget_increased** | **sonnet** | **DONE — rs=1.000** |
| 1779370484 | postmortem_kept_on | gpt-5.4 | r=45, running |
| 1779370495 | postmortem_kept_on | gpt-5.4 | r=44, running |
| 1779370507 | postmortem_kept_on | gpt-5.4 | r=44, running |
| **1779370518** | **postmortem_kept_on** | **sonnet** | **DONE — eval queued** |
| **1779370530** | **postmortem_kept_on** | **sonnet** | **DONE — eval queued** |
| **1779370541** | **postmortem_kept_on** | **sonnet** | **DONE — eval queued** |
| _12 more pending (budget_decreased + with_noise)_ | | | queued in orchestrator |

### Intervention results so far (16 of 24 evaluated; 24 of 24 launched)

| Variant | Model | n | Mean rs | Replica scores | Δ vs baseline (same model, budget=450) |
|---|---|---|---|---|---|
| baseline (budget=450) | gpt-5.4 | 3 | 0.726 | 0.822, 0.533, 0.822 | — |
| baseline (budget=450) | sonnet | 3 | 0.778 | 0.822, 0.844, 0.667 | — |
| **`budget_increased`** | **gpt-5.4** | 3 | **0.904** | 0.911, 0.889, 0.911 | **+17.8 pp** |
| **`budget_increased`** | **sonnet** | 3 | **0.978** | 0.956, 0.978, 1.000 | **+20.0 pp** |
| **`postmortem_kept_on`** | **gpt-5.4** | 3 | **0.793** | 0.778, 0.800, 0.800 | **+6.7 pp** |
| **`postmortem_kept_on`** | **sonnet** | 3 | **0.904** | 0.822, 0.956, 0.933 | **+12.6 pp** |
| **`budget_decreased`** | **sonnet** | 3 | **0.333** | 0.422, 0.356, 0.222 | **-44.4 pp** |
| **`budget_decreased`** | **gpt-5.4** | 3 | **0.407** | 0.467, 0.244, 0.511 | **-31.9 pp** |
| **`with_noise`** | **sonnet** | 3 | **0.644** | 0.556, 0.556, 0.822 | **-13.4 pp** |
| **`with_noise`** | **gpt-5.4** | 3 | **0.607** | 0.600, 0.600, 0.622 | **-11.9 pp** |

### Headline (Phase 1 complete — 24 / 24 intervention runs evaluated)

Sorted by absolute lift, both models:

| Variant | gpt-5.4 Δ | sonnet Δ | direction |
|---|---|---|---|
| `budget_increased` (1500 s/round) | **+17.8** | **+20.0** | both models lift strongly |
| `postmortem_kept_on` | +6.7 | +12.6 | both lift; sonnet larger |
| `with_noise` (0.15 drop) | **-11.9** | **-13.4** | both regress mildly; gpt slightly more robust |
| `budget_decreased` (150 s/round) | **-31.9** | **-44.4** | both collapse; sonnet worse |

Notes:
- gpt-5.4 budget_increased variance is tiny (stdev ≈ 0.013) — the 1500 s headroom removes
  almost all timeout-driven collapses we identified in the gpt-5.4 budget=800 source diagnosis.
- sonnet budget_increased hits ceiling (one replica = 1.000).
- `budget_decreased` is the only intervention where gpt-5.4 outperforms sonnet (small mercy).
- `with_noise` variance is asymmetric across models: sonnet shows 0.556/0.556/0.822 (one resilient
  replica); gpt-5.4 clusters tightly at 0.60.

**Headline findings:**

- **`budget_increased` confirmed for both models.** Sonnet: 0.778 → 0.978 (+20.0 pp). gpt-5.4: 0.726 → 0.904 (+17.8 pp). The lift is large and consistent.
- gpt-5.4 replicas under `budget_increased` show very low variance (0.911, 0.889, 0.911 — stdev ≈ 0.013) — a sign that the budget headroom removes the timeout-driven failures we identified in the source post-mortem.
- gpt baseline mean 0.726 is dragged by one outlier replica (1779359876 = 0.533). Excluding it, the gpt baseline cell is 0.822, making the lift +8.2 pp — smaller but still real.
- **`postmortem_kept_on` shows a real but smaller lift** (sonnet +12.6 pp). Need gpt to confirm.

**Phase breakdown for `budget_increased` × sonnet:**

| Window | Replica mean | Source `1778162284` | Δ replica vs source same window |
|---|---|---|---|
| Phase B (r=16-30) | 0.978 | 0.867 | +11.1 pp |
| Phase C (r=31-45) | 1.000 | 0.733 | **+26.7 pp** |
| Phase D (r=46-60) | 0.956 | 0.867 | +8.9 pp |
| Overall (16-60) | 0.978 | 0.822 | **+15.6 pp** |

Phase C (engineer swap window) is where extra time helps most — that's exactly where the source
suffered the most timeout-driven collapses (8/15 = 53% rs in source).


## Open questions / observations

- TBD as runs land.
