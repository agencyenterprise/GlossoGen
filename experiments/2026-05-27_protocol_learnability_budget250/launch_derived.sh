#!/bin/bash
# Stage 2 of the protocol-learnability experiment. For every completed baseline
# (discovered via list_baselines.py) launch:
#   * 3x resume-at-round  (no config change, +10 rounds)            -> "expected"
#   * 3x replace-agent    (fresh same-model field_observer, +10 rounds,
#                          link history windowed to rounds 5-14,
#                          no historical postmortem, no new postmortem) -> "learned"
#
# Concurrency is capped PER PROVIDER at 6 (counting the detached `--resume`
# sims). Anthropic (sonnet + opus sources) and openai (gpt sources) advance in
# parallel. Each derived run is labelled right after the CLI returns its id.
#
# Run this ONLY after launch_baselines.sh has finished and all 30 baselines
# reached round 15.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
REPLACE_KNOBS_CANON="$SCRIPT_DIR/replace_knobs.json"
REPLACE_KNOBS_LEGACY="$SCRIPT_DIR/replace_knobs_legacy.json"
RESUME_KNOBS_LEGACY="$SCRIPT_DIR/resume_knobs_legacy.json"
LOG=/tmp/protolearn_derived.log
CAP=10
REPLICAS=3
ROUND_START=15
ROUNDS_AFTER=10
HISTORY_FROM=5   # round_start - 10 -> previous 10 rounds (5..14)

count_running_derived_for_provider() {
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run veyru" \
    | grep -- "--provider $1" \
    | grep -- "--resume" \
    | grep -v grep \
    | wc -l | tr -d ' '
}

wait_for_slot() {
  while [ "$(count_running_derived_for_provider "$1")" -ge "$CAP" ]; do sleep 30; done
}

count_existing_derived() {
  # How many runs already carry both the given phase label and src=<src_id>.
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

launch_resume() {
  local provider="$1" short="$2" src_dir="$3" src_id="$4" kind="$5"
  wait_for_slot "$provider"
  echo "$(date) [$short] resume src=$src_id kind=$kind" >> "$LOG"
  local out rid extra=""
  if [ "$kind" = "legacy" ]; then
    extra="--knobs $RESUME_KNOBS_LEGACY"
  fi
  # shellcheck disable=SC2086
  out=$(VIRTUAL_ENV= uv run --no-sync python -m glossogen resume-at-round veyru \
        --source-run-dir "$src_dir" --round-start "$ROUND_START" \
        --rounds-after-resume "$ROUNDS_AFTER" --runs-dir "./$RUNS_DIR" $extra 2>>"$LOG")
  rid=$(echo "$out" | grep -oE 'new_run_id=[^ ]+' | head -1 | cut -d= -f2)
  label_run "$rid" "[\"protocol_learnability\", \"phase=resume_expected\", \"budget=250\", \"model=${short}\", \"history=10\", \"src=${src_id}\"]"
  sleep 2
}

launch_replace() {
  local provider="$1" short="$2" model="$3" src_dir="$4" src_id="$5" kind="$6"
  wait_for_slot "$provider"
  echo "$(date) [$short] replace src=$src_id kind=$kind" >> "$LOG"
  local out rid knobs="$REPLACE_KNOBS_CANON"
  if [ "$kind" = "legacy" ]; then
    knobs="$REPLACE_KNOBS_LEGACY"
  fi
  out=$(VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
        --source-run-dir "$src_dir" --round-start "$ROUND_START" \
        --replaced-agent-id field_observer \
        --model "$model" --provider "$provider" \
        --rounds-after-swap "$ROUNDS_AFTER" --history-from-round "$HISTORY_FROM" \
        --knobs "$knobs" --runs-dir "./$RUNS_DIR" 2>>"$LOG")
  rid=$(echo "$out" | grep -oE 'new_run_id=[^ ]+' | head -1 | cut -d= -f2)
  label_run "$rid" "[\"protocol_learnability\", \"phase=replace_learned\", \"budget=250\", \"model=${short}\", \"history=10\", \"src=${src_id}\"]"
  sleep 2
}

# WORKLIST: lines of "short model provider kind run_dir" for each baseline.
WORKLIST=$(VIRTUAL_ENV= uv run --no-sync python "$SCRIPT_DIR/list_baselines.py" "$RUNS_DIR/veyru")

run_provider_queue() {
  local provider="$1"
  echo "$WORKLIST" | while read -r short model prov kind src_dir; do
    [ "$prov" = "$provider" ] || continue
    local src_id="veyru/$(basename "$src_dir")"
    local have_resume; have_resume=$(count_existing_derived "phase=resume_expected" "$src_id")
    local have_replace; have_replace=$(count_existing_derived "phase=replace_learned" "$src_id")
    local need_resume=$((REPLICAS - have_resume))
    local need_replace=$((REPLICAS - have_replace))
    echo "$(date) [$short] src=$src_id kind=$kind existing resume=$have_resume replace=$have_replace need resume=$need_resume replace=$need_replace" >> "$LOG"
    # Explicit > 0 guard: macOS BSD `seq 1 0` outputs "1\n0\n" (downward),
    # unlike GNU seq which is empty — without this guard, fully-derived sources
    # would silently get spurious extra launches.
    if [ "$need_resume" -gt 0 ]; then
      for _ in $(seq 1 "$need_resume"); do launch_resume "$provider" "$short" "$src_dir" "$src_id" "$kind"; done
    fi
    if [ "$need_replace" -gt 0 ]; then
      for _ in $(seq 1 "$need_replace"); do launch_replace "$provider" "$short" "$model" "$src_dir" "$src_id" "$kind"; done
    fi
  done
  echo "$(date) [$provider] derived queue complete" >> "$LOG"
}

n=$(echo "$WORKLIST" | grep -c .)
echo "=== protocol-learnability derived runs started $(date): $n baselines ===" >> "$LOG"
run_provider_queue anthropic &
run_provider_queue openai &
wait
echo "=== protocol-learnability derived runs complete $(date) ===" >> "$LOG"
