#!/bin/bash
# Evaluation for the random_letter cohort: runs the same metric set the
# channel_noise cohort carries (18 registered metrics -> 19 measurements;
# dialog_retransmission emits both dialog_count and retransmission_request_count)
# so the two cohorts are directly comparable. communication_feature_presence is
# intentionally excluded — it was not run on channel_noise.
# Matches runs by the "random_letter" label only, across all budgets. Gate on
# simulation_ended (never a round_advanced count) so the final round is never
# clipped. Merges into each run's existing report.
#
# protocol_explanation probes each agent under its OWN model (gpt/opus); every
# other LLM-judge metric uses the canonical haiku judge.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/veyru_random_letter_eval.log
CAP=10
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,perplexity,mean_chars_per_round,mean_chars_per_message,content_filter_refusal,round_ended_idle,round_ended_timeout,language_strangeness,slang_emergence,neologism,shorthand_codes,language_repetition,english_ngram_surprisal,message_entropy,communication_open_coding,protocol_explanation,gzip_compression_ratio,dialog_retransmission

count_running_evals() {
  # Capital "Python" matches only the homebrew interpreter (one per eval), not
  # the lowercase "uv run ... python" wrapper, so each eval counts once. The
  # trailing "grep -v grep" also drops any monitor process whose command string
  # embeds this pattern (those lines contain "grep").
  ps -axo command 2>/dev/null | grep "Python -m schmidt evaluate veyru" | grep -v grep | wc -l | tr -d ' '
}

echo "=== random_letter eval started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/veyru/*/; do
  [ -f "$d/labels.json" ] && grep -q '"random_letter"' "$d/labels.json" || continue
  grep -q '"simulation_ended"' "$d/veyru.jsonl" 2>/dev/null || { echo "$(date) SKIP (no simulation_ended) $d" >> "$LOG"; continue; }
  [ -f "$d/veyru_report.json" ] && { echo "$(date) SKIP (already evaluated) $d" >> "$LOG"; continue; }
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 10; done
  echo "$(date) eval $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_random_letter_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) random_letter eval complete" >> "$LOG"
