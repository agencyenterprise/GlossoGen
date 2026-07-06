# Protocol-learnability export

Exports the data behind the Streamlit **Protocol learnability** tab
(`analysis/results_viewer/protocol_learnability_tab.py`) into spreadsheet form. It reuses
the baseline round-success export's column schema, adding only a few cohort columns plus
the one signal the tab doesn't surface directly: **`round_success_after_resume`**.

One invocation produces **one workbook** covering every phase, so it maps 1:1 onto the online
spreadsheet's data tabs. Frontier (Anthropic/OpenAI) and self-hosted **Llama** observers share
the same `phase=baseline` runs (the source teams that developed the protocol) and the same
`run_level` / `message_level` schema; they split only at the aggregate, whose column set is
cohort-specific (`baseline_aggregate` for frontier, `baseline_aggregate_llama` for Llama).

## Phases

| phase label | what it is |
|---|---|
| `phase=baseline` | the 15-round source team that developed the private protocol (shared by both cohorts) |
| `phase=resume_expected` | the intact team resumed at the swap boundary, postmortem on (the *expected* ceiling) |
| `phase=resume_expected_no_postmortem` | intact team resumed, postmortem killed going forward (isolates the no-postmortem effect from the fresh-observer effect) |
| `phase=replace_learned` | a fresh **same-model** field observer that learned the protocol from the windowed link transcript (the `history=` label records the window: 0/1/5/10 prior link rounds) |
| `phase=replace_cross_family` | a fresh **other-family** observer (the `observer=` label records its family) |
| `phase=replace_llama` | a fresh **Llama-3.3-70B** observer (self-hosted via Modal); `observer=llama`, `history=` window as in `replace_learned` |

Each derived run links to its baseline through the `src=<scenario>/<ts>` label and carries a
`replace_manifest.json` (`rounds_after_swap`). Runs derive directly from the `src=` baseline
(no supersession resolution — every baseline in the cohort is current; see the integrity
checks under *Run Output Directory Structure* in the repo `CLAUDE.md`).

## Layout

```
analysis/protocol_learnability_export/
├── README.md                       # this file
├── export_protocol_learnability.py
└── output/                         # generated; regenerated on each run
    ├── protocol_learnability.xlsx                       # all four sheets in one workbook
    ├── protocol_learnability_run_level.csv
    ├── protocol_learnability_message_level.csv
    ├── protocol_learnability_baseline_aggregate.csv
    └── protocol_learnability_baseline_aggregate_llama.csv
```

## Regenerate

Run from the repo root — a single invocation writes the whole workbook:

```bash
VIRTUAL_ENV= uv run --no-sync --with openpyxl \
  python -m analysis.protocol_learnability_export.export_protocol_learnability
```

`--with openpyxl` is only needed for the `.xlsx`; the CSVs are written regardless. The first
run scores every link message's gpt2 perplexity and caches it beside each run's JSONL
(`message_perplexity_cache.json`); later runs reuse the cache and only re-score runs whose
JSONL changed. Other flags: `--runs-dir` (default `runs`), `--scenario` (default `veyru`),
`--output-dir`, `--stem` (default `protocol_learnability`).

To push the regenerated workbook to the online spreadsheet, see
[`analysis/sheets_sync`](../sheets_sync/README.md) (`--target protocol_learnability`).

## `round_success_after_resume`

The stored metric's `score`: the fraction of post-resume rounds won over rounds
`round_start`–(`round_start` + `rounds_after_swap`) — rounds 15–25 in this experiment.
Blank on baseline runs (they carry no swap manifest, so the metric is not emitted).

## Sheets

### `run_level` — one row per cohort run

The baseline export's `run_level` columns — `run_id`, `scenario`, `field_observer_model`,
`engineer_model`, `model_class`, `postmortem`, `round_time_budget_seconds`, `random_seed`,
`total_rounds`, `round_success_count`, `perplexity`, `english_ngram_surprisal`,
`english_ngram_backoff_surprisal`, `message_entropy`, `gzip_compression_ratio`, `mcm`,
`labels` — plus the cohort columns
`phase`, `src_id`, `observer_model`, `history`, `rounds_after_swap`, and
`round_success_after_resume`. (`round_success_fraction` is dropped — it's just
`round_success_count / total_rounds`.)

`perplexity` (run-wide mean per-message surprisal, nats/gpt2), `english_ngram_surprisal`
(run-wide mean per-message per-char surprisal under an English char trigram — higher = less
English-like), `english_ngram_backoff_surprisal` (same, richer variant: case-sensitive,
digits + punctuation kept, stupid-backoff smoothing), `message_entropy` (run-wide mean within-message character Shannon entropy,
bits/char — lower = more repetitive/compressible), `gzip_compression_ratio` (run-wide mean
per-message raw-DEFLATE compressed/original with the constant gzip framing excluded — lower =
more compressible/repetitive), and `mcm` (run-wide mean chars per link message)
are rolled up from the per-message `message_level` scoring, since these runs carry no
`perplexity` / `mcm` metric in their reports.

### `message_level` — one row per link-channel message

The baseline export's `message_level` columns — sender role, `message_text`, `chars`,
per-message gpt2 `perplexity`, per-message English-char-trigram `english_ngram_surprisal`
(higher = less English-like), per-message `english_ngram_backoff_surprisal` (backoff variant:
case-sensitive, digits + punctuation kept), per-message `message_entropy` (within-message character Shannon
entropy, bits/char; lower = more repetitive), per-message `gzip_compression_ratio` (raw-DEFLATE
compressed/original, gzip framing excluded; lower = more compressible/repetitive), substage ground truth (`substage`, `symptoms` / `actions`,
`substage_stabilized`), `message_index_in_substage`, and the round-level `success` (0/1
whole-round outcome) / `note` — plus the cohort columns `phase`, `src_id`, `observer_model`.
One row per link message across **every round each run played** (rounds 1–25 for derived
runs, since their cloned JSONL carries the source's pre-swap history). Substages with no link
traffic produce no rows.

### `baseline_aggregate` — one row per baseline (frontier)

Mirrors the tab's `BaselineLearnability`, computed on `round_success_after_resume`. Fixed
columns: `src_id`, `field_observer_model`, `engineer_model`, `model_class`,
`round_time_budget_seconds`, `baseline_round_success_fraction` (the baseline's own 1–15
performance), `cross_family_observer`. Then, per frontier phase `expected` / `expected_no_pm` /
`learned` / `cross_family`: `n_<prefix>`, `<prefix>_mean`, `<prefix>_std`, and
`delta = learned − expected_no_pm` (the fresh same-model observer's transmission gap vs the
no-postmortem ceiling).

### `baseline_aggregate_llama` — one row per baseline (Llama)

Same fixed columns, then the single phase `llama`: `n_llama`, `llama_mean`, `llama_std`, and
`delta = llama − baseline` (the fresh Llama observer's post-swap success vs the source team's
own baseline success). `cross_family_observer` is blank.

Both aggregates use the tab's semantics: mean over the phase's replicas, sample std (`ddof=1`)
when `n ≥ 2` else `0.0`, and `None` when the phase has no replicas.
