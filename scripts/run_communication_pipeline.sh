#!/usr/bin/env bash
#
# Run the full open coding → ontology → relabel pipeline across every
# run directory of the chosen scenario. Three phases:
#
#   1. communication_open_coding   (parallel, $CONCURRENCY workers)
#   2. consolidate_communication_ontology   (one call, blocks until done)
#   3. communication_feature_presence   (parallel, $CONCURRENCY workers)
#
# Idempotent: each phase skips runs whose sidecar already exists. Kill
# mid-run and re-launch — the script picks up where it left off. All
# per-eval logs go to /tmp/pipeline_<run>_<phase>.log; one-line status
# rows are appended to $STATUS_LOG so failures are auditable.
#
# Usage:
#   scripts/run_communication_pipeline.sh --scenario veyru [--phase 1|2|3|all] [--limit N]
#   scripts/run_communication_pipeline.sh --scenario container_yard_stacking
#
#   --scenario  scenario name; runs are read from $RUNS_DIR/<scenario>/*/
#               (and the per-scenario JSONL filename is <scenario>.jsonl)
#   --phase     restrict to a single phase (default: all)
#   --limit     process at most N runs per parallel phase (default: 0 = all)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CONCURRENCY="${CONCURRENCY:-10}"
JUDGE_MODEL="${JUDGE_MODEL:-claude-haiku-4-5-20251001}"
JUDGE_PROVIDER="${JUDGE_PROVIDER:-anthropic}"
RUNS_DIR="${RUNS_DIR:-runs}"
STATUS_LOG="${STATUS_LOG:-/tmp/communication_pipeline_status.log}"
CONSOLIDATE_MIN_RUNS="${CONSOLIDATE_MIN_RUNS:-1}"

OPEN_CODING_METRIC="communication_open_coding"
OPEN_CODING_SIDECAR="communication_open_coding.json"
FEATURE_PRESENCE_METRIC="communication_feature_presence"
FEATURE_PRESENCE_SIDECAR="communication_feature_presence.json"

SCENARIO=""
PHASE="all"
LIMIT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --scenario) SCENARIO="$2"; shift 2 ;;
    --phase) PHASE="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SCENARIO" ]; then
  echo "ERROR: --scenario <name> is required" >&2
  exit 2
fi

SCENARIO_RUNS_DIR="$RUNS_DIR/$SCENARIO"
SCENARIO_ONTOLOGY_DIR="$SCENARIO_RUNS_DIR/_ontology"
SCENARIO_JSONL="${SCENARIO}.jsonl"

log_status() {
  # tab-separated: timestamp \t run_id \t phase \t exit_code \t duration_seconds
  printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" >> "$STATUS_LOG"
}

# Build the queue of scenario runs that have a JSONL log but no $1 sidecar.
build_queue() {
  local sidecar_name="$1"
  for d in "$SCENARIO_RUNS_DIR"/*/; do
    [ -d "$d" ] || continue
    [ -f "${d}${SCENARIO_JSONL}" ] || continue
    [ -f "${d}${sidecar_name}" ] && continue
    printf '%s\n' "${d%/}"
  done
}

# Run one eval and emit a status row. Exported so xargs subshells can call it.
run_one_eval() {
  local run_dir="$1"
  local metric="$2"
  local ontology_path="$3"   # empty string when not applicable
  local run_id
  run_id="$(basename "$(dirname "$run_dir")")/$(basename "$run_dir")"
  local log="/tmp/pipeline_$(basename "$run_dir")_${metric}.log"
  local start_ts
  start_ts=$(date +%s)

  local cmd=(
    env "VIRTUAL_ENV="
    uv run --no-sync python -m glossogen evaluate "$SCENARIO"
    --run-dir "$run_dir"
    --metrics "$metric"
    --model "$JUDGE_MODEL"
    --provider "$JUDGE_PROVIDER"
  )
  if [ -n "$ontology_path" ]; then
    cmd+=(--ontology-path "$ontology_path")
  fi

  "${cmd[@]}" > "$log" 2>&1
  local rc=$?
  local end_ts
  end_ts=$(date +%s)
  log_status "$run_id" "$metric" "$rc" "$((end_ts - start_ts))"
  return $rc
}

export -f run_one_eval log_status
export JUDGE_MODEL JUDGE_PROVIDER STATUS_LOG SCENARIO

apply_limit() {
  if [ "$LIMIT" -gt 0 ]; then
    head -n "$LIMIT"
  else
    cat
  fi
}

phase_one() {
  echo "=== Phase 1: open coding ==="
  local queue_file="/tmp/communication_pipeline_${SCENARIO}_phase1_queue.txt"
  build_queue "$OPEN_CODING_SIDECAR" | apply_limit > "$queue_file"
  local n
  n=$(wc -l < "$queue_file" | tr -d ' ')
  echo "queue: $n run(s) need $OPEN_CODING_METRIC"
  if [ "$n" -eq 0 ]; then return 0; fi
  xargs -P "$CONCURRENCY" -I '{}' bash -c 'run_one_eval "$1" "$2" ""' _ '{}' "$OPEN_CODING_METRIC" < "$queue_file"
  echo "phase 1 done"
}

phase_two() {
  echo "=== Phase 2: consolidation ==="
  local run_ids_file="/tmp/communication_pipeline_${SCENARIO}_phase2_run_ids.txt"
  : > "$run_ids_file"
  for d in "$SCENARIO_RUNS_DIR"/*/; do
    [ -f "${d}${OPEN_CODING_SIDECAR}" ] || continue
    printf '%s/%s\n' "$SCENARIO" "$(basename "$d")" >> "$run_ids_file"
  done
  local n
  n=$(wc -l < "$run_ids_file" | tr -d ' ')
  echo "pool: $n run(s) have open-coding sidecars"
  if [ "$n" -lt 2 ]; then
    echo "need at least 2 sidecars to consolidate; phase 2 skipped"
    return 0
  fi
  mkdir -p "$SCENARIO_ONTOLOGY_DIR"
  local version
  version="$(date -u +%Y%m%dT%H%M%SZ)_full"
  local output="${SCENARIO_ONTOLOGY_DIR}/${version}.json"
  echo "writing ontology to $output"
  local start_ts
  start_ts=$(date +%s)
  env "VIRTUAL_ENV=" uv run --no-sync python scripts/consolidate_communication_ontology.py \
    --scenario-name "$SCENARIO" \
    --run-ids-file "$run_ids_file" \
    --runs-dir "$RUNS_DIR" \
    --version "$version" \
    --model "$JUDGE_MODEL" \
    --provider "$JUDGE_PROVIDER" \
    --min-runs "$CONSOLIDATE_MIN_RUNS" \
    > "/tmp/communication_pipeline_${SCENARIO}_phase2.log" 2>&1
  local rc=$?
  local end_ts
  end_ts=$(date +%s)
  log_status "consolidation" "ontology" "$rc" "$((end_ts - start_ts))"
  if [ "$rc" -ne 0 ]; then
    echo "phase 2 FAILED (rc=$rc); see /tmp/communication_pipeline_${SCENARIO}_phase2.log" >&2
    return $rc
  fi
  echo "$output" > "/tmp/communication_pipeline_${SCENARIO}_latest_ontology.txt"
  echo "phase 2 done; ontology: $output"
}

phase_three() {
  echo "=== Phase 3: feature presence ==="
  local ontology_path
  local latest_file="/tmp/communication_pipeline_${SCENARIO}_latest_ontology.txt"
  if [ -f "$latest_file" ]; then
    ontology_path="$(cat "$latest_file")"
  else
    # Fall back to the newest ontology in the scenario's ontology dir.
    ontology_path="$(ls -t "$SCENARIO_ONTOLOGY_DIR"/*.json 2>/dev/null | head -n 1)"
  fi
  if [ -z "$ontology_path" ] || [ ! -f "$ontology_path" ]; then
    echo "no ontology JSON found under $SCENARIO_ONTOLOGY_DIR; run phase 2 first" >&2
    return 1
  fi
  echo "using ontology: $ontology_path"
  export ONTOLOGY_PATH="$ontology_path"

  local queue_file="/tmp/communication_pipeline_${SCENARIO}_phase3_queue.txt"
  build_queue "$FEATURE_PRESENCE_SIDECAR" | apply_limit > "$queue_file"
  local n
  n=$(wc -l < "$queue_file" | tr -d ' ')
  echo "queue: $n run(s) need $FEATURE_PRESENCE_METRIC"
  if [ "$n" -eq 0 ]; then return 0; fi
  xargs -P "$CONCURRENCY" -I '{}' bash -c 'run_one_eval "$1" "$2" "$ONTOLOGY_PATH"' _ '{}' "$FEATURE_PRESENCE_METRIC" < "$queue_file"
  echo "phase 3 done"
}

mkdir -p "$(dirname "$STATUS_LOG")"
echo "scenario=$SCENARIO concurrency=$CONCURRENCY judge=$JUDGE_MODEL/$JUDGE_PROVIDER runs_dir=$SCENARIO_RUNS_DIR"
echo "status log: $STATUS_LOG"

case "$PHASE" in
  1) phase_one ;;
  2) phase_two ;;
  3) phase_three ;;
  all) phase_one && phase_two && phase_three ;;
  *) echo "Unknown phase: $PHASE (use 1|2|3|all)" >&2; exit 2 ;;
esac
