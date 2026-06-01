#!/bin/bash
# Stage 3 of the protocol-learnability experiment. Adds a third condition for
# every completed baseline (discovered via list_baselines.py):
#   * 3x resume-at-round with postmortem disabled going forward (+10 rounds)
#     -> "expected_no_postmortem"
#
# Isolates the "no-postmortem" effect from the "fresh-observer" effect so that
# Δ_observer = learned - expected_no_postmortem  (fresh observer alone)
# Δ_postmortem = expected_no_postmortem - expected  (no postmortem alone)
#
# Concurrency: 6 per provider, sonnet+opus (anthropic) and gpt-5.4 (openai)
# advance in parallel. Each run is labelled right after the CLI returns its id.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
RESUME_KNOBS_CANON="$SCRIPT_DIR/resume_no_postmortem_knobs.json"
RESUME_KNOBS_LEGACY="$SCRIPT_DIR/resume_no_postmortem_knobs_legacy.json"
LOG=/tmp/protolearn_resume_no_postmortem.log
CAP=6
REPLICAS=3
ROUND_START=15
ROUNDS_AFTER=10
PHASE_LABEL="phase=resume_expected_no_postmortem"

count_running_derived_for_provider() {
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt run veyru" \
    | grep -- "--provider $1" \
    | grep -- "--resume" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

wait_for_slot() {
  while [ "$(count_running_derived_for_provider "$1")" -ge "$CAP" ]; do sleep 30; done
}

count_existing_derived() {
  local phase="$1" src_id="$2" n=0
  for lf in "$RUNS_DIR"/veyru/*/labels.json; do
    [ -f "$lf" ] || continue
    if grep -q "\"$phase\"" "$lf" 2>/dev/null && grep -q "\"src=$src_id\"" "$lf" 2>/dev/null; then
      n=$((n + 1))
    fi
  done
  echo "$n"
}

label_run() {
  local rid="$1" labels="$2"
  if [ -n "$rid" ] && [ -d "$RUNS_DIR/$rid" ]; then
    echo "$labels" > "$RUNS_DIR/$rid/labels.json"
    echo "$(date) labelled $rid $labels" >> "$LOG"
  else
    echo "$(date) WARN could not label rid='$rid'" >> "$LOG"
  fi
}

launch_resume_no_pm() {
  local provider="$1" short="$2" src_dir="$3" src_id="$4" kind="$5"
  wait_for_slot "$provider"
  echo "$(date) [$short] resume_no_pm src=$src_id kind=$kind" >> "$LOG"
  local out rid knobs="$RESUME_KNOBS_CANON"
  if [ "$kind" = "legacy" ]; then
    knobs="$RESUME_KNOBS_LEGACY"
  fi
  out=$(VIRTUAL_ENV= uv run --no-sync python -m schmidt resume-at-round veyru \
        --source-run-dir "$src_dir" --round-start "$ROUND_START" \
        --rounds-after-resume "$ROUNDS_AFTER" --runs-dir "./$RUNS_DIR" \
        --knobs "$knobs" 2>>"$LOG")
  rid=$(echo "$out" | grep -oE 'new_run_id=[^ ]+' | head -1 | cut -d= -f2)
  label_run "$rid" "[\"protocol_learnability\", \"$PHASE_LABEL\", \"budget=250\", \"model=${short}\", \"history=10\", \"src=${src_id}\"]"
  sleep 2
}

WORKLIST=$(VIRTUAL_ENV= uv run --no-sync python "$SCRIPT_DIR/list_baselines.py" "$RUNS_DIR/veyru")

run_provider_queue() {
  local provider="$1"
  echo "$WORKLIST" | while read -r short model prov kind src_dir; do
    [ "$prov" = "$provider" ] || continue
    local src_id="veyru/$(basename "$src_dir")"
    local have; have=$(count_existing_derived "$PHASE_LABEL" "$src_id")
    local need=$((REPLICAS - have))
    echo "$(date) [$short] src=$src_id kind=$kind existing=$have need=$need" >> "$LOG"
    if [ "$need" -gt 0 ]; then
      for _ in $(seq 1 "$need"); do launch_resume_no_pm "$provider" "$short" "$src_dir" "$src_id" "$kind"; done
    fi
  done
  echo "$(date) [$provider] resume_no_postmortem queue complete" >> "$LOG"
}

n=$(echo "$WORKLIST" | grep -c .)
echo "=== resume_no_postmortem started $(date): $n baselines ===" >> "$LOG"
run_provider_queue anthropic &
run_provider_queue openai &
wait
echo "=== resume_no_postmortem complete $(date) ===" >> "$LOG"
