#!/bin/bash
# Restart the runs killed after the 2026-07-01 21:14-21:16Z anthropic API
# incident (connection/timeout errors that exhausted the 3 retries). The 7
# degraded runs (3 sonnet + 4 opus) were deleted via the webserver DELETE API;
# this relaunches equivalent fresh runs labelled ["baseline"].
#
# Shares the anthropic 10-cap with the main launcher via the same
# count_running_provider gate (counts ALL "--model claude-" sims), so combined
# anthropic concurrency never exceeds 10. All 7 relaunches are anthropic.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/spot_baseline.log
CAP=10

count_running_provider() {
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt run spot_the_difference --model $1" \
    | grep -v grep | wc -l | tr -d ' '
}

launch_one() {
  local short="$1" model="$2" rep="$3"
  local rep_log="/tmp/spot_baseline_relaunch_${short}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [relaunch $short] launching rep $rep" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m schmidt run spot_the_difference \
      --model '$model' --provider anthropic --runs-dir ./$RUNS_DIR --config '$CONFIG' \
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
    echo "$(date) [relaunch $short] labelled $(basename "$rd")" >> "$LOG"
  else
    echo "$(date) [relaunch $short] WARN no run dir found in $rep_log" >> "$LOG"
  fi
  sleep 2
}

echo "=== relaunch of 3 sonnet + 4 opus started $(date) ===" >> "$LOG"
for rep in 1 2 3; do
  while [ "$(count_running_provider claude-)" -ge "$CAP" ]; do sleep 30; done
  launch_one sonnet46 claude-sonnet-4-6 "$rep"
done
for rep in 1 2 3 4; do
  while [ "$(count_running_provider claude-)" -ge "$CAP" ]; do sleep 30; done
  launch_one opus47 claude-opus-4-7 "$rep"
done
echo "$(date): relaunch complete" >> "$LOG"
