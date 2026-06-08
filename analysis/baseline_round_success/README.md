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
    ├── baseline_round_success_message_level.csv
    ├── baseline_round_success_round_context.csv
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
`total_rounds`, `round_success_count`, `round_success_fraction`, `perplexity` (run-wide
mean per-token surprisal, nats/gpt2), `mcm` (run-wide mean chars per link message),
`labels`.

### `message_level` — one row per link-channel message

A veyru round is a multi-stage case: the team stabilizes one stage, then new symptoms
appear for the next. This sheet has one row per link-channel message, tagged with the
substage it belongs to. Good for sequence/turn-level analysis of the conversation.

Message columns:

- `message_agent` — sender role, normalized to `field_observer` or
  `stabilization_engineer` (the engineer's varying ids — including the legacy
  `specialist` — all map to `stabilization_engineer`).
- `message_text` — the message body.
- `message_index_in_substage` — 1-indexed order of the message within its substage.
- `chars` — character count of the message (`len(message_text)`); the per-message value
  that `mcm` aggregates.
- `perplexity` — per-message mean per-token surprisal (nats) under `gpt2`, recomputed at
  export time with the same method as the `perplexity` metric. Blank for empty or
  single-token messages (no left context → NaN).

Substage context (repeated across the substage's messages):

- `substage` — 1-indexed stage number within the round.
- `symptoms` / `actions` — that stage's observable symptoms (what the observer saw) and
  the judge's expected procedure.
- `substage_stabilized` — `1` if the team stabilized this substage, else `0` (the last
  reached substage of a failed round is `0`).

Messages are attributed to the substage in effect when sent (the counter advances on each
successful stabilization), so the observer's "Done. New: <symptoms>" message opens the
next substage. Messages are walked over the substages the team reached
(`stages_reached = min(stabilized_stages + 1, total_stages)`); **substages with no link
traffic produce no rows.**

Repeated round-level columns (identical across a round's message rows): `round_number`,
`success` (0/1, whole-round outcome), `success_raw`, `note`, plus all the run covariates
(`field_observer_model`, `engineer_model`, `model_class`, `postmortem`,
`round_time_budget_seconds`, `random_seed`, `easy_rounds`).

The round-start briefings live in the separate `round_context` sheet (below) to keep this
sheet small — join on `run_id` + `round_number`.

### `round_context` — one row per (run, round)

The large round-start briefings, stored once per round instead of repeated on every
message row (they were ~86% of the file otherwise). Join to `message_level` on
`run_id` + `round_number`.

- `run_id`, `round_number` — join keys.
- `field_observer_round_event` / `engineer_round_event` — the `--- NEW VEYRU ---`
  briefing each agent received at round start (the engineer's carries the full stellar
  table; the observer's, the stage-1 symptoms).

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
