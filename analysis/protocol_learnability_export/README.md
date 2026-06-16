# Protocol-learnability export

Exports the data behind the Streamlit **Protocol learnability** tab
(`analysis/results_viewer/protocol_learnability_tab.py`) into spreadsheet form. It reuses
the baseline round-success export's column schema, adding only a few cohort columns plus
the one signal the tab doesn't surface directly: **`round_success_after_resume`**.

## Layout

```
analysis/protocol_learnability_export/
├── README.md                       # this file
├── export_protocol_learnability.py
└── output/                         # generated; regenerated on each run
    ├── protocol_learnability.xlsx              # all three sheets in one workbook
    ├── protocol_learnability_run_level.csv
    ├── protocol_learnability_message_level.csv
    └── protocol_learnability_baseline_aggregate.csv
```

## Regenerate

Run from the repo root:

```bash
VIRTUAL_ENV= uv run --no-sync --with openpyxl \
  python -m analysis.protocol_learnability_export.export_protocol_learnability
```

`--with openpyxl` is only needed for the `.xlsx`; the CSVs are written regardless. The
first run scores every link message's gpt2 perplexity and caches it beside each run's
JSONL (`message_perplexity_cache.json`); later runs reuse the cache and only re-score runs
whose JSONL changed.

## What's in the cohort

Every run labeled `protocol_learnability`, in five phases:

| phase label | what it is |
|---|---|
| `phase=baseline` | the 15-round source team that developed the private protocol |
| `phase=resume_expected` | the intact team resumed at the swap boundary, postmortem on (the *expected* ceiling) |
| `phase=resume_expected_no_postmortem` | intact team resumed, postmortem killed going forward |
| `phase=replace_learned` | a fresh same-model field observer that learned the protocol from the windowed link transcript |
| `phase=replace_cross_family` | a fresh *other-family* observer (the `observer=` label records its family) |

Each derived run links to its baseline through the `src=<scenario>/<ts>` label and carries
a `replace_manifest.json` (`rounds_after_swap`).

## `round_success_after_resume`

The stored metric's `score`: the fraction of post-resume rounds won over rounds
`round_start`–(`round_start` + `rounds_after_swap`) — rounds 15–25 in this experiment.
Blank on baseline runs (they carry no swap manifest, so the metric is not emitted).

## Sheets

### `run_level` — one row per cohort run

The baseline export's `run_level` columns — `run_id`, `scenario`, `field_observer_model`,
`engineer_model`, `model_class`, `postmortem`, `round_time_budget_seconds`, `random_seed`,
`total_rounds`, `round_success_count`, `perplexity`, `mcm`, `labels` — plus the cohort
columns `phase`, `src_id`, `observer_model`, `history`, `rounds_after_swap`, and
`round_success_after_resume`. (`round_success_fraction` is dropped — it's just
`round_success_count / total_rounds`.)

`perplexity` (run-wide mean per-message surprisal, nats/gpt2) and `mcm` (run-wide mean
chars per link message) are rolled up from the per-message `message_level` scoring, since
these runs carry no `perplexity` / `mcm` metric in their reports.

### `message_level` — one row per link-channel message

The baseline export's `message_level` columns — sender role, `message_text`, `chars`,
per-message gpt2 `perplexity`, substage ground truth (`substage`, `symptoms` / `actions`,
`substage_stabilized`), `message_index_in_substage`, and the round-level `success` (0/1
whole-round outcome) / `note` — plus the cohort columns `phase`, `src_id`,
`observer_model`. One row per link message across **every round each run played** (rounds
1–25 for derived runs, since their cloned JSONL carries the source's pre-swap history).
Substages with no link traffic produce no rows.

### `baseline_aggregate` — one row per baseline

Mirrors the tab's `BaselineLearnability`, computed on `round_success_after_resume`:
`src_id`, `field_observer_model`, `engineer_model`, `model_class`,
`round_time_budget_seconds`, `baseline_round_success_fraction` (the baseline's own 1–15
performance), `cross_family_observer`, then for each derived phase
(`expected` / `expected_no_pm` / `learned` / `cross_family`): `n_<phase>`, `<phase>_mean`,
`<phase>_std`. Finally `delta` — the transmission gap `learned − expected_no_pm`.

Means/std use the tab's semantics: mean over the phase's replicas, sample std (`ddof=1`)
when `n ≥ 2` else `0.0`, and `None` when the phase has no replicas.

**Supersession lineage.** Baselines in this cohort are re-run over time; each replacement is
recorded in `runs/supersedes_map.csv` (`old_run_id,new_run_id`). A derived run's `src=`
points at whichever baseline id was current when it ran, so the aggregate resolves each
`src` through the chain to the head-of-chain (current) baseline before joining. Without this,
re-run baselines would look childless and their derived runs orphaned.
