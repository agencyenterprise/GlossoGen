#!/bin/bash
# Channel-noise baseline sweep (no swap):
#   noise   {0.2, 0.4, 0.6}
#   budget  {450, 800}  (round_time_budget_seconds)
#   model   {gpt-5.4/openai, claude-opus-4-7/anthropic}
#   5 replicas/cell  ->  3*2*2*5 = 60 runs (30 per provider).
#
# Fixed: 15 rounds, postmortem ON (link is noisy, postmortem stays clean),
# seed=42, easy_round_numbers=[], judge=haiku. Noise + budget are overridden
# inline on knobs_base.json per cell.
#
# Concurrency is capped PER PROVIDER at 10 via two parallel queues joined by
# `wait`, so the openai queue never blocks on anthropic capacity or vice versa.
# Each run is labelled (labels.json) as soon as its run dir appears.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/veyru_noise.log
CAP=10
REPLICAS=5

NOISE_LEVELS=(0.2 0.4 0.6)
# Budgets default to the original 450/800 tiers; override with the NOISE_BUDGETS
# env var (space-separated) to launch a different tier, e.g. NOISE_BUDGETS="150".
read -r -a BUDGETS <<< "${NOISE_BUDGETS:-450 800}"

# Per-provider cell lists: "short|model|provider"
declare -a OPENAI_MODELS=(
  "gpt54|gpt-5.4|openai"
)
declare -a ANTHROPIC_MODELS=(
  "opus47|claude-opus-4-7|anthropic"
)

count_running_for_provider() {
  # Capital "Python" matches the homebrew-framework sim process, never the
  # lowercase "python" uv wrapper nor the grep itself.
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run veyru" \
    | grep -- "--provider $1" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

launch_one() {
  local short="$1" model="$2" provider="$3" noise="$4" budget="$5" rep="$6"
  local labels="[\"channel_noise\", \"phase=baseline\", \"noise=${noise}\", \"budget=${budget}\", \"model=${short}\", \"rc=15\"]"
  local rep_log="/tmp/veyru_noise_${short}_n${noise}_b${budget}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [$short] launching noise=$noise budget=$budget rep $rep/$REPLICAS" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
      --model '$model' --provider '$provider' --runs-dir ./$RUNS_DIR \
      --config '$CONFIG' \
      channel_noise_level=$noise round_time_budget_seconds=$budget \
      >>'$rep_log' 2>&1" >/dev/null 2>&1 &
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
    echo "$(date) [$short] labelled $rid (noise=$noise budget=$budget)" >> "$LOG"
  else
    echo "$(date) [$short] WARN no run dir found in $rep_log (noise=$noise budget=$budget rep=$rep)" >> "$LOG"
  fi
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

process_queue() {
  local provider="$1"; shift
  local -a models=("$@")
  for cell in "${models[@]}"; do
    IFS='|' read -r short model prov <<< "$cell"
    for noise in "${NOISE_LEVELS[@]}"; do
      for budget in "${BUDGETS[@]}"; do
        for rep in $(seq 1 "$REPLICAS"); do
          while [ "$(count_running_for_provider "$provider")" -ge "$CAP" ]; do sleep 30; done
          launch_one "$short" "$model" "$prov" "$noise" "$budget" "$rep"
        done
      done
    done
  done
  echo "$(date) [$provider] queue complete" >> "$LOG"
}

echo "=== veyru channel-noise sweep started at $(date) ===" >> "$LOG"
process_queue openai "${OPENAI_MODELS[@]}" &
process_queue anthropic "${ANTHROPIC_MODELS[@]}" &
wait
echo "$(date): all launches complete" >> "$LOG"
