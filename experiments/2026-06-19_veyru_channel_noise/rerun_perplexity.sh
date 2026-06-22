#!/bin/bash
# Re-run the (now pristine-text) perplexity metric on every channel_noise run.
# Merges into each run's existing report, replacing only the perplexity
# measurement. Caps concurrency since each eval loads gpt2.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/veyru_noise_ppl_rerun.log
CAP=4
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic

count_running_evals() {
  ps -axo command 2>/dev/null | grep "Python -m schmidt evaluate veyru" | grep -v grep | wc -l | tr -d ' '
}

echo "=== perplexity rerun (pristine) started $(date) ===" >> "$LOG"
for d in "$RUNS_DIR"/veyru/*/; do
  [ -f "$d/labels.json" ] && grep -q '"channel_noise"' "$d/labels.json" || continue
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 10; done
  echo "$(date) $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate veyru \
    --run-dir "$d" --metrics perplexity \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    >> "$d/eval_ppl_pristine.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) perplexity rerun complete" >> "$LOG"
