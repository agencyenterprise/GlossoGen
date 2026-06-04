# Analysis

Static plot generators, spreadsheet exports, and the interactive Streamlit
results viewer. Everything is run from the repo root and reads from `runs/`.

Each subfolder is one deliverable with its own README:

| Folder | What it is |
|---|---|
| [`plots/`](plots/) | Matplotlib plot generators (round success, budget sweep, language emergence/features, multi-swap phases). PNGs land in `plots/output/`. |
| [`results_viewer/`](results_viewer/) | The Streamlit results viewer (see below). |
| [`baseline_round_success/`](baseline_round_success/) | Spreadsheet export (CSV/XLSX) of the baseline round-success data for inferential statistics. |
| [`judge_validation_set/`](judge_validation_set/) | Balanced labeled set for validating candidate Veyru stabilization judges. |

## `results_viewer/`

The Streamlit results viewer. Tabs: Timeline, Baseline, OSS frontier, Verbosity,
Probe similarity, Feature presence, Resume, Cross-swap, Multi-swap, Protocol
learnability, Judge replay. Shared seed-mode filter at the top of every tab.

Launch:

```bash
make results-viewer
```

Or directly:

```bash
VIRTUAL_ENV= PYTHONPATH=. uv run --group analysis --no-sync streamlit run analysis/results_viewer/app.py
```

## `cross_run_swap_order_asymmetry.md`

Free-text analysis notes on cross-run swap ordering asymmetry — read directly, no
script to run.
