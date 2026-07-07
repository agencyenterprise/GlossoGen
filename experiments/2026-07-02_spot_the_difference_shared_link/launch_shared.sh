#!/bin/bash
# spot_the_difference SHARED-LINK cohort — 4 runs (2 gpt-5.4 + 2 sonnet-4.6).
#
# Same knobs as the 2026-07-01 baseline (knobs_base.json here mirrors it): 15 rounds,
# seed=42 (FIXED — all reps face the byte-identical scenes), two_teams=true,
# all_must_submit=true, round_time_budget_seconds=-1 (no cap),
# max_round_duration_seconds=600, easy_round_numbers=[], haiku judge — PLUS
# shared_link=true: both teams share ONE link channel (all four viewers) while their
# postmortem channels stay per-team and private. Each run is labelled ["shared_link"].
#
# Only 4 runs (2 per provider), so no concurrency cap is needed — all launch at once.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/spot_shared_link.log

launch_one() {
  local short="$1" model="$2" provider="$3" rep="$4"
  local rep_log="/tmp/spot_shared_${short}_rep${rep}.log"
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
    echo '["shared_link"]' > "$RUNS_DIR/spot_the_difference/$(basename "$rd")/labels.json"
    echo "$(date) [$short] labelled $(basename "$rd")" >> "$LOG"
  else
    echo "$(date) [$short] WARN no run dir found in $rep_log (rep=$rep)" >> "$LOG"
  fi
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

echo "=== spot shared_link cohort started $(date) ===" >> "$LOG"
launch_one gpt54 gpt-5.4 openai 1
launch_one gpt54 gpt-5.4 openai 2
launch_one sonnet46 claude-sonnet-4-6 anthropic 1
launch_one sonnet46 claude-sonnet-4-6 anthropic 2
echo "$(date): all shared_link launches complete" >> "$LOG"
