#!/bin/bash
# Veyru random-letter noise cohort — re-execution of the 2026-06-19 channel_noise
# grid with the SAME knobs and models, but noise_replacement_mode=random_letter
# (substitution channel: dropped chars become a different random letter, no
# marker) instead of the default mask (dropped chars become "_", visible erasure).
#
#   noise   {0.2, 0.4, 0.6}
#   budget  {150, 450, 800}  (round_time_budget_seconds)
#   model   {gpt-5.4/openai, claude-opus-4-7/anthropic}
#   5 replicas/cell  ->  3*3*2*5 = 90 runs (45 per provider).
#
# Fixed knobs come from knobs_base.json (identical to the channel_noise base plus
# noise_replacement_mode=random_letter): 15 rounds, postmortem ON, seed=42,
# easy_round_numbers=[], max_round_duration_seconds=600,
# postmortem_duration_seconds=240, judge=haiku. Noise + budget are overridden
# inline per cell (noise_replacement_mode is also passed inline so it shows up in
# each run's config-override log).
#
# Concurrency is capped PER MODEL at 10 via two parallel queues joined by `wait`,
# so the openai queue never blocks on anthropic capacity or vice versa. Each run
# is labelled (labels.json) as soon as its run dir appears.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/veyru_random_letter.log
CAP=10
REPLICAS=5

NOISE_LEVELS=(0.2 0.4 0.6)
# Defaults to all three budget tiers (the full channel_noise grid). Override with
# the NOISE_BUDGETS env var (space-separated) to run a subset, e.g.
# NOISE_BUDGETS="800".
read -r -a BUDGETS <<< "${NOISE_BUDGETS:-150 450 800}"

count_running_for_model() {
  # Capital "Python" matches the homebrew-framework sim process, never the
  # lowercase "python" uv wrapper nor the grep itself. Anchored on the exact
  # model so the two queues never count each other's sims.
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run veyru --model $1" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

launch_one() {
  local short="$1" model="$2" provider="$3" noise="$4" budget="$5" rep="$6"
  local labels="[\"random_letter\", \"phase=baseline\", \"noise=${noise}\", \"budget=${budget}\", \"model=${short}\", \"rc=15\"]"
  local rep_log="/tmp/veyru_random_letter_${short}_n${noise}_b${budget}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [$short] launching noise=$noise budget=$budget rep $rep/$REPLICAS" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
      --model '$model' --provider '$provider' --runs-dir ./$RUNS_DIR \
      --config '$CONFIG' \
      channel_noise_level=$noise round_time_budget_seconds=$budget \
      noise_replacement_mode=random_letter \
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
  local short="$1" model="$2" provider="$3"
  for noise in "${NOISE_LEVELS[@]}"; do
    for budget in "${BUDGETS[@]}"; do
      for rep in $(seq 1 "$REPLICAS"); do
        while [ "$(count_running_for_model "$model")" -ge "$CAP" ]; do sleep 30; done
        launch_one "$short" "$model" "$provider" "$noise" "$budget" "$rep"
      done
    done
  done
  echo "$(date) [$short] queue complete" >> "$LOG"
}

echo "=== veyru random-letter cohort started at $(date) ===" >> "$LOG"
process_queue gpt54 gpt-5.4 openai &
process_queue opus47 claude-opus-4-7 anthropic &
wait
echo "$(date): all launches complete" >> "$LOG"
