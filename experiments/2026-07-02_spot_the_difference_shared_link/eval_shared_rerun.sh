#!/bin/bash
# spot_the_difference SHARED-LINK re-run evaluation (post round-4 fix).
#
# Gates STRICTLY on `simulation_ended`. Selects the NEW clean shared-link runs:
# labelled "shared_link" AND NOT "round_4_bug" (the old contaminated 4 carry both
# labels, so they are excluded). Canonical haiku judge, same metric set as the
# baseline. Because the link channel is SHARED, char/language metrics emit POOLED
# base names (perplexity, mean_chars_per_round, ...); round_success stays per-team.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/spot_shared_rerun_eval.log
CAP=10
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,round_ended_idle,round_ended_timeout,mean_chars_per_round,mean_chars_per_message,perplexity,message_entropy,gzip_compression_ratio,english_ngram_surprisal,content_filter_refusal,shorthand_codes,slang_emergence,neologism,language_strangeness,language_repetition,communication_open_coding,dialog_retransmission

count_running_evals() {
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt evaluate spot_the_difference" \
    | grep -v grep | wc -l | tr -d ' '
}

echo "=== spot_the_difference shared_link re-run eval pass started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/spot_the_difference/*/; do
  [ -f "$d/labels.json" ] || continue
  grep -q '"shared_link"' "$d/labels.json" || continue
  grep -q '"round_4_bug"' "$d/labels.json" && continue   # skip the old contaminated 4
  grep -q '"simulation_ended"' "$d/spot_the_difference.jsonl" 2>/dev/null \
    || { echo "$(date) SKIP (not finished) $d" >> "$LOG"; continue; }
  [ -f "$d/spot_the_difference_report.json" ] \
    && grep -q 'round_success' "$d/spot_the_difference_report.json" \
    && { echo "$(date) SKIP (already evaluated) $d" >> "$LOG"; continue; }
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 10; done
  echo "$(date) eval $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate spot_the_difference \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_shared_rerun_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) shared_link re-run eval pass complete" >> "$LOG"
