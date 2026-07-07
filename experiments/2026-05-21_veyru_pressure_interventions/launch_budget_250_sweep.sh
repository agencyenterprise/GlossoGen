#!/bin/bash
# Phase 6: budget=250 sweep. 36 runs total — 6 variants × 2 sources × 3 replicas.
# Sources are veyru/1778172878 (sonnet, budget=250) and veyru/1778173047
# (gpt-5.4, budget=250), both cultural_transmission with the canonical
# set_postmortem(r=16, off) + 3 swap_agent schedule.
#
# Per-model cap of 3 so we never exceed the Phase 1+3 launch policy.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

LOG=/tmp/phase6_budget_250.log
EXP_DIR="experiments/2026-05-21_veyru_pressure_interventions"

# Spec format: "<source_id> <knob_file> <model_tag> <variant_label> <budget_label>"
# - source_id is the veyru/<timestamp> dir (relative to runs/)
# - knob_file is the experiments/.../ JSON
# - model_tag is the model name used by per-model parallelism gating
# - variant_label is the intervention tag written to labels.json
# - budget_label is the budget=N label (250 for most variants; 1500 for
#   budget_increased and 150 for budget_decreased since those override the knob)
declare -a SPECS=(
  # baseline (3 per source)
  "1778173047 ${EXP_DIR}/baseline_b250.json gpt-5.4 _baseline_ budget=250"
  "1778173047 ${EXP_DIR}/baseline_b250.json gpt-5.4 _baseline_ budget=250"
  "1778173047 ${EXP_DIR}/baseline_b250.json gpt-5.4 _baseline_ budget=250"
  "1778172878 ${EXP_DIR}/baseline_b250.json claude-sonnet-4-6 _baseline_ budget=250"
  "1778172878 ${EXP_DIR}/baseline_b250.json claude-sonnet-4-6 _baseline_ budget=250"
  "1778172878 ${EXP_DIR}/baseline_b250.json claude-sonnet-4-6 _baseline_ budget=250"
  # postmortem_kept_on
  "1778173047 ${EXP_DIR}/postmortem_kept_on_b250_gpt.json gpt-5.4 postmortem_kept_on budget=250"
  "1778173047 ${EXP_DIR}/postmortem_kept_on_b250_gpt.json gpt-5.4 postmortem_kept_on budget=250"
  "1778173047 ${EXP_DIR}/postmortem_kept_on_b250_gpt.json gpt-5.4 postmortem_kept_on budget=250"
  "1778172878 ${EXP_DIR}/postmortem_kept_on_b250_sonnet.json claude-sonnet-4-6 postmortem_kept_on budget=250"
  "1778172878 ${EXP_DIR}/postmortem_kept_on_b250_sonnet.json claude-sonnet-4-6 postmortem_kept_on budget=250"
  "1778172878 ${EXP_DIR}/postmortem_kept_on_b250_sonnet.json claude-sonnet-4-6 postmortem_kept_on budget=250"
  # budget_increased (1500s — overrides source budget)
  "1778173047 ${EXP_DIR}/budget_increased_b250.json gpt-5.4 budget_increased budget=1500"
  "1778173047 ${EXP_DIR}/budget_increased_b250.json gpt-5.4 budget_increased budget=1500"
  "1778173047 ${EXP_DIR}/budget_increased_b250.json gpt-5.4 budget_increased budget=1500"
  "1778172878 ${EXP_DIR}/budget_increased_b250.json claude-sonnet-4-6 budget_increased budget=1500"
  "1778172878 ${EXP_DIR}/budget_increased_b250.json claude-sonnet-4-6 budget_increased budget=1500"
  "1778172878 ${EXP_DIR}/budget_increased_b250.json claude-sonnet-4-6 budget_increased budget=1500"
  # budget_decreased (150s)
  "1778173047 ${EXP_DIR}/budget_decreased_b250.json gpt-5.4 budget_decreased budget=150"
  "1778173047 ${EXP_DIR}/budget_decreased_b250.json gpt-5.4 budget_decreased budget=150"
  "1778173047 ${EXP_DIR}/budget_decreased_b250.json gpt-5.4 budget_decreased budget=150"
  "1778172878 ${EXP_DIR}/budget_decreased_b250.json claude-sonnet-4-6 budget_decreased budget=150"
  "1778172878 ${EXP_DIR}/budget_decreased_b250.json claude-sonnet-4-6 budget_decreased budget=150"
  "1778172878 ${EXP_DIR}/budget_decreased_b250.json claude-sonnet-4-6 budget_decreased budget=150"
  # with_noise
  "1778173047 ${EXP_DIR}/with_noise_b250.json gpt-5.4 with_noise budget=250"
  "1778173047 ${EXP_DIR}/with_noise_b250.json gpt-5.4 with_noise budget=250"
  "1778173047 ${EXP_DIR}/with_noise_b250.json gpt-5.4 with_noise budget=250"
  "1778172878 ${EXP_DIR}/with_noise_b250.json claude-sonnet-4-6 with_noise budget=250"
  "1778172878 ${EXP_DIR}/with_noise_b250.json claude-sonnet-4-6 with_noise budget=250"
  "1778172878 ${EXP_DIR}/with_noise_b250.json claude-sonnet-4-6 with_noise budget=250"
  # new_motifs_injected
  "1778173047 ${EXP_DIR}/new_motifs_injected_b250_gpt.json gpt-5.4 new_motifs_injected budget=250"
  "1778173047 ${EXP_DIR}/new_motifs_injected_b250_gpt.json gpt-5.4 new_motifs_injected budget=250"
  "1778173047 ${EXP_DIR}/new_motifs_injected_b250_gpt.json gpt-5.4 new_motifs_injected budget=250"
  "1778172878 ${EXP_DIR}/new_motifs_injected_b250_sonnet.json claude-sonnet-4-6 new_motifs_injected budget=250"
  "1778172878 ${EXP_DIR}/new_motifs_injected_b250_sonnet.json claude-sonnet-4-6 new_motifs_injected budget=250"
  "1778172878 ${EXP_DIR}/new_motifs_injected_b250_sonnet.json claude-sonnet-4-6 new_motifs_injected budget=250"
)

count_running_for_model() {
  pgrep -f "Python -m glossogen run veyru --model $1" 2>/dev/null | wc -l | tr -d ' '
}

echo "=== Phase 6 launcher started $(date) ===" >> "$LOG"
for spec in "${SPECS[@]}"; do
  read -r src knobs model_tag variant_label budget_label <<< "$spec"
  while [ "$(count_running_for_model "$model_tag")" -ge 3 ]; do
    sleep 30
  done
  echo "$(date) launching source=$src knobs=$knobs variant=$variant_label budget=$budget_label" >> "$LOG"
  out=$(VIRTUAL_ENV= uv run --no-sync python -m glossogen resume-at-round veyru \
    --source-run-dir "runs/veyru/$src" \
    --round-start 16 \
    --runs-dir runs \
    --knobs "$knobs" 2>&1)
  echo "$out" | tail -3 >> "$LOG"
  new_run_id=$(echo "$out" | grep -oE 'new_run_id=veyru/[0-9]+' | head -1 | sed 's|new_run_id=||')
  if [ -n "$new_run_id" ]; then
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
  sleep 2
done
echo "=== Phase 6 launcher complete $(date) ===" >> "$LOG"
