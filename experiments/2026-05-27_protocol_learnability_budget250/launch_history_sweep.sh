#!/bin/bash
# History-window sweep for the protocol-learnability "learned" condition.
#
# For every completed baseline (discovered via list_baselines.py) launch, for each
# history window h in {5, 1, 0}, 3x replace-agent with a fresh SAME-MODEL field_observer
# (+10 rounds, no postmortem) whose link history is windowed to the previous h rounds:
#   h=5 -> --history-from-round 10  (link rounds 10-14)
#   h=1 -> --history-from-round 14  (link round 14 only)
#   h=0 -> --history-from-round 15  (no prior link history at all)
# => 45 baselines x 3 windows x 3 replicas = 405 runs. Labelled phase=replace_learned with
# history=<h> so they are distinct from the existing history=10 learned runs.
#
# NEVER check out or modify src/schmidt/scenarios/veyru/prompts/stabilization_judge.jinja.
# veyru judges stabilization LIVE during the simulation, so the judge prompt must always be
# at HEAD when running sims — pinning/altering it corrupts every run.
#
# Concurrency is capped PER PROVIDER at 10 (provider == baseline's own model family, since
# the observer is same-model). anthropic (sonnet+opus baselines) and openai (gpt baselines)
# advance in parallel. Run only after the in-flight history=10 batch has finished.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
REPLACE_KNOBS_CANON="$SCRIPT_DIR/replace_knobs.json"
REPLACE_KNOBS_LEGACY="$SCRIPT_DIR/replace_knobs_legacy.json"
LOG=/tmp/protolearn_history_sweep.log
CAP=10
REPLICAS=3
ROUND_START=15
ROUNDS_AFTER=10
HISTORY_WINDOWS=(5 1 0)

count_running_for_provider() {
  ps -axo command 2>/dev/null \
    | grep "Python -m schmidt run veyru" \
    | grep -- "--provider $1" \
    | grep -- "--resume" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

wait_for_slot() {
  while [ "$(count_running_for_provider "$1")" -ge "$CAP" ]; do sleep 30; done
}

count_existing() {
  # replace_learned runs already carrying this src AND this exact history window.
  local src_id="$1" hist="$2" n=0
  for lf in "$RUNS_DIR"/veyru/*/labels.json; do
    [ -f "$lf" ] || continue
    if grep -q '"phase=replace_learned"' "$lf" 2>/dev/null \
       && grep -q "\"src=$src_id\"" "$lf" 2>/dev/null \
       && grep -q "\"history=$hist\"" "$lf" 2>/dev/null; then
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

launch_replace() {
  local provider="$1" short="$2" model="$3" src_dir="$4" src_id="$5" kind="$6" hist="$7"
  local from=$((ROUND_START - hist))
  wait_for_slot "$provider"
  echo "$(date) [$short] replace src=$src_id hist=$hist from=$from kind=$kind" >> "$LOG"
  local out rid knobs="$REPLACE_KNOBS_CANON"
  if [ "$kind" = "legacy" ]; then knobs="$REPLACE_KNOBS_LEGACY"; fi
  out=$(VIRTUAL_ENV= uv run --no-sync python -m schmidt replace-agent veyru \
        --source-run-dir "$src_dir" --round-start "$ROUND_START" \
        --replaced-agent-id field_observer \
        --model "$model" --provider "$provider" \
        --rounds-after-swap "$ROUNDS_AFTER" --history-from-round "$from" \
        --knobs "$knobs" --runs-dir "./$RUNS_DIR" 2>>"$LOG")
  rid=$(echo "$out" | grep -oE 'new_run_id=[^ ]+' | head -1 | cut -d= -f2)
  label_run "$rid" "[\"protocol_learnability\", \"phase=replace_learned\", \"budget=250\", \"model=${short}\", \"history=${hist}\", \"src=${src_id}\"]"
  sleep 2
}

WORKLIST=$(VIRTUAL_ENV= uv run --no-sync python "$SCRIPT_DIR/list_baselines.py" "$RUNS_DIR/veyru")

run_provider_queue() {
  local provider="$1"
  echo "$WORKLIST" | while read -r short model prov kind src_dir; do
    [ "$prov" = "$provider" ] || continue
    local src_id="veyru/$(basename "$src_dir")"
    for hist in "${HISTORY_WINDOWS[@]}"; do
      local have; have=$(count_existing "$src_id" "$hist")
      local need=$((REPLICAS - have))
      echo "$(date) [$short] src=$src_id hist=$hist have=$have need=$need" >> "$LOG"
      if [ "$need" -gt 0 ]; then
        for _ in $(seq 1 "$need"); do
          launch_replace "$provider" "$short" "$model" "$src_dir" "$src_id" "$kind" "$hist"
        done
      fi
    done
  done
  echo "$(date) [$provider] history-sweep queue complete" >> "$LOG"
}

# Guard: never run with a non-HEAD judge prompt.
JP="src/schmidt/scenarios/veyru/prompts/stabilization_judge.jinja"
if [ "$(git hash-object $JP)" != "$(git rev-parse HEAD:$JP)" ]; then
  echo "ABORT: $JP is not at HEAD. The judge prompt must never be pinned/edited for a run." >&2
  exit 1
fi

echo "=== protocol-learnability history sweep started $(date): $(echo "$WORKLIST" | grep -c .) baselines x {5,1,0} x $REPLICAS ===" >> "$LOG"
run_provider_queue anthropic &
run_provider_queue openai &
wait
echo "=== protocol-learnability history sweep complete $(date) ===" >> "$LOG"
