#!/bin/bash
# Launches the six `new_motifs_injected` resume-at-round replicas described in
# experiments/2026-05-21_veyru_pressure_interventions.md. Three per source:
#   - source veyru/1778518004 (gpt-5.4 baseline) — uses _gpt.json knobs
#   - source veyru/1778162284 (sonnet baseline)  — uses _sonnet.json knobs
# Per-model cap of 3 (so all six can run in parallel without exceeding the
# six-per-model limit applied during Phase 1).
set -euo pipefail
# Script lives at experiments/<exp_folder>/launch_new_motifs_injected.sh;
# go up two levels to reach the repo root so the glossogen CLI can resolve
# runs/ and the knob paths below.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

LOG=/tmp/phase3_new_motifs_injected.log
EXP_DIR="experiments/2026-05-21_veyru_pressure_interventions"

declare -a SPECS=(
  "1778518004 ${EXP_DIR}/new_motifs_injected_gpt.json gpt-5.4"
  "1778518004 ${EXP_DIR}/new_motifs_injected_gpt.json gpt-5.4"
  "1778518004 ${EXP_DIR}/new_motifs_injected_gpt.json gpt-5.4"
  "1778162284 ${EXP_DIR}/new_motifs_injected_sonnet.json claude-sonnet-4-6"
  "1778162284 ${EXP_DIR}/new_motifs_injected_sonnet.json claude-sonnet-4-6"
  "1778162284 ${EXP_DIR}/new_motifs_injected_sonnet.json claude-sonnet-4-6"
)

count_running_for_model() {
  pgrep -f "Python -m glossogen run veyru --model $1" 2>/dev/null | wc -l | tr -d ' '
}

echo "=== Phase 3 launcher started $(date) ===" >> "$LOG"
for spec in "${SPECS[@]}"; do
  read -r src knobs model_tag <<< "$spec"
  while [ "$(count_running_for_model "$model_tag")" -ge 6 ]; do
    sleep 30
  done
  echo "$(date) launching source=$src knobs=$knobs" >> "$LOG"
  out=$(VIRTUAL_ENV= uv run --no-sync python -m glossogen resume-at-round veyru \
    --source-run-dir "runs/veyru/$src" \
    --round-start 16 \
    --runs-dir runs \
    --knobs "$knobs" 2>&1)
  echo "$out" | tail -3 >> "$LOG"
  new_run_id=$(echo "$out" | grep -oE 'new_run_id=veyru/[0-9]+' | head -1 | sed 's|new_run_id=||')
  if [ -n "$new_run_id" ]; then
    echo '["new_motifs_injected","budget=450","cultural_transmission"]' > "runs/$new_run_id/labels.json"
    echo "$(date) labeled $new_run_id" >> "$LOG"
  else
    echo "$(date) WARN no new_run_id parsed" >> "$LOG"
  fi
  sleep 2
done
echo "=== Phase 3 launcher complete $(date) ===" >> "$LOG"
