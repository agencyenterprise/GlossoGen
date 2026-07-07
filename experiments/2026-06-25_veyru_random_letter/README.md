# Veyru random-letter cohort (2026-06-25)

Re-execution of the 2026-06-19 `channel_noise` grid with identical knobs and
models, but `noise_replacement_mode=random_letter` instead of the default
`mask`. The link channel becomes a **substitution channel** (each dropped
character is replaced with a different random letter, no marker) rather than an
**erasure channel** (dropped characters become `_`). This isolates how much the
visible `_` loss-marker was helping teams recover — agents can no longer tell
which characters were corrupted, or that any corruption happened.

## Design

| Dimension | Values | n |
|---|---|---|
| `channel_noise_level` | 0.2, 0.4, 0.6 | 3 |
| `round_time_budget_seconds` | 150, 450, 800 | 3 |
| model | `gpt-5.4` (openai), `claude-opus-4-7` (anthropic) | 2 |
| replicas | 5 | 5 |

**90 runs** (45 per provider).

Fixed knobs (`knobs_base.json`, identical to the channel_noise base plus
`noise_replacement_mode=random_letter`): 15 rounds, postmortem **on**,
`seed=42`, `easy_round_numbers=[]`, `max_round_duration_seconds=600`,
`postmortem_duration_seconds=240`, judge `claude-haiku-4-5-20251001`. Noise and
budget are overridden inline per cell.

Noise applies **only to the link channel**; the postmortem channel stays
lossless. The pristine pre-noise message is recoverable from
`ToolResultReceived.arguments.text` and joins to the persisted (corrupted)
`MessageSent` via `SendMessageResult.message_id`, so the pristine-text metrics
(perplexity / entropy / english_ngram_surprisal) score pre-noise text exactly
as in the channel_noise cohort.

## Run

```bash
nohup bash experiments/2026-06-25_veyru_random_letter/launch_random_letter.sh \
  > /tmp/veyru_random_letter.stdout 2>&1 &
disown
```

Per-provider parallel queues, cap **10** each. Runs are labelled on launch:
`["random_letter", "phase=baseline", "noise=<lvl>", "budget=<b>", "model=<short>", "rc=15"]`.

Run a single budget tier with `NOISE_BUDGETS="800" bash .../launch_random_letter.sh`.

## Monitor

```bash
tail -20 /tmp/veyru_random_letter.log
ps -axo command | grep "Python -m glossogen run veyru" | grep -v grep | wc -l
```

## Evaluate (after drain)

```bash
nohup bash experiments/2026-06-25_veyru_random_letter/eval_random_letter.sh \
  > /tmp/veyru_random_letter_eval.stdout 2>&1 &
disown
```

Gates on `simulation_ended` (never a round count) and runs the same 16-metric
set the channel_noise cohort carries, so the mask vs random_letter comparison is
metric-for-metric.

## Comparison note

Runs are tagged `random_letter`, not `channel_noise`, so the streamlit baseline /
verbosity tabs (which filter on `channel_noise`) will not pick them up as-is.
Compare against the channel_noise cohort by joining on `(model, budget, noise)`.
