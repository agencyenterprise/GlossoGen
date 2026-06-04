# Baseline round-success export

Exports the data behind the Streamlit baseline tab (round success vs. round-time
budget, closed vs. open models, postmortem on/off) into spreadsheet form for
inferential statistics / mixed-effects modelling.

## Layout

```
analysis/baseline_round_success/
├── README.md                       # this file
├── export_baseline_round_success.py
└── output/                         # generated; regenerated on each run
    ├── baseline_round_success.xlsx              # all three sheets in one workbook
    ├── baseline_round_success_run_level.csv
    ├── baseline_round_success_round_level.csv
    └── baseline_round_success_budget_aggregate.csv
```

## Regenerate

Run from the repo root:

```bash
VIRTUAL_ENV= uv run --no-sync --with openpyxl \
  python -m analysis.baseline_round_success.export_baseline_round_success
```

`--with openpyxl` is only needed for the `.xlsx`; the CSVs are written regardless.
Re-run any time new runs land — it always reads the current `./runs` on disk.

## What's in the cohort

Starts from every veyru run labeled `baseline` (closed-model frontier) or
`baseline_oss` (open-weight) that has a `round_time_budget_seconds` knob and a
`round_success` measurement, then filters for judge soundness:

- **Judge correctness.** Runs launched **before** the cutoff (`--corrected-judge-cutoff`,
  default `2026-06-02`) were scored by the pre-correction stabilization judge, so each is
  validated against its `judge_replay.json` sidecar: any run with ≥1 previously-accepted
  stabilization that flips to rejected under the corrected prompt is dropped (the
  Streamlit judge-replay slider pinned at 0%), and sidecar-less runs are dropped. Runs
  launched **on/after** the cutoff were scored by the corrected judge live during the
  simulation, so they need no replay and are kept without a sidecar.
- **Design.** Every seed mode and easy-round skeleton is included by default and tagged
  with the `random_seed` / `easy_rounds` columns. Pass `--canonical-only` to keep just
  the fixed-`seed=42`, default-easy-round runs.

Design target is **5 replicas per (model × postmortem × budget) cell** (see
`src/schmidt/scenarios/veyru/scripts/run_baseline_no_specialist.py`); the judge filter can
leave a cell below 5.

## Sheets

### `run_level` — one row per run

For binomial GLMMs (`cbind(round_success_count, total_rounds - round_success_count) ~ …`)
or a model on `round_success_fraction`.

`run_id`, `scenario`, `field_observer_model`, `engineer_model`, `model_class`
(closed/open), `postmortem`, `round_time_budget_seconds`, `random_seed`, `easy_rounds`,
`total_rounds`, `round_success_count`, `round_success_fraction`, `labels`.

### `round_level` — one row per (run, round)

The unit for a logistic mixed model
`success ~ log_budget * model_class * postmortem + (1 | model) + (1 | run_id)`.
Carries the per-round metric plus the veyru ground truth read from the event log:

- `success` (0/1), `success_raw`, `note`.
- `veyru_symptoms_1..5` / `veyru_actions_1..5` — per-stage observable symptoms and the
  judge's expected procedure. **Blank for stages the team never reached**
  (`stages_reached = min(stabilized_stages + 1, total_stages)`); stage 1 is always
  present. Cases have up to 5 stages.
- `field_observer_round_event` / `engineer_round_event` — the round-start briefing each
  agent received (the `--- NEW VEYRU ---` injection; the postmortem/discussion injection
  is excluded).
- `link_messages` — JSON list `[{"agent": ..., "message": ...}]` of the round's
  link-channel conversation, in chronological order.

### `budget_aggregate` — one row per cell

Per (model_class, field_observer_model, engineer_model, postmortem, random_seed,
easy_rounds, budget): `n`, and mean / std (population, ddof=0) / min / max of
`round_success_fraction`, plus `mean_success_count`. A sanity check against the
plotted mean ± std bands.

## Useful flags

| Flag | Default | Effect |
|---|---|---|
| `--canonical-only` | off | Keep only fixed-`seed=42` + default-easy-round runs. |
| `--judge-flip-threshold F` | `0.0` | Max flip ratio a pre-cutoff run may have (0.0 = drop on any flip). |
| `--allow-missing-sidecar` | off | Keep pre-cutoff runs without a `judge_replay.json`. |
| `--corrected-judge-cutoff YYYY-MM-DD` | `2026-06-02` | Runs on/after this date bypass the judge-replay check. |
| `--scenario`, `--runs-dir`, `--output-dir`, `--stem` | veyru / runs / output / baseline_round_success | Standard overrides. |
