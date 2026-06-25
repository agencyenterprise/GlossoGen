# Channel-noise export

Exports the veyru channel-noise sweep (per-character link-channel noise vs. round
success, across noise levels and round-time budgets) into spreadsheet form for
inferential statistics / mixed-effects modelling. Mirrors the
[`baseline_round_success`](../baseline_round_success/README.md) export's shape so the two
workbooks share a schema and concatenate cleanly.

## Layout

```
analysis/channel_noise_export/
├── README.md                  # this file
├── export_channel_noise.py
└── output/                    # generated; regenerated on each run
    ├── channel_noise.xlsx                 # all four sheets in one workbook
    ├── channel_noise_run_level.csv
    ├── channel_noise_message_level.csv
    ├── channel_noise_round_context.csv
    └── channel_noise_budget_aggregate.csv
```

## Regenerate

Run from the repo root:

```bash
VIRTUAL_ENV= uv run --no-sync --with openpyxl \
  python -m analysis.channel_noise_export.export_channel_noise
```

`--with openpyxl` is only needed for the `.xlsx`; the CSVs are written regardless.
Re-run any time new runs land — it always reads the current `./runs` on disk.

## What's in the cohort

Every veyru run labeled `channel_noise` that has a `round_time_budget_seconds` knob and a
`round_success` measurement. The sweep design is **5 replicas per (model ×
`channel_noise_level` × budget) cell** (see
`experiments/2026-06-19_veyru_channel_noise/`).

`channel_noise_level` is the per-character drop probability applied to the **link
channel only** — the postmortem channel stays lossless. A dropped character is replaced
with `_` in the persisted (transmitted) message.

Columns inherited from the baseline export that are **constant across this cohort** are
kept so the two workbooks concatenate for cross-cohort comparison:

- **`model_class`** — always `closed` (the sweep pairs `gpt-5.4` with `claude-opus-4-7`).
- **`postmortem`** — always `True` (the clean postmortem channel is the whole point: it
  lets teams develop noise-robust shorthand the noisy link can't carry reliably).
- **`random_seed`** — always `False` (the canonical fixed `seed=42`).

## Pristine vs. transmitted text

The text an agent **composes** differs from what the channel **delivers** under noise. The
JSONL stores the transmitted (corrupted) text on the `MessageSent` event; the pristine
pre-transform text survives on the `send_message` tool result and is joined back via
`SendMessageResult.message_id`. The `message_level` sheet reports both, and per-message
`perplexity` (and the run-level `perplexity`) score the **pristine** text — so perplexity
measures the language the agent intended, not underscore-riddled transmission.

## Sheets

### `run_level` — one row per run

For binomial GLMMs (`cbind(round_success_count, total_rounds - round_success_count) ~ …`)
or a model on `round_success_fraction`.

`run_id`, `scenario`, `field_observer_model`, `engineer_model`, `model_class`,
`postmortem`, `round_time_budget_seconds`, **`channel_noise_level`**, `random_seed`,
`total_rounds`, `round_success_count`, `round_success_fraction`, `perplexity` (run-wide
mean per-token surprisal, nats/gpt2, **pristine text**), `english_ngram_surprisal`
(run-wide mean per-char surprisal under an English character trigram, nats, **pristine
text** — higher = less English-like), `message_entropy` (run-wide mean within-message
character Shannon entropy, bits/char, **pristine text** — lower = more
repetitive/compressible), `gzip_compression_ratio` (run-wide mean per-message gzip
compressed/original, **pristine text** — lower = more compressible; short messages are
overhead-dominated so the mean exceeds 1), `dialog_count` / `retransmission_request_count`
(run-wide mean per round from the LLM-judge `dialog_retransmission` metric — clarification/
coordination turns, and requests to repeat/resend lost or garbled info), `mcm` (run-wide mean
chars per link message — length is preserved under character-drop noise), `labels`.

### `message_level` — one row per link-channel message

A veyru round is a multi-stage case: the team stabilizes one stage, then new symptoms
appear for the next. One row per link-channel message, tagged with the substage it
belongs to. Good for sequence/turn-level analysis.

Message columns:

- `message_agent` — sender role, normalized to `field_observer` or
  `stabilization_engineer`.
- `message_text` — the **pristine** text the agent composed (joined via `message_id`).
- `message_text_transmitted` — what the channel delivered (`_` for dropped characters).
- `message_index_in_substage` — 1-indexed order of the message within its substage.
- `chars` — character count (`len(message_text)`); preserved under noise, so equal for
  pristine and transmitted.
- `chars_dropped` — number of `_` substitutions in the transmitted text.
- `drop_fraction` — `chars_dropped / chars` (blank for empty messages); per-message
  realized noise, which averages to `channel_noise_level` within a cell.
- `perplexity` — per-message mean per-token surprisal (nats) under `gpt2`, on the pristine
  text, same method as the `perplexity` metric. Blank for empty or single-token messages.
- `english_ngram_surprisal` — per-message mean per-char surprisal (nats) under an English
  character trigram, on the pristine text, same method as the `english_ngram_surprisal`
  metric. Higher = less English-like (degenerate repetition, codes, digit runs score high).
  Blank for empty messages.
- `message_entropy` — per-message within-message character Shannon entropy (bits/char), on
  the pristine text, same method as the `message_entropy` metric. Lower = more
  repetitive/compressible (`LLLLLLL` → 0). Blank for empty messages.
- `gzip_compression_ratio` — per-message gzip compressed/original size ratio, on the pristine
  text, same method as the `gzip_compression_ratio` metric. Lower = more compressible. Note
  gzip's ~18-byte header overhead makes short messages exceed 1.0 (`LLLLLLL` → 3.29); the
  signal is meaningful in aggregate. Blank for empty messages.

Substage context (repeated across the substage's messages):

- `substage` — 1-indexed stage number within the round.
- `symptoms` / `actions` — that stage's observable symptoms and the judge's expected
  procedure.
- `substage_stabilized` — `1` if the team stabilized this substage, else `0`.

Messages are attributed to the substage in effect when sent (the counter advances on each
successful stabilization). Messages are walked over the substages the team reached
(`stages_reached = min(stabilized_stages + 1, total_stages)`); **substages with no link
traffic produce no rows.**

Repeated round-level columns (identical across a round's message rows): `round_number`,
`success` (0/1, whole-round outcome), `note`, plus all the run covariates
(`field_observer_model`, `engineer_model`, `model_class`, `postmortem`,
`round_time_budget_seconds`, `channel_noise_level`, `random_seed`).

The round-start briefings live in the separate `round_context` sheet — join on `run_id` +
`round_number`.

### `round_context` — one row per (run, round)

The large round-start briefings, stored once per round instead of repeated on every
message row. Join to `message_level` on `run_id` + `round_number`. (Briefings are
`injection_delivered` events, not link traffic, so they are never noise-corrupted.)

- `run_id`, `round_number` — join keys.
- `round_success` — 1/0 whole-round outcome; `repetition_factor` — the round's
  `language_repetition` redundancy factor.
- `dialog_count` / `retransmission_request_count` — per-round counts from the LLM-judge
  `dialog_retransmission` metric (clarification/coordination turns, and requests to
  repeat/resend). Blank when the run wasn't scored; `0` for a judged round with no
  occurrences.
- `field_observer_round_event` / `engineer_round_event` — the `--- NEW VEYRU ---`
  briefing each agent received at round start.

### `budget_aggregate` — one row per cell

Per (model_class, field_observer_model, engineer_model, postmortem, random_seed,
**channel_noise_level**, budget): `n`, and mean / std (population, ddof=0) / min / max of
`round_success_fraction`, plus `mean_success_count`. A sanity check against the success
grid.

## Useful flags

| Flag | Default | Effect |
|---|---|---|
| `--scenario`, `--runs-dir`, `--output-dir`, `--stem` | veyru / runs / output / channel_noise | Standard overrides. |
