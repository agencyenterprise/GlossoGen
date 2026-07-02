#!/bin/bash
# Rolling auto-eval for the spot_the_difference baseline cohort.
#
# Repeatedly runs eval_baseline.sh (which STRICTLY gates each run on the
# `simulation_ended` event and skips already-evaluated runs) until all
# EXPECTED baseline runs are finished AND evaluated, or a deadline is hit.
# Safe to start right after launch: unfinished runs are simply skipped each pass
# and picked up once they emit `simulation_ended` (scenario complete). Each pass
# blocks on eval_baseline.sh's own `wait`, so passes never overlap.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
EXPECTED="${SPOT_BASELINE_EXPECTED:-30}"
LOG=/tmp/spot_baseline_autoeval.log
DEADLINE=$(( $(date +%s) + 4 * 3600 ))  # 4h ceiling

echo "=== spot baseline autoeval loop started $(date) (expecting $EXPECTED) ===" >> "$LOG"
while true; do
  bash "$SCRIPT_DIR/eval_baseline.sh"

  total=0; finished=0; evaluated=0
  for d in "$RUNS_DIR"/spot_the_difference/*/; do
    [ -f "$d/labels.json" ] && grep -q '"baseline"' "$d/labels.json" || continue
    total=$((total + 1))
    grep -q '"simulation_ended"' "$d/spot_the_difference.jsonl" 2>/dev/null && finished=$((finished + 1))
    [ -f "$d/spot_the_difference_report.json" ] \
      && grep -q 'round_success' "$d/spot_the_difference_report.json" \
      && evaluated=$((evaluated + 1))
  done
  echo "$(date) total=$total finished=$finished evaluated=$evaluated/$EXPECTED" >> "$LOG"

  [ "$evaluated" -ge "$EXPECTED" ] && { echo "$(date) ALL $EXPECTED EVALUATED" >> "$LOG"; break; }
  [ "$(date +%s)" -ge "$DEADLINE" ] \
    && { echo "$(date) AUTOEVAL TIMEOUT evaluated=$evaluated/$EXPECTED" >> "$LOG"; break; }
  sleep 150
done
