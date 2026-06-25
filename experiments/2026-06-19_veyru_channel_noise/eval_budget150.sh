#!/bin/bash
# Full-match evaluation for the budget=150 tier: runs the same 15-metric set the
# original 450/800 cohort carries, so the channel_noise cohort is uniform.
# Merges into each run's existing report (english_ngram_surprisal is already
# present on most; re-running it is idempotent). Cap 4 — sims are drained.
#
# protocol_explanation probes each agent under its OWN model (gpt/opus); every
# other LLM-judge metric uses the canonical haiku judge.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/veyru_noise_b150_eval.log
CAP=4
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,perplexity,mean_chars_per_round,mean_chars_per_message,content_filter_refusal,round_ended_idle,round_ended_timeout,language_strangeness,slang_emergence,neologism,shorthand_codes,language_repetition,english_ngram_surprisal,communication_open_coding,protocol_explanation

count_running_evals() {
  ps -axo command 2>/dev/null | grep "Python -m schmidt evaluate veyru" | grep -v grep | wc -l | tr -d ' '
}

echo "=== budget=150 full-match eval started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/veyru/*/; do
  [ -f "$d/labels.json" ] && grep -q '"channel_noise"' "$d/labels.json" && grep -q '"budget=150"' "$d/labels.json" || continue
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 10; done
  echo "$(date) eval $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_b150_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) budget=150 full-match eval complete" >> "$LOG"
