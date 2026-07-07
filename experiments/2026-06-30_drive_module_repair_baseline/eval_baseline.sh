#!/bin/bash
# Drive-module-repair BASELINE evaluation — full comparable metric set.
#
# ##############################################################################
# # CRITICAL — NEVER EVALUATE A RUN BEFORE IT HAS EMITTED `simulation_ended`.   #
# # The ONLY completion signal is the `simulation_ended` event in the JSONL.    #
# # A run can have round 15's `round_result_recorded` written while its         #
# # postmortem + final events are still pending; evaluating then clips the run  #
# # and `round_success` reads short. This script gates STRICTLY on              #
# # `grep -q '"simulation_ended"'` and NEVER on a round count. Runs without it  #
# # are skipped (they get picked up on a later pass).                           #
# ##############################################################################
#
# Matches runs by the `baseline` label (path-scoped to drive_module_repair).
# protocol_explanation probes each
# agent under its OWN model (gpt/opus); every other LLM-judge metric uses the
# canonical haiku judge. Merges into each run's existing report; skips runs that
# already carry the full set (round_success present).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/drive_baseline_eval.log
CAP=10
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,round_ended_idle,round_ended_timeout,mean_chars_per_round,mean_chars_per_message,perplexity,content_filter_refusal,shorthand_codes,slang_emergence,neologism,language_strangeness,language_repetition,protocol_explanation

count_running_evals() {
  ps -axo command 2>/dev/null | grep "Python -m glossogen evaluate drive_module_repair" | grep -v grep | wc -l | tr -d ' '
}

echo "=== drive baseline eval started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/drive_module_repair/*/; do
  [ -f "$d/labels.json" ] && grep -q '"baseline"' "$d/labels.json" || continue
  # HARD GATE: simulation_ended only — never a round count.
  grep -q '"simulation_ended"' "$d/drive_module_repair.jsonl" 2>/dev/null \
    || { echo "$(date) SKIP (no simulation_ended yet) $d" >> "$LOG"; continue; }
  [ -f "$d/drive_module_repair_report.json" ] \
    && grep -q '"round_success"' "$d/drive_module_repair_report.json" \
    && { echo "$(date) SKIP (already evaluated) $d" >> "$LOG"; continue; }
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 10; done
  echo "$(date) eval $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate drive_module_repair \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_baseline_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) baseline eval complete" >> "$LOG"
