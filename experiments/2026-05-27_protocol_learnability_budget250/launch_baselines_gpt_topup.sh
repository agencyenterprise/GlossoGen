#!/bin/bash
# Top-up: launch 5 additional canon-config gpt-5.4 baselines so the cohort
# (existing 10 fresh gpt + this 5 top-up) reaches parity with the bumped
# anthropic side (10 fresh + 5 pre-existing reused per model).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_baseline.json"
LOG=/tmp/protolearn_baselines_gpt_topup.log
CAP=6
PER_MODEL=5
SHORT=gpt54
MODEL=gpt-5.4
PROVIDER=openai

count_running_for_provider() {
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run veyru" \
    | grep -- "--provider $1" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

launch_one() {
  local rep="$1"
  local labels="[\"protocol_learnability\", \"phase=baseline\", \"budget=250\", \"model=${SHORT}\", \"rc=15\"]"
  local rep_log="/tmp/protolearn_baseline_${SHORT}_topup_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [${SHORT}] launching topup rep $rep/$PER_MODEL" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
      --model '$MODEL' --provider '$PROVIDER' --runs-dir ./$RUNS_DIR \
      --config '$CONFIG' >>'$rep_log' 2>&1" >/dev/null 2>&1 &
  disown
  local new_run_dir=""
  for _ in $(seq 1 90); do
    new_run_dir=$(grep -oE "Run directory: [^ ]+" "$rep_log" 2>/dev/null | head -1 | sed 's|Run directory: ||' || true)
    [ -n "$new_run_dir" ] && break
    sleep 1
  done
  if [ -n "$new_run_dir" ]; then
    local rid; rid="veyru/$(basename "$new_run_dir")"
    echo "$labels" > "$RUNS_DIR/$rid/labels.json"
    echo "$(date) [${SHORT}] labelled $rid" >> "$LOG"
  else
    echo "$(date) [${SHORT}] WARN no run dir found in $rep_log for rep $rep" >> "$LOG"
  fi
  sleep 3
}

echo "=== gpt5x topup started $(date) ===" >> "$LOG"
for rep in $(seq 1 "$PER_MODEL"); do
  while [ "$(count_running_for_provider $PROVIDER)" -ge "$CAP" ]; do sleep 30; done
  launch_one "$rep"
done
echo "$(date) [${SHORT}] topup queue complete" >> "$LOG"
