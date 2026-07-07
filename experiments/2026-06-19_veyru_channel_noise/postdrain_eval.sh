#!/bin/bash
# Post-drain eval stages for the channel-noise sweep (run after all sims drain).
# Stage 1: protocol_explanation + communication_open_coding per run (cap 4).
# Stage 2: consolidate communication ontology across the cohort (1 LLM call).
# Stage 3: communication_feature_presence per run against that ontology (cap 4).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
LOG=/tmp/veyru_noise_postdrain.log
CAP=4
JUDGE_MODEL=claude-haiku-4-5-20251001
JUDGE_PROVIDER=anthropic
ONTOLOGY_VERSION=channel_noise_2026_06_19
ONTOLOGY_PATH="$RUNS_DIR/veyru/_ontology/${ONTOLOGY_VERSION}.json"
RUN_IDS_FILE=/tmp/veyru_noise_run_ids.txt

channel_noise_dirs() {
  # Only emit runs that have emitted simulation_ended. Never gate on a
  # round_advanced count: round_advanced to N fires when round N STARTS, so a
  # count-based gate evaluates mid-final-round and drops the last round.
  for d in "$RUNS_DIR"/veyru/*/; do
    [ -f "$d/labels.json" ] && grep -q '"channel_noise"' "$d/labels.json" || continue
    grep -q '"simulation_ended"' "$d/veyru.jsonl" 2>/dev/null && echo "$d"
  done
}

count_running_evals() {
  ps -axo command 2>/dev/null | grep "Python -m glossogen evaluate veyru" | grep -v grep | wc -l | tr -d ' '
}

eval_metrics() {
  local d="$1" metrics="$2" extra_log="$3"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate veyru \
    --run-dir "$d" --metrics "$metrics" \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    >> "$d/$extra_log" 2>&1
}

echo "=== post-drain eval started $(date) ===" >> "$LOG"

echo "$(date) STAGE 1: protocol_explanation + communication_open_coding" >> "$LOG"
for d in $(channel_noise_dirs); do
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 15; done
  echo "$(date) [s1] $d" >> "$LOG"
  eval_metrics "$d" "protocol_explanation,communication_open_coding" "eval_postdrain_stdout.log" &
  sleep 1
done
wait
echo "$(date) STAGE 1 complete" >> "$LOG"

echo "$(date) STAGE 2: consolidate ontology (this cohort only)" >> "$LOG"
: > "$RUN_IDS_FILE"
for d in $(channel_noise_dirs); do echo "veyru/$(basename "$d")" >> "$RUN_IDS_FILE"; done
VIRTUAL_ENV= uv run --no-sync python scripts/consolidate_communication_ontology.py \
  --scenario-name veyru --runs-dir "$RUNS_DIR" --version "$ONTOLOGY_VERSION" \
  --run-ids-file "$RUN_IDS_FILE" \
  --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
  >> "$LOG" 2>&1 || { echo "$(date) WARN ontology consolidation failed; skipping stage 3" >> "$LOG"; exit 1; }
echo "$(date) STAGE 2 complete -> $ONTOLOGY_PATH" >> "$LOG"

echo "$(date) STAGE 3: communication_feature_presence (ontology pinned)" >> "$LOG"
for d in $(channel_noise_dirs); do
  while [ "$(count_running_evals)" -ge "$CAP" ]; do sleep 15; done
  echo "$(date) [s3] $d" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate veyru \
    --run-dir "$d" --metrics communication_feature_presence \
    --model "$JUDGE_MODEL" --provider "$JUDGE_PROVIDER" \
    --ontology-path "$ONTOLOGY_PATH" \
    >> "$d/eval_postdrain_stdout.log" 2>&1 &
  sleep 1
done
wait
echo "$(date) post-drain eval complete" >> "$LOG"
