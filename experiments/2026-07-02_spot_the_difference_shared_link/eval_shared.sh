#!/bin/bash
# Evaluate the 4 shared_link runs with the canonical haiku judge and the same
# metric set as the 2026-07-01 baseline eval. Gates strictly on simulation_ended
# (all four have it). Two-team runs emit per-team round_success_team_a/_team_b;
# because the link channel is SHARED, the char/language metrics emit POOLED base
# names (perplexity, mean_chars_per_round, ...) rather than _team_a/_team_b.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
LOG=/tmp/spot_shared_eval.log
METRICS=round_success,round_ended_idle,round_ended_timeout,mean_chars_per_round,mean_chars_per_message,perplexity,message_entropy,gzip_compression_ratio,english_ngram_surprisal,content_filter_refusal,shorthand_codes,slang_emergence,neologism,language_strangeness,language_repetition,communication_open_coding,dialog_retransmission

echo "=== shared_link eval started $(date) ===" >> "$LOG"
for r in 1783016451 1783016458 1783016466 1783016473; do
  d="$RUNS_DIR/spot_the_difference/$r"
  grep -q '"simulation_ended"' "$d/spot_the_difference.jsonl" 2>/dev/null \
    || { echo "$(date) SKIP not-finished $r" >> "$LOG"; continue; }
  echo "$(date) eval $r" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate spot_the_difference \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_shared_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) shared_link eval complete" >> "$LOG"
