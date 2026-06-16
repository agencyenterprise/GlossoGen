#!/bin/bash
# Llama field-observer condition for the protocol-learnability experiment.
#
# For every completed baseline (discovered via list_baselines.py) launch, for each history
# window h in {0, 1, 5, 10}, 3x replace-agent that swaps field_observer for a fresh
# Llama-3.3-70B observer (self-hosted via Modal), +10 rounds, no postmortem, with the link
# history windowed to the previous h rounds:
#   h=10 -> --history-from-round 5   (link rounds 5-14)
#   h=5  -> --history-from-round 10  (link rounds 10-14)
#   h=1  -> --history-from-round 14  (link round 14 only)
#   h=0  -> --history-from-round 15  (no prior link history at all)
# => 45 baselines x 4 windows x 3 replicas = 540 runs. Labelled phase=replace_llama,
# observer=llama, history=<h> so they are distinct from the same-model/cross-family runs.
#
# The stabilization_engineer keeps its original baseline model (replace-agent pins every
# non-replaced agent to its source registration). So each run hits the Llama endpoint for
# the observer AND anthropic/openai for the engineer.
#
# Concurrency is capped PER ENGINEER FAMILY (the baseline's own family, which is the agent
# that hits anthropic/openai) at 15 — NOT on the Llama endpoint, which serves all observers
# from 2 warm replicas (64 request slots) and is never the bottleneck. Two queues advance in
# parallel:
#   anthropic-engine queue: sonnet + opus47 baselines
#   openai-engine queue:    gpt54 baselines
# Each queue counts only the runs IT launched that are still live (tracked by run id), since
# every subprocess shares --provider self-hosted and cannot be told apart by ps.
#
# NEVER check out or modify src/schmidt/scenarios/veyru/prompts/stabilization_judge.jinja.
# veyru judges stabilization LIVE during the simulation, so the judge prompt must always be
# at HEAD when running sims -- pinning/altering it corrupts every run.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
REPLACE_KNOBS_CANON="$SCRIPT_DIR/replace_knobs.json"
REPLACE_KNOBS_LEGACY="$SCRIPT_DIR/replace_knobs_legacy.json"
LOG=/tmp/protolearn_llama.log
CAP=15
REPLICAS=3
ROUND_START=15
ROUNDS_AFTER=10
HISTORY_WINDOWS=(0 1 5 10)
OBS_MODEL="meta-llama/Llama-3.3-70B-Instruct"
OBS_PROVIDER="self-hosted"

# rid arrays per engine queue (kept in-shell via process substitution, not a pipe subshell).
declare -a ANTH_RIDS=()
declare -a OAI_RIDS=()

count_active() {
  # Count, among the run ids passed as args, how many still have a live --resume subprocess.
  local n=0 rid
  for rid in "$@"; do
    if ps -axo command 2>/dev/null | grep "Python -m schmidt run veyru" | grep -- "--resume" \
       | grep -v grep | grep -qE "/${rid}( |/)"; then
      n=$((n + 1))
    fi
  done
  echo "$n"
}

count_existing() {
  # replace_llama runs already carrying this src AND this exact history window.
  local src_id="$1" hist="$2" n=0
  for lf in "$RUNS_DIR"/veyru/*/labels.json; do
    [ -f "$lf" ] || continue
    if grep -q '"phase=replace_llama"' "$lf" 2>/dev/null \
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
  # echoes the new run id (timestamp dir name) on success, empty on failure.
  local short="$1" src_dir="$2" src_id="$3" kind="$4" hist="$5"
  local from=$((ROUND_START - hist))
  echo "$(date) [$short->llama] replace src=$src_id hist=$hist from=$from kind=$kind" >> "$LOG"
  local out rid knobs="$REPLACE_KNOBS_CANON"
  if [ "$kind" = "legacy" ]; then knobs="$REPLACE_KNOBS_LEGACY"; fi
  # Llama 3.3 70B is served at 24576 ctx; the default 16384 output cap + the
  # observer's growing input (peaks ~18k) overflows it. veyru outputs are short
  # tool calls, so cap output low to leave maximum room for input.
  out=$(LLM_MAX_TOKENS=2048 VIRTUAL_ENV= uv run --no-sync python -m schmidt replace-agent veyru \
        --source-run-dir "$src_dir" --round-start "$ROUND_START" \
        --replaced-agent-id field_observer \
        --model "$OBS_MODEL" --provider "$OBS_PROVIDER" \
        --rounds-after-swap "$ROUNDS_AFTER" --history-from-round "$from" \
        --knobs "$knobs" --runs-dir "./$RUNS_DIR" 2>>"$LOG")
  rid=$(echo "$out" | grep -oE 'new_run_id=[^ ]+' | head -1 | cut -d= -f2 | sed 's#veyru/##')
  if [ -n "$rid" ]; then
    label_run "veyru/$rid" "[\"protocol_learnability\", \"phase=replace_llama\", \"budget=250\", \"model=${short}\", \"observer=llama\", \"history=${hist}\", \"src=${src_id}\", \"ordered_easy_rounds\"]"
  fi
  sleep 2
  echo "$rid"
}

WORKLIST=$(VIRTUAL_ENV= uv run --no-sync python "$SCRIPT_DIR/list_baselines.py" "$RUNS_DIR/veyru")

run_engine_queue() {
  # $1 = engine provider (anthropic|openai); operates only on baselines of that family.
  local engine="$1"
  while read -r short model prov kind src_dir; do
    [ -n "$short" ] || continue
    [ "$prov" = "$engine" ] || continue
    local src_id="veyru/$(basename "$src_dir")"
    for hist in "${HISTORY_WINDOWS[@]}"; do
      local have; have=$(count_existing "$src_id" "$hist")
      local need=$((REPLICAS - have))
      echo "$(date) [$engine][$short] src=$src_id hist=$hist have=$have need=$need" >> "$LOG"
      [ "$need" -gt 0 ] || continue
      for _ in $(seq 1 "$need"); do
        if [ "$engine" = "anthropic" ]; then
          while [ "$(count_active ${ANTH_RIDS[@]+"${ANTH_RIDS[@]}"})" -ge "$CAP" ]; do sleep 30; done
          local rid; rid=$(launch_replace "$short" "$src_dir" "$src_id" "$kind" "$hist")
          [ -n "$rid" ] && ANTH_RIDS+=("$rid")
        else
          while [ "$(count_active ${OAI_RIDS[@]+"${OAI_RIDS[@]}"})" -ge "$CAP" ]; do sleep 30; done
          local rid; rid=$(launch_replace "$short" "$src_dir" "$src_id" "$kind" "$hist")
          [ -n "$rid" ] && OAI_RIDS+=("$rid")
        fi
      done
    done
  done < <(echo "$WORKLIST")
  echo "$(date) [$engine] llama queue complete" >> "$LOG"
}

# Guard: never run with a non-HEAD judge prompt.
JP="src/schmidt/scenarios/veyru/prompts/stabilization_judge.jinja"
if [ "$(git hash-object $JP)" != "$(git rev-parse HEAD:$JP)" ]; then
  echo "ABORT: $JP is not at HEAD. The judge prompt must never be pinned/edited for a run." >&2
  exit 1
fi

echo "=== protocol-learnability llama sweep started $(date): $(echo "$WORKLIST" | grep -c .) baselines x {0,1,5,10} x $REPLICAS ===" >> "$LOG"
run_engine_queue anthropic &
run_engine_queue openai &
wait
echo "=== protocol-learnability llama sweep complete $(date) ===" >> "$LOG"
