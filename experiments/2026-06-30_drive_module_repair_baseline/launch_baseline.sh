#!/bin/bash
# Drive-module-repair BASELINE cohort.
#
#   budgets   veyru-matched tiers, set via DRIVE_BASELINE_BUDGETS (space-separated),
#             e.g. DRIVE_BASELINE_BUDGETS="200 300 450 600 900"
#   models    gpt-5.4/openai, claude-opus-4-7/anthropic
#   3 replicas per (model, budget) cell.
#
# Fixed knobs (knobs_base.json): 15 rounds, postmortem ON, seed=42,
# easy_round_numbers=[] (NO warmup rounds — matches veyru), max_round_duration_seconds=900
# (generous so the char BUDGET is the binding constraint, not the wall-clock), judge=haiku.
# Budget is overridden inline per cell. seed=42 is fixed across every run so the
# per-round input (faults/units/symptoms/procedures) is byte-identical across
# budgets and models — apples-to-apples.
#
# Concurrency capped PER MODEL at 10 via two parallel queues joined by `wait`.
# REUSE-AWARE: counts existing baseline-labelled runs per (model,budget) and
# only launches the remainder to reach 3 — so pre-existing reps (e.g. relabelled
# clean-sweep gpt-5.4 runs at the same budget/seed) are not re-run. Each new run is
# labelled (labels.json) as soon as its run dir appears.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/drive_baseline.log
CAP=10
REPLICAS=3
read -r -a BUDGETS <<< "${DRIVE_BASELINE_BUDGETS:?set DRIVE_BASELINE_BUDGETS, e.g. \"200 300 450 600 900\"}"

count_running_for_model() {
  # Capital "Python" matches the homebrew sim interpreter, never the lowercase
  # "uv run python" wrapper nor the grep itself. Anchored on the exact model so
  # the two queues never count each other's sims.
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt run drive_module_repair --model $1" \
    | grep -v grep | wc -l | tr -d ' '
}

count_existing_cell() {
  # Count runs already carrying ALL of {baseline, budget=<b>, model=<short>}.
  # Parses labels.json as JSON (set membership) — never substring-matches.
  python3 - "$1" "$2" <<'PY'
import json, sys, glob
short, budget = sys.argv[1], sys.argv[2]
need = {"baseline", f"budget={budget}", f"model={short}"}
n = 0
for lf in glob.glob("runs/drive_module_repair/*/labels.json"):
    try:
        labels = json.load(open(lf))
    except Exception:
        continue
    if isinstance(labels, list) and need.issubset(set(labels)):
        n += 1
print(n)
PY
}

launch_one() {
  local short="$1" model="$2" provider="$3" budget="$4" rep="$5"
  local rep_log="/tmp/drive_baseline_${short}_b${budget}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [$short] launching budget=$budget rep=$rep" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m schmidt run drive_module_repair \
      --model '$model' --provider '$provider' --runs-dir ./$RUNS_DIR --config '$CONFIG' \
      round_time_budget_seconds=$budget \
      >>'$rep_log' 2>&1" >/dev/null 2>&1 &
  disown
  local rd=""
  for _ in $(seq 1 90); do
    rd=$(grep -oE "Run directory: [^ ]+" "$rep_log" 2>/dev/null | head -1 | sed 's|Run directory: ||' || true)
    [ -n "$rd" ] && break
    sleep 1
  done
  if [ -n "$rd" ]; then
    echo "[\"baseline\", \"budget=${budget}\", \"model=${short}\", \"rc=15\"]" \
      > "$RUNS_DIR/drive_module_repair/$(basename "$rd")/labels.json"
    echo "$(date) [$short] labelled $(basename "$rd") budget=$budget" >> "$LOG"
  else
    echo "$(date) [$short] WARN no run dir (budget=$budget rep=$rep)" >> "$LOG"
  fi
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

process_queue() {
  local short="$1" model="$2" provider="$3"
  for budget in "${BUDGETS[@]}"; do
    local have need rep
    have=$(count_existing_cell "$short" "$budget")
    need=$((REPLICAS - have))
    echo "$(date) [$short] budget=$budget have=$have need=$need" >> "$LOG"
    rep=$((have + 1))
    while [ "$need" -gt 0 ]; do
      while [ "$(count_running_for_model "$model")" -ge "$CAP" ]; do sleep 30; done
      launch_one "$short" "$model" "$provider" "$budget" "$rep"
      rep=$((rep + 1)); need=$((need - 1))
    done
  done
  echo "$(date) [$short] queue complete" >> "$LOG"
}

echo "=== drive baseline started $(date) budgets=${BUDGETS[*]} ===" >> "$LOG"
process_queue gpt54 gpt-5.4 openai &
process_queue opus47 claude-opus-4-7 anthropic &
wait
echo "$(date): all baseline launches complete" >> "$LOG"
