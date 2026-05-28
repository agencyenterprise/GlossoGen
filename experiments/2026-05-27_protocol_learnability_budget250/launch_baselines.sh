#!/bin/bash
# Stage 1 of the protocol-learnability experiment: 30 clean baseline runs at
# budget=250, 15 rounds, postmortem on, seed=42 — 10 each for sonnet, opus-4-7
# (both anthropic) and gpt-5.4 (openai).
#
# Concurrency is capped PER PROVIDER at 6: the anthropic queue interleaves the
# 10 sonnet + 10 opus runs under one shared 6-cap; the openai queue runs the 10
# gpt runs under its own 6-cap. Each run is labelled as soon as its dir appears.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_baseline.json"
LOG=/tmp/protolearn_baselines.log
CAP=6
PER_MODEL=10

# Each spec: short|model|provider, repeated PER_MODEL times within its provider queue.
declare -a ANTHROPIC_SPECS=(
  "sonnet|claude-sonnet-4-6|anthropic"
  "opus47|claude-opus-4-7|anthropic"
)
declare -a OPENAI_SPECS=(
  "gpt54|gpt-5.4|openai"
)

count_running_for_provider() {
  # Capital "Python" matches the homebrew-framework sim process, never the
  # lowercase "python" uv wrapper nor the grep itself.
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt run veyru" \
    | grep -- "--provider $1" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

launch_one() {
  local short="$1" model="$2" provider="$3" rep="$4"
  local labels="[\"protocol_learnability\", \"phase=baseline\", \"budget=250\", \"model=${short}\", \"rc=15\"]"
  local rep_log="/tmp/protolearn_baseline_${short}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [$short] launching baseline rep $rep/$PER_MODEL" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru \
      --model '$model' --provider '$provider' --runs-dir ./$RUNS_DIR \
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
    echo "$(date) [$short] labelled $rid" >> "$LOG"
  else
    echo "$(date) [$short] WARN no run dir found in $rep_log for rep $rep" >> "$LOG"
  fi
  sleep 3
}

run_provider_queue() {
  local provider="$1"; shift
  local -a specs=("$@")
  for rep in $(seq 1 "$PER_MODEL"); do
    for spec in "${specs[@]}"; do
      IFS='|' read -r short model prov <<< "$spec"
      while [ "$(count_running_for_provider "$provider")" -ge "$CAP" ]; do sleep 30; done
      launch_one "$short" "$model" "$prov" "$rep"
    done
  done
  echo "$(date) [$provider] queue complete" >> "$LOG"
}

echo "=== protocol-learnability baselines started $(date) ===" >> "$LOG"
run_provider_queue anthropic "${ANTHROPIC_SPECS[@]}" &
run_provider_queue openai "${OPENAI_SPECS[@]}" &
wait
echo "=== protocol-learnability baselines complete $(date) ===" >> "$LOG"
