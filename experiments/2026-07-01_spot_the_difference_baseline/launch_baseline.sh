#!/bin/bash
# spot_the_difference BASELINE cohort — 30 runs.
#
#   models    claude-sonnet-4-6/anthropic, claude-opus-4-7/anthropic, gpt-5.4/openai
#   10 replicas per model (30 runs total, 20 anthropic + 10 openai).
#
# Fixed knobs (knobs_base.json): 15 rounds, seed=42 (FIXED across every run, so
# all 10 replicas per model face the byte-identical 15 scene pairs — the reps
# measure LLM run-to-run variance on one workload), two_teams=true,
# all_must_submit=true, round_time_budget_seconds=-1 (NO char cap),
# max_round_duration_seconds=600 (so a round ends on both-teams-submit, not a
# premature wall-clock timeout), easy_round_numbers=[], judge=haiku. No inline
# overrides — the config carries everything.
#
# Concurrency capped PER PROVIDER at 10 (your choice): the anthropic queue runs
# sonnet+opus (20 runs) against a single shared 10-cap; the openai queue runs gpt
# against its own 10-cap. Two parallel queues joined by `wait`, so a paused
# anthropic queue never idles the openai slots. Each run is labelled ["baseline"]
# as soon as its run dir appears (parsed from the run's own stdout log).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../.."

RUNS_DIR=runs
CONFIG="$SCRIPT_DIR/knobs_base.json"
LOG=/tmp/spot_baseline.log
CAP=10
REPLICAS=10

count_running_provider() {
  # $1 is a model-name PREFIX that identifies the provider's sims: "claude-"
  # matches BOTH claude-sonnet-4-6 and claude-opus-4-7 (anthropic shares one
  # cap); "gpt-5.4" matches the openai sims. Capital "Python" matches the
  # homebrew sim interpreter, never the "uv run python" wrapper nor the grep.
  ps -axo command 2>/dev/null \
    | grep "Python -m glossogen run spot_the_difference --model $1" \
    | grep -v grep | wc -l | tr -d ' '
}

launch_one() {
  local short="$1" model="$2" provider="$3" rep="$4"
  local rep_log="/tmp/spot_baseline_${short}_rep${rep}.log"
  : > "$rep_log"
  echo "$(date) [$short] launching rep $rep/$REPLICAS" >> "$LOG"
  nohup bash -c "VIRTUAL_ENV= uv run --no-sync python -m glossogen run spot_the_difference \
      --model '$model' --provider '$provider' --runs-dir ./$RUNS_DIR --config '$CONFIG' \
      >>'$rep_log' 2>&1" >/dev/null 2>&1 &
  disown
  local rd=""
  for _ in $(seq 1 90); do
    rd=$(grep -oE "Run directory: [^ ]+" "$rep_log" 2>/dev/null | head -1 | sed 's|Run directory: ||' || true)
    [ -n "$rd" ] && break
    sleep 1
  done
  if [ -n "$rd" ]; then
    echo '["baseline"]' > "$RUNS_DIR/spot_the_difference/$(basename "$rd")/labels.json"
    echo "$(date) [$short] labelled $(basename "$rd")" >> "$LOG"
  else
    echo "$(date) [$short] WARN no run dir found in $rep_log (rep=$rep)" >> "$LOG"
  fi
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

# One queue per PROVIDER. The anthropic queue interleaves sonnet+opus against the
# shared count_running_provider "claude-" cap.
process_anthropic() {
  local rep
  for rep in $(seq 1 "$REPLICAS"); do
    while [ "$(count_running_provider claude-)" -ge "$CAP" ]; do sleep 30; done
    launch_one sonnet46 claude-sonnet-4-6 anthropic "$rep"
  done
  for rep in $(seq 1 "$REPLICAS"); do
    while [ "$(count_running_provider claude-)" -ge "$CAP" ]; do sleep 30; done
    launch_one opus47 claude-opus-4-7 anthropic "$rep"
  done
  echo "$(date) [anthropic] queue complete" >> "$LOG"
}

process_openai() {
  local rep
  for rep in $(seq 1 "$REPLICAS"); do
    while [ "$(count_running_provider gpt-5.4)" -ge "$CAP" ]; do sleep 30; done
    launch_one gpt54 gpt-5.4 openai "$rep"
  done
  echo "$(date) [openai] queue complete" >> "$LOG"
}

echo "=== spot_the_difference baseline started $(date) ===" >> "$LOG"
process_anthropic &
process_openai &
wait
echo "$(date): all baseline launches complete" >> "$LOG"
