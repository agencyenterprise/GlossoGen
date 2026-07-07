#!/bin/bash
# Rolling evaluator for the channel-noise sweep. Repeatedly scans for completed
# channel_noise runs (those that have emitted simulation_ended) that lack an
# evaluation report, and
# evaluates each with the deterministic + language-emergence metric set under
# the canonical haiku judge. Caps concurrency to avoid contending with the live
# opus sims on the anthropic rate limit. Exits once the orchestrator has drained
# AND every completed run has a report.
#
# protocol_explanation (probes agents under their own opus/gpt model) and the
# communication ontology pipeline are intentionally NOT run here — they run
# after full drain.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/veyru_noise_eval.log
EVAL_CAP=1
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
METRICS=round_success,perplexity,mean_chars_per_round,mean_chars_per_message,content_filter_refusal,round_ended_idle,round_ended_timeout,language_strangeness,slang_emergence,neologism,shorthand_codes

count_running_evals() {
  ps -axo command 2>/dev/null | grep "Python -m glossogen evaluate veyru" | grep -v grep | wc -l | tr -d ' '
}

is_channel_noise_run() {
  local d="$1"
  [ -f "$d/labels.json" ] && grep -q '"channel_noise"' "$d/labels.json"
}

is_complete() {
  # A run is only safe to evaluate once it has emitted simulation_ended.
  # Do NOT use a round_advanced count: round_advanced to N fires when round N
  # STARTS, but round N's RoundResultRecorded isn't written until round N ENDS,
  # so a count>=round_count gate evaluates mid-final-round and drops the last
  # round's results (round_success then reads N-1 rounds).
  local d="$1"
  grep -q '"simulation_ended"' "$d/veyru.jsonl" 2>/dev/null
}

has_report() {
  [ -f "$1/veyru_report.json" ]
}

evaluate_one() {
  local d="$1" rid; rid="veyru/$(basename "$d")"
  echo "$(date) evaluating $rid" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate veyru \
    --run-dir "$d" --metrics "$METRICS" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    > "$d/eval_stdout.log" 2>&1
  echo "$(date) done $rid (exit $?)" >> "$LOG"
}

echo "=== rolling eval started at $(date) ===" >> "$LOG"
while true; do
  pending=0
  for d in "$RUNS_DIR"/veyru/*/; do
    is_channel_noise_run "$d" || continue
    has_report "$d" && continue
    is_complete "$d" || { pending=$((pending+1)); continue; }
    while [ "$(count_running_evals)" -ge "$EVAL_CAP" ]; do sleep 15; done
    evaluate_one "$d" &
    sleep 1
  done
  # stop condition: orchestrator drained and nothing left pending/running
  if grep -q "all launches complete" /tmp/veyru_noise.log 2>/dev/null; then
    sims=$(ps -axo command | grep "Python -m glossogen run veyru" | grep -v grep | wc -l | tr -d ' ')
    evals=$(count_running_evals)
    if [ "$sims" -eq 0 ] && [ "$evals" -eq 0 ] && [ "$pending" -eq 0 ]; then
      wait
      echo "$(date) rolling eval complete" >> "$LOG"
      break
    fi
  fi
  sleep 30
done
