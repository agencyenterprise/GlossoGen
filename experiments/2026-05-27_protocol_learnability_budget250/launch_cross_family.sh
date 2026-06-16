#!/bin/bash
# Stage 4 of the protocol-learnability experiment. For every completed baseline
# (discovered via list_baselines.py) launch:
#   * 3x replace-agent with a CROSS-FAMILY fresh field_observer (+10 rounds,
#     link history windowed to rounds 5-14, no historical postmortem, no new
#     postmortem) -> "replace_cross_family"
#
# Swap rules (baseline_model -> observer_family):
#   sonnet -> gpt-5.4   (cross-family read of sonnet's protocol by openai)
#   opus47 -> gpt-5.4   (cross-family read of opus's protocol by openai)
#   gpt54  -> opus47    (cross-family read of gpt's protocol by anthropic)
#
# Concurrency is capped PER PROVIDER at 6, where provider is the OBSERVER
# family (the one schmidt run will hit) — not the baseline's family. With the
# rules above:
#   anthropic queue (opus47 observer) handles 15 gpt54 sources    -> 45 runs
#   openai    queue (gpt-5.4 observer) handles 30 sonnet+opus sources -> 90 runs
# Each derived run is labelled right after the CLI returns its id with
# `model=<baseline_short>` and `observer=<observer_short>` so the streamlit tab
# can identify both ends of the swap.
#
# NEVER check out or modify src/schmidt/scenarios/veyru/prompts/stabilization_judge.jinja
# to an older version. veyru judges stabilization LIVE during the simulation, so the judge
# prompt must always be at HEAD when running sims — pinning/altering it silently changes
# round outcomes and corrupts every run launched against it.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
REPLACE_KNOBS_CANON="$SCRIPT_DIR/replace_knobs.json"
REPLACE_KNOBS_LEGACY="$SCRIPT_DIR/replace_knobs_legacy.json"
LOG=/tmp/protolearn_cross_family.log
CAP=10
REPLICAS=3
ROUND_START=15
ROUNDS_AFTER=10
HISTORY_FROM=5
PHASE_LABEL="phase=replace_cross_family"

# Cross-family swap table. Each row: <baseline_short> <observer_short> <observer_model> <observer_provider>
SWAP_OBSERVER_FOR_SONNET=("gpt54" "gpt-5.4" "openai")
SWAP_OBSERVER_FOR_OPUS47=("gpt54" "gpt-5.4" "openai")
SWAP_OBSERVER_FOR_GPT54=("opus47" "claude-opus-4-7" "anthropic")

observer_for() {
  case "$1" in
    sonnet) echo "${SWAP_OBSERVER_FOR_SONNET[@]}" ;;
    opus47) echo "${SWAP_OBSERVER_FOR_OPUS47[@]}" ;;
    gpt54)  echo "${SWAP_OBSERVER_FOR_GPT54[@]}" ;;
    *)      echo "" ;;
  esac
}

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

count_existing_cross_family() {
  # How many runs already carry phase=replace_cross_family AND src=<src_id> AND observer=<observer_short>.
  local src_id="$1" observer_short="$2" n=0
  for lf in "$RUNS_DIR"/veyru/*/labels.json; do
    [ -f "$lf" ] || continue
    if grep -q "\"$PHASE_LABEL\"" "$lf" 2>/dev/null \
       && grep -q "\"src=$src_id\"" "$lf" 2>/dev/null \
       && grep -q "\"observer=$observer_short\"" "$lf" 2>/dev/null; then
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

launch_cross_family() {
  local baseline_short="$1" observer_short="$2" observer_model="$3" observer_provider="$4"
  local src_dir="$5" src_id="$6" kind="$7"
  wait_for_slot "$observer_provider"
  echo "$(date) [$baseline_short->$observer_short] cross-family src=$src_id kind=$kind" >> "$LOG"
  local out rid knobs="$REPLACE_KNOBS_CANON"
  if [ "$kind" = "legacy" ]; then
    knobs="$REPLACE_KNOBS_LEGACY"
  fi
  out=$(VIRTUAL_ENV= uv run --no-sync python -m schmidt replace-agent veyru \
        --source-run-dir "$src_dir" --round-start "$ROUND_START" \
        --replaced-agent-id field_observer \
        --model "$observer_model" --provider "$observer_provider" \
        --rounds-after-swap "$ROUNDS_AFTER" --history-from-round "$HISTORY_FROM" \
        --knobs "$knobs" --runs-dir "./$RUNS_DIR" 2>>"$LOG")
  rid=$(echo "$out" | grep -oE 'new_run_id=[^ ]+' | head -1 | cut -d= -f2)
  label_run "$rid" "[\"protocol_learnability\", \"$PHASE_LABEL\", \"budget=250\", \"model=${baseline_short}\", \"observer=${observer_short}\", \"history=10\", \"src=${src_id}\"]"
  sleep 2
}

WORKLIST=$(VIRTUAL_ENV= uv run --no-sync python "$SCRIPT_DIR/list_baselines.py" "$RUNS_DIR/veyru")

run_provider_queue() {
  # Each queue is keyed by the OBSERVER provider. We iterate every baseline and
  # only act on those whose swap-table observer_provider matches this queue.
  local observer_provider="$1"
  echo "$WORKLIST" | while read -r baseline_short _baseline_model _baseline_provider kind src_dir; do
    read -r observer_short observer_model swap_provider <<< "$(observer_for "$baseline_short")"
    if [ -z "$observer_short" ]; then
      echo "$(date) [skip $baseline_short] no cross-family swap defined" >> "$LOG"
      continue
    fi
    [ "$swap_provider" = "$observer_provider" ] || continue
    local src_id="veyru/$(basename "$src_dir")"
    local have; have=$(count_existing_cross_family "$src_id" "$observer_short")
    local need=$((REPLICAS - have))
    echo "$(date) [$baseline_short->$observer_short] src=$src_id kind=$kind existing=$have need=$need" >> "$LOG"
    if [ "$need" -gt 0 ]; then
      for _ in $(seq 1 "$need"); do
        launch_cross_family "$baseline_short" "$observer_short" "$observer_model" "$observer_provider" "$src_dir" "$src_id" "$kind"
      done
    fi
  done
  echo "$(date) [$observer_provider] cross_family queue complete" >> "$LOG"
}

n=$(echo "$WORKLIST" | grep -c .)
echo "=== cross_family started $(date): $n baselines ===" >> "$LOG"
run_provider_queue anthropic &
run_provider_queue openai &
wait
echo "=== cross_family complete $(date) ===" >> "$LOG"
