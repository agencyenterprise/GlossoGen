#!/bin/bash
# spot_the_difference FIXED-baseline re-run — remaining 14 runs.
#
# The round-4 scene bug (undecodable / non-judge-attributable case) is fixed in
# scene_generation.py, so this cohort is the corrected baseline. 5 replicas per
# model; the gpt-5.4 canary (1783022954) already ran and was audited clean, so
# this launches the other 14:
#   gpt-5.4/openai         x4   (reps 2-5; canary was rep 1)
#   claude-sonnet-4-6/anthropic x5
#   claude-opus-4-7/anthropic   x5
#
# Fixed knobs (knobs_base.json, identical to the original baseline): 15 rounds,
# seed=42 (FIXED across every run), two_teams=true, all_must_submit=true,
# round_time_budget_seconds=-1, max_round_duration_seconds=600,
# easy_round_numbers=[], haiku judge. Each run labelled ["baseline"] as soon as
# its run dir appears. Per-provider concurrency caps; anthropic queue runs
# sonnet+opus against one shared cap, openai queue runs gpt against its own.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/spot_rerun_remaining.log
CAP=10

count_running_provider() {
  # $1 is a model-name PREFIX: "claude-" matches both anthropic sims (shared
  # cap); "gpt-5.4" matches the openai sims. Capital "Python" matches the sim
  # interpreter, never the "uv run python" wrapper nor grep.
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run spot_the_difference --model $1" \
    | grep -v grep | wc -l | tr -d ' '
}

launch_one() {
  local short="$1" model="$2" provider="$3" rep="$4"
  local rep_log="/tmp/spot_rerun_${short}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [$short] launching rep $rep" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m glossogen run spot_the_difference \
      --model '$model' --provider '$provider' --runs-dir ./$RUNS_DIR --config '$CONFIG' \
      >>'$rep_log' 2>&1" >/dev/null 2>&1 &
  disown
  local rd=""
  for _ in $(seq 1 90); do
    rd=$(grep -oE "Run directory: [^ ]+" "$rep_log" 2>/dev/null | head -1 | sed 's|Run directory: ||' || true)
    [ -n "$rd" ] && break
    sleep 1
  done
  if [ -n "$rd" ]; then
    echo '["baseline"]' > "$RUNS_DIR/spot_the_difference/$(basename "$rd")/labels.json"
    echo "$(date) [$short] labelled $(basename "$rd")" >> "$LOG"
  else
    echo "$(date) [$short] WARN no run dir found in $rep_log (rep=$rep)" >> "$LOG"
  fi
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

process_anthropic() {
  local rep
  for rep in $(seq 1 5); do
    while [ "$(count_running_provider claude-)" -ge "$CAP" ]; do sleep 30; done
    launch_one sonnet46 claude-sonnet-4-6 anthropic "$rep"
  done
  for rep in $(seq 1 5); do
    while [ "$(count_running_provider claude-)" -ge "$CAP" ]; do sleep 30; done
    launch_one opus47 claude-opus-4-7 anthropic "$rep"
  done
  echo "$(date) [anthropic] queue complete" >> "$LOG"
}

process_openai() {
  local rep
  for rep in $(seq 2 5); do
    while [ "$(count_running_provider gpt-5.4)" -ge "$CAP" ]; do sleep 30; done
    launch_one gpt54 gpt-5.4 openai "$rep"
  done
  echo "$(date) [openai] queue complete" >> "$LOG"
}

echo "=== spot_the_difference baseline re-run (remaining 14) started $(date) ===" >> "$LOG"
process_anthropic &
process_openai &
wait
echo "$(date): all baseline re-run launches complete" >> "$LOG"
