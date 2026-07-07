#!/bin/bash
# spot_the_difference FIXED-baseline re-run evaluation — one pass over the cohort.
#
# ##############################################################################
# # CRITICAL — NEVER EVALUATE A RUN BEFORE IT HAS EMITTED `simulation_ended`.   #
# # Gates STRICTLY on `grep -q '"simulation_ended"'`, never a round count.      #
# ##############################################################################
#
# Matches the 15 fixed-baseline runs by the ["baseline"] label (the old buggy
# runs are relabelled ["round_4_bug"], so they are excluded). Canonical haiku
# judge; two-team runs emit per-team measurements. Merges into each run's
# report; skips runs already carrying round_success.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/spot_rerun_eval.log
CAP=10
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,round_ended_idle,round_ended_timeout,mean_chars_per_round,mean_chars_per_message,perplexity,message_entropy,gzip_compression_ratio,english_ngram_surprisal,content_filter_refusal,shorthand_codes,slang_emergence,neologism,language_strangeness,language_repetition,communication_open_coding,dialog_retransmission

count_running_evals() {
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen evaluate spot_the_difference" \
    | grep -v grep | wc -l | tr -d ' '
}

echo "=== spot_the_difference baseline re-run eval pass started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/spot_the_difference/*/; do
  [ -f "$d/labels.json" ] && grep -q '"baseline"' "$d/labels.json" || continue
  grep -q '"simulation_ended"' "$d/spot_the_difference.jsonl" 2>/dev/null \
    || { echo "$(date) SKIP (not finished) $d" >> "$LOG"; continue; }
  [ -f "$d/spot_the_difference_report.json" ] \
    && grep -q 'round_success' "$d/spot_the_difference_report.json" \
    && { echo "$(date) SKIP (already evaluated) $d" >> "$LOG"; continue; }
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 10; done
  echo "$(date) eval $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate spot_the_difference \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_rerun_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) baseline re-run eval pass complete" >> "$LOG"
