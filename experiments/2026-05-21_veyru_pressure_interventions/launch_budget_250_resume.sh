#!/bin/bash
# Phase 6 launcher — RESUMED with per-provider parallelism.
#
# Replaces the original launch_budget_250_sweep.sh after the 7 already-launched
# specs (6 baselines + 1 postmortem_kept_on_gpt). The remaining 29 specs are
# split into two independent queues (one per model), each capped at 6 concurrent
# sims. The two queues run in parallel via background subshells, so a paused
# gpt-5.4 queue never blocks the claude-sonnet-4-6 queue (the bug the previous
# strict-sequential launcher exhibited).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

LOG=/tmp/phase6_budget_250.log
EXP_DIR="experiments/2026-05-21_veyru_pressure_interventions"

GPT_SOURCE="1778173047"
SONNET_SOURCE="1778172878"

# Spec format inside each model's queue: "<knobs_file> <variant_label> <budget_label>".
# 14 specs per model = 28 remaining launches (the 7 already-launched have been
# removed: 3 gpt baselines, 3 sonnet baselines, 1 gpt postmortem_kept_on).
declare -a GPT_SPECS=(
  "${EXP_DIR}/postmortem_kept_on_b250_gpt.json postmortem_kept_on budget=250"
  "${EXP_DIR}/postmortem_kept_on_b250_gpt.json postmortem_kept_on budget=250"
  "${EXP_DIR}/budget_increased_b250.json budget_increased budget=1500"
  "${EXP_DIR}/budget_increased_b250.json budget_increased budget=1500"
  "${EXP_DIR}/budget_increased_b250.json budget_increased budget=1500"
  "${EXP_DIR}/budget_decreased_b250.json budget_decreased budget=150"
  "${EXP_DIR}/budget_decreased_b250.json budget_decreased budget=150"
  "${EXP_DIR}/budget_decreased_b250.json budget_decreased budget=150"
  "${EXP_DIR}/with_noise_b250.json with_noise budget=250"
  "${EXP_DIR}/with_noise_b250.json with_noise budget=250"
  "${EXP_DIR}/with_noise_b250.json with_noise budget=250"
  "${EXP_DIR}/new_motifs_injected_b250_gpt.json new_motifs_injected budget=250"
  "${EXP_DIR}/new_motifs_injected_b250_gpt.json new_motifs_injected budget=250"
  "${EXP_DIR}/new_motifs_injected_b250_gpt.json new_motifs_injected budget=250"
)

declare -a SONNET_SPECS=(
  "${EXP_DIR}/postmortem_kept_on_b250_sonnet.json postmortem_kept_on budget=250"
  "${EXP_DIR}/postmortem_kept_on_b250_sonnet.json postmortem_kept_on budget=250"
  "${EXP_DIR}/postmortem_kept_on_b250_sonnet.json postmortem_kept_on budget=250"
  "${EXP_DIR}/budget_increased_b250.json budget_increased budget=1500"
  "${EXP_DIR}/budget_increased_b250.json budget_increased budget=1500"
  "${EXP_DIR}/budget_increased_b250.json budget_increased budget=1500"
  "${EXP_DIR}/budget_decreased_b250.json budget_decreased budget=150"
  "${EXP_DIR}/budget_decreased_b250.json budget_decreased budget=150"
  "${EXP_DIR}/budget_decreased_b250.json budget_decreased budget=150"
  "${EXP_DIR}/with_noise_b250.json with_noise budget=250"
  "${EXP_DIR}/with_noise_b250.json with_noise budget=250"
  "${EXP_DIR}/with_noise_b250.json with_noise budget=250"
  "${EXP_DIR}/new_motifs_injected_b250_sonnet.json new_motifs_injected budget=250"
  "${EXP_DIR}/new_motifs_injected_b250_sonnet.json new_motifs_injected budget=250"
  "${EXP_DIR}/new_motifs_injected_b250_sonnet.json new_motifs_injected budget=250"
)

count_running_for_model() {
  pgrep -f "Python -m schmidt run veyru --model $1" 2>/dev/null | wc -l | tr -d ' '
}

launch_resume() {
  local source_id=$1
  local knobs=$2
  local variant_label=$3
  local budget_label=$4
  echo "$(date) launching source=$source_id knobs=$knobs variant=$variant_label budget=$budget_label" >> "$LOG"
  local out
  out=$(VIRTUAL_ENV= uv run --no-sync python -m schmidt resume-at-round veyru \
    --source-run-dir "runs/veyru/$source_id" \
    --round-start 16 \
    --runs-dir runs \
    --knobs "$knobs" 2>&1)
  echo "$out" | tail -3 >> "$LOG"
  local new_run_id
  new_run_id=$(echo "$out" | grep -oE 'new_run_id=veyru/[0-9]+' | head -1 | sed 's|new_run_id=||')
  if [ -n "$new_run_id" ]; then
    local labels_json
    if [ "$variant_label" = "_baseline_" ]; then
      labels_json="[\"cultural_transmission\", \"$budget_label\"]"
    else
      labels_json="[\"$variant_label\", \"$budget_label\", \"cultural_transmission\"]"
    fi
    echo "$labels_json" > "runs/$new_run_id/labels.json"
    echo "$(date) labeled $new_run_id with $labels_json" >> "$LOG"
  else
    echo "$(date) WARN no new_run_id parsed" >> "$LOG"
  fi
}

process_queue_gpt() {
  for spec in "${GPT_SPECS[@]}"; do
    read -r knobs variant_label budget_label <<< "$spec"
    while [ "$(count_running_for_model gpt-5.4)" -ge 6 ]; do
      sleep 30
    done
    launch_resume "$GPT_SOURCE" "$knobs" "$variant_label" "$budget_label"
    sleep 2
  done
  echo "$(date) [gpt-5.4] queue complete" >> "$LOG"
}

process_queue_sonnet() {
  for spec in "${SONNET_SPECS[@]}"; do
    read -r knobs variant_label budget_label <<< "$spec"
    while [ "$(count_running_for_model claude-sonnet-4-6)" -ge 6 ]; do
      sleep 30
    done
    launch_resume "$SONNET_SOURCE" "$knobs" "$variant_label" "$budget_label"
    sleep 2
  done
  echo "$(date) [sonnet] queue complete" >> "$LOG"
}

echo "=== Phase 6 RESUMED launcher (per-provider parallel) started $(date) ===" >> "$LOG"
process_queue_gpt &
process_queue_sonnet &
wait
echo "=== Phase 6 launcher complete $(date) ===" >> "$LOG"
