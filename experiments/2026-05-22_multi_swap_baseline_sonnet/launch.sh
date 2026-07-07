#!/bin/bash
# Multi-swap baseline (sonnet) — 2026-05-22
# 10 fully independent veyru runs at budget=450, phases=A10-B10-C10-D10.
# Single-provider sonnet workload: cap=6 concurrent.
#
# Each `glossogen run` is a foreground process (no resume / no detached spawn),
# so we background each invocation with nohup and poll its per-replica stdout
# log for the "Run directory: ..." line (emitted seconds after launch) so we
# can label the new run dir.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

LOG=/tmp/multi_swap_baseline_sonnet.log
CONFIG="experiments/2026-05-22_multi_swap_baseline_sonnet/knobs.json"
LABELS_JSON='["multi_swap_baseline", "budget=450", "phases=A10-B10-C10-D10", "history=10"]'
# Replicas 1-2 were launched manually (veyru/1779473397, veyru/1779473436).
# Launcher fires replicas 3-10 here.
START_REP=3
TOTAL_RUNS=10

count_running_sonnet() {
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run veyru --model claude-sonnet-4-6" \
    | grep -v grep \
    | wc -l \
    | tr -d ' '
}

echo "=== Multi-swap baseline launcher started $(date) ===" >> "$LOG"
for rep in $(seq "$START_REP" "$TOTAL_RUNS"); do
  while [ "$(count_running_sonnet)" -ge 6 ]; do
    sleep 30
  done

  rep_log="/tmp/multi_swap_baseline_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) launching replica $rep/$TOTAL_RUNS" >> "$LOG"

  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
      --model claude-sonnet-4-6 --provider anthropic \
      --runs-dir ./runs \
      --config '$CONFIG' >>'$rep_log' 2>&1" >/dev/null 2>&1 &
  disown

  new_run_dir=""
  for _ in $(seq 1 60); do
    new_run_dir=$(grep -oE "Run directory: [^ ]+" "$rep_log" 2>/dev/null | head -1 | sed 's|Run directory: ||' || true)
    if [ -n "$new_run_dir" ]; then
      break
    fi
    sleep 1
  done

  if [ -n "$new_run_dir" ]; then
    new_run_id="veyru/$(basename "$new_run_dir")"
    echo "$LABELS_JSON" > "runs/$new_run_id/labels.json"
    echo "$(date) labeled $new_run_id with $LABELS_JSON" >> "$LOG"
  else
    echo "$(date) WARN no Run directory found in $rep_log for replica $rep" >> "$LOG"
  fi
  sleep 3
done
echo "=== Multi-swap baseline launcher complete $(date) ===" >> "$LOG"
