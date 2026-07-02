# spot_the_difference export

Modelling-ready spreadsheet export of the `spot_the_difference` cohort. The
per-team counterpart to `baseline_round_success/` and `channel_noise_export/`
(which are single-team + staged and cover veyru / drive_module_repair).

`spot_the_difference` runs two competing teams; each team runs two viewers (a
left viewer holding scene A, a right viewer holding scene B) who talk on a
private link channel and submit the differences they find. A round is a
**success** for a team when it passes the correctness gate (every planted
difference found, no false positives, within the character budget); in two-team
mode the eligible team with the **fewest** link characters **wins**. Every
char/language metric is scored per team, so the report carries
`round_success_team_a` / `round_success_team_b`, `perplexity_team_a` /
`perplexity_team_b`, and so on.

## Unit of analysis

**(run, team)** — a two-team run contributes two rows to `run_level` (one per
team), keyed by `team_id`. This maps the per-team metric families onto rows and
keeps single-team scenarios' exporters untouched.

## Run

```bash
VIRTUAL_ENV= uv run --no-sync python -m analysis.spot_the_difference_export.export_spot_the_difference \
  --runs-dir ./runs
```

Scopes to runs labelled `baseline`. Pass `--canonical-only` to keep just the
fixed-seed runs (those without a `random_seed` label). Outputs land in
`analysis/spot_the_difference_export/output/` as one CSV per frame plus a
multi-sheet `.xlsx` workbook.

## Frames

| Frame | Grain | What it holds |
|---|---|---|
| `run_level` | (run, team) | per-team outcome numerators (`round_success_count`/`fraction`, `wins_count`/`wins_fraction`, `mean_found_fraction`, `mean_characters_used`, `budget_exceeded_count`, `did_not_submit_count`, `disagreed_count`) and per-team headline metrics (`perplexity`, `english_ngram_surprisal`, `message_entropy`, `gzip_compression_ratio`, `language_repetition`, `mcm`, `mcr`) |
| `round_level` | (run, round, team) | reconstructed outcome (`success`=eligible, `won`, `found_count`/`found_fraction`, `false_positive_count`, `found_all`, `submitted`, `budget_exceeded`, `characters_used`, `members_submitted`/`members_required`/`agreed`, `opponent_characters`/`opponent_found_all`/`opponent_eligible`, `reason`), scene facts (`difference_count`, `difference_kinds`, `object_count`, `grid_size`), and per-round-per-team `perplexity`/`mcr`/`language_repetition` |
| `message_level` | link message | `message_agent`, pristine `message_text`, `message_text_transmitted`, `chars`, per-message `perplexity`/`english_ngram_surprisal`/`message_entropy`/`gzip_compression_ratio`/`message_repetition_factor`, round team `success`/`won` |
| `team_aggregate` | (model_class, viewer models, all_must_submit) | mean ± std of the success and win fractions plus mean characters / perplexity / repetition; a sanity check against `run_level` |

## Google Sheets

The workbook feeds the live spreadsheet
[`1x1F0…zKiI`](https://docs.google.com/spreadsheets/d/1x1F0YPsztudX1YwDeWJ-yMp6s3h9uHUBIGzWS79zKiI):

```bash
make sync-sheets-spot   # regenerate the workbook, then push the 5 data tabs
make charts-spot        # (re)build the Plot: * chart tabs + embedded charts
```

`sync-sheets-spot` overwrites only the four data tabs (via
`analysis/sheets_sync/`). `charts-spot` owns the `Plot: *` tabs and is
idempotent — [build_spot_charts.py](build_spot_charts.py) deletes and rebuilds
every chart tab each run. The two never touch each other's tabs. The chart set
mirrors the veyru baseline spreadsheet's intent, adapted to spot's two-team
design:

- **Plot: Model Performance** — COLUMN: per-model mean round-success / win / found fraction.
- **Plot: Round by Round** — three LINE charts: per-model mean success, characters used, perplexity by round.
- **Plot: Perplexity vs Success** — SCATTER: per-(run, team) perplexity vs round-success, one series per model.
- **Plot: Characters per Model** — COLUMN: per-model mean characters used per round (the efficiency headline).

## Notes

- Per-round-per-team outcomes are reconstructed from the JSONL event log through
  the same scoring path the live world uses (`restore_outcomes_from_events`), so
  the correctness gate and fewest-characters win match what happened live. The
  human-readable `reason` is read from the canonical `RoundResultRecorded`
  events.
- Solo (single-team) runs are handled: `team_id` = `solo` and the per-team metric
  columns read the un-suffixed metric names.
