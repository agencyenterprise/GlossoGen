#!/bin/bash
# EXP-CL13: arm A, both observation cells, revised split-budget world, n=30/cell.
B=/Users/thalys/Development/GlossoGen/.claude/worktrees/claude-benjamin-k
CFG_DIR=docs/research/covenant-game/experiments/EXP-CL13-pure-witness/configs
LOG=/private/tmp/claude-501/-Users-thalys-Development-GlossoGen--claude-worktrees-zen-wescoff-cbcd44/04b32412-f03b-42b8-84e7-7dd05397766c/scratchpad/launch_cl13.log
CAP=8
REPS=30
count_sims() {
  pgrep -f "glossogen run claude_benjamin_pure_witness" 2>/dev/null \
    | while read -r p; do ps -o comm= -p "$p" 2>/dev/null; done | grep -ci python
}
cd "$B" || exit 1
date +%s > "$LOG.floor"
echo "=== EXP-CL13 started $(date) (cap $CAP, floor $(cat "$LOG.floor")) ===" >> "$LOG"
for i in $(seq 1 $REPS); do
  for obs in observed unobserved; do
    while [ "$(count_sims)" -ge "$CAP" ]; do sleep 15; done
    VIRTUAL_ENV= uv run --no-sync python -m glossogen run claude_benjamin_pure_witness \
      --model claude-sonnet-5 --provider anthropic --runs-dir ./runs \
      --config "$CFG_DIR/arm_A_${obs}.json" \
      > /dev/null 2>&1 &
    echo "$(date +%H:%M:%S) rep=$i obs=$obs live=$(count_sims)" >> "$LOG"
    sleep 2
  done
done
wait
echo "=== EXP-CL13 complete $(date) ===" >> "$LOG"
