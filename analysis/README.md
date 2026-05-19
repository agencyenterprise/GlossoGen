# Analysis

Static plot generators and the interactive Streamlit results viewer. Every script is run from the repo root and reads from `runs/`.

## Generated plots

Each plot script writes its PNGs into this directory. Run them from the repo root:

```bash
VIRTUAL_ENV= uv run --no-sync python analysis/<script>.py
```

All static plots ship at presentation-scale font sizes. The font / figsize / margin tweaks live near the top of each script.

### `plot_round_success_with_mcm.py`

Per-round round success rate and per-round mean chars per message for the Veyru `random_seed` + `no_ordered_easy_rounds` cohort (90 runs). Writes three PNGs:

- `round_success_with_mcm.png` — two vertically stacked panels sharing the X axis (success rate on top, MCM below). X-tick labels repeat on both panels; Y-labels are aligned via `fig.align_ylabels`.
- `round_success.png` — success-rate only (Wilson 95% CI bars + cell-level replica dots).
- `mean_chars_per_message.png` — MCM only.

Success means are computed over the 90 raw per-round outcomes; the dot scatter is computed over per-cell `(model, budget, postmortem)` means so the dots form a continuous cloud rather than a binary 0/1 band. Wilson 95% CI is bounded to `[0, 1]` by construction.

### `plot_baseline_budget_sweep.py`

Round success vs per-round `round_time_budget_seconds` (log scale) for Veyru baseline runs, split into two vertically stacked panels:

- **Closed models** (top) — every run carrying the `baseline` label (sonnet-4.6, opus-4.7, gpt-5.4).
- **Open models** (bottom) — every run carrying the `baseline_oss` label (Llama-3.3-70B, Qwen3-32B).

Each panel renders one series per `(model, postmortem_enabled)`: solid line + circle markers for postmortem-on, dashed line + square markers for postmortem-off. Replica dots are jittered in log-space; mean traces carry ±1 std error bars. Per-model brand colours are defined in `_MODEL_COLORS`. Writes `baseline_budget_sweep.png`.

### `plot_language_emergence.py`

Side-by-side per-round perplexity (left panel) and mean chars per message (right panel) for Veyru and `container_yard_stacking`. Two lines per panel (one per scenario) with shaded ±1 std bands. Writes `language_emergence.png`.

Cohorts:

- **Veyru** — `random_seed` + `no_ordered_easy_rounds` (90 runs).
- **Container yard** — all `baseline` runs (74 runs).

### `plot_language_features.py`

Grouped vertical bar chart of per-feature presence frequency across both scenarios, scored against the same Veyru ontology (`runs/veyru/_ontology/20260511T142136Z_full.json`). For each category, the bar height is the fraction of cohort runs with confidence ≥ 0.5. Categories with max prevalence below `_MIN_PREVALENCE_TO_SHOW` (0.5) are dropped so the chart stays readable at presentation fonts — the script prints which fraction of the ontology's categories is rendered. Writes `language_features.png`.

To regenerate the feature-presence sidecars for one scenario against a specific ontology:

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate <scenario> \
  --run-dir runs/<scenario>/<timestamp> \
  --metrics communication_feature_presence \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  --ontology-path runs/veyru/_ontology/<version>.json
```

Re-running pass 3 overwrites each run's `communication_feature_presence.json`. Back up the existing sidecar first if the prior ontology's scores need to be preserved:

```bash
cp runs/<scenario>/<timestamp>/communication_feature_presence.json \
   runs/<scenario>/<timestamp>/communication_feature_presence.<previous_ontology>.json
```

The Streamlit "Language features" tab resolves the ontology JSON by version, so after re-scoring against a foreign ontology, copy that ontology JSON into `runs/<scenario>/_ontology/` so the tab can still load.

## `results_viewer/`

The Streamlit results viewer. Tabs: Timeline, Baseline, OSS frontier, Verbosity, Probe similarity, Feature presence, Resume, Cross-swap, Multi-swap. Shared seed-mode filter at the top of every tab.

Launch:

```bash
make results-viewer
```

Or directly:

```bash
VIRTUAL_ENV= PYTHONPATH=. uv run --group analysis --no-sync streamlit run analysis/results_viewer/app.py
```

## `cross_run_swap_order_asymmetry.md`

Free-text analysis notes on cross-run swap ordering asymmetry — read directly, no script to run.
