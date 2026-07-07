# Veyru channel-noise sweep (2026-06-19)

Measures how round-success degrades as the comm link gets noisier, and whether
the (clean) postmortem channel lets teams develop noise-robust shorthand.

## Design

Baseline (no swap) grid:

| Dimension | Values | n |
|---|---|---|
| `channel_noise_level` | 0.2, 0.4, 0.6 | 3 |
| `round_time_budget_seconds` | 450, 800 | 2 |
| model | `gpt-5.4` (openai), `claude-opus-4-7` (anthropic) | 2 |
| replicas | 5 | 5 |

**60 runs** (30 per provider).

Fixed knobs (`knobs_base.json`): 15 rounds, postmortem **on**, `seed=42`,
`easy_round_numbers=[]`, `max_round_duration_seconds=600`,
`postmortem_duration_seconds=240`, judge `claude-haiku-4-5-20251001`. Noise and
budget are overridden inline per cell.

Noise applies **only to the link channel** (per-character drop, dropped chars
become `_`); the postmortem channel stays lossless. The pristine message the
agent sent is recoverable from `ToolResultReceived.arguments.text` and joins to
the persisted (corrupted) `MessageSent` via `SendMessageResult.message_id`.

## Run

```bash
nohup bash experiments/2026-06-19_veyru_channel_noise/launch_noise.sh \
  > /tmp/veyru_noise.stdout 2>&1 &
disown
```

Per-provider parallel queues, cap **10** each. Runs are labelled on launch:
`["channel_noise", "phase=baseline", "noise=<lvl>", "budget=<b>", "model=<short>", "rc=15"]`.

## Monitor

```bash
tail -20 /tmp/veyru_noise.log
ps -axo command | grep "Python -m glossogen run veyru" | grep -v grep | wc -l
```
