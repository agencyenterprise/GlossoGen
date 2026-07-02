#!/bin/bash
# spot_the_difference BASELINE evaluation — one pass over the cohort.
#
# ##############################################################################
# # CRITICAL — NEVER EVALUATE A RUN BEFORE IT HAS EMITTED `simulation_ended`.   #
# # The ONLY "scenario really finished" signal is the `simulation_ended` event  #
# # in the JSONL. Round 15's `round_result_recorded` is written BEFORE its      #
# # postmortem + final events, so evaluating on a round count clips the run and #
# # round_success reads short. This script gates STRICTLY on                    #
# # `grep -q '"simulation_ended"'` and NEVER on a round count; unfinished runs  #
# # are skipped and picked up on the next pass (see autoeval_loop.sh).          #
# ##############################################################################
#
# Matches runs by the ["baseline"] label (path-scoped to spot_the_difference).
# Every LLM-judge metric uses the canonical haiku judge. Two-team runs emit
# per-team measurements (round_success_team_a/_team_b, perplexity_team_a/_team_b,
# etc.). Merges into each run's existing report; skips runs already carrying
# round_success. protocol_explanation is intentionally omitted (probes under each
# agent's own model = extra cost); add it here if wanted.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/spot_baseline_eval.log
CAP=10
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,round_ended_idle,round_ended_timeout,mean_chars_per_round,mean_chars_per_message,perplexity,message_entropy,gzip_compression_ratio,english_ngram_surprisal,content_filter_refusal,shorthand_codes,slang_emergence,neologism,language_strangeness,language_repetition,communication_open_coding,dialog_retransmission

count_running_evals() {
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt evaluate spot_the_difference" \
    | grep -v grep | wc -l | tr -d ' '
}

echo "=== spot_the_difference baseline eval pass started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/spot_the_difference/*/; do
  [ -f "$d/labels.json" ] && grep -q '"baseline"' "$d/labels.json" || continue
  # HARD GATE: simulation_ended only — never a round count.
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
    > "$d/eval_baseline_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) baseline eval pass complete" >> "$LOG"
