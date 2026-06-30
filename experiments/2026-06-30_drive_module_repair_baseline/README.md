# Drive-module-repair baseline (2026-06-30)

Establishes a drive_module_repair baseline whose per-budget `round_success`
spans the same range as the veyru baseline, so the two scenarios are
comparable. Budgets are chosen from a gpt-5.4 calibration sweep to land on
veyru's tiers `~{0.18, 0.30, 0.48, 0.77, 0.91}`.

## Design

| Dimension | Values | n |
|---|---|---|
| `round_time_budget_seconds` | 5 veyru-matched budgets (set via `DRIVE_BASELINE_BUDGETS`) | 5 |
| model | `gpt-5.4` (openai), `claude-opus-4-7` (anthropic) | 2 |
| replicas | 3 | 3 |

**30 cells** (5 budgets × 2 models × 3 reps), minus reuse of pre-existing reps.

Fixed knobs (`knobs_base.json`): 15 rounds, postmortem **on**, `seed=42`,
**`easy_round_numbers=[]`** (no warmup — matches veyru), `max_round_duration_seconds=900`
(generous so the char **budget** binds, not the wall-clock), judge
`claude-haiku-4-5-20251001`. Budget overridden inline per cell.

## Apples-to-apples

`seed=42` is fixed across every run and the case generator is budget- and
model-independent, so the per-round input (faults / units / symptoms / full
procedures) is **byte-identical** across all budgets and both models — verified
2026-06-30 by diffing `drive_module_case_started` events across a budget-200 and
a budget-500 run (identical for all shared rounds; only `round_time_budget_seconds`
differed).

## Reuse

The launcher is **reuse-aware**: it counts existing `baseline`-labelled runs
per `(model, budget)` (scoped to `runs/drive_module_repair/`) and only launches
the remainder to reach 3. The gpt-5.4 clean calibration-sweep runs (`seed=42`,
`easy=[]`, rc15, dur900) at any chosen budget are valid baseline reps — relabel
them `baseline` before launch and they count toward the 3, so only the missing
gpt rep + the 3 opus reps run.

## Run

```bash
DRIVE_BASELINE_BUDGETS="<b1 b2 b3 b4 b5>" \
  nohup bash experiments/2026-06-30_drive_module_repair_baseline/launch_baseline.sh \
  > /tmp/drive_baseline.stdout 2>&1 &
disown
```

Per-provider parallel queues, cap **10** each. Runs labelled on launch:
`["baseline","budget=<b>","model=<short>","rc=15"]`.

## Monitor

```bash
tail -20 /tmp/drive_baseline.log
ps -axo command | grep "Python -m schmidt run drive_module_repair" | grep -v grep | wc -l
```

## Evaluate (ONLY after every run has emitted `simulation_ended`)

```bash
nohup bash experiments/2026-06-30_drive_module_repair_baseline/eval_baseline.sh \
  > /tmp/drive_baseline_eval.stdout 2>&1 &
disown
```

**CRITICAL:** `eval_baseline.sh` gates strictly on the `simulation_ended` event
(never a round count) — a run with round 15 recorded but postmortem still
pending is NOT complete, and evaluating it clips `round_success`. The script
skips any run lacking `simulation_ended` and picks it up on a later pass.

Full comparable metric set: `round_success`, `round_ended_idle/timeout`,
`mean_chars_per_round/message`, `perplexity`, `content_filter_refusal`,
`shorthand_codes`, `slang_emergence`, `neologism`, `language_strangeness`,
`language_repetition`, `protocol_explanation`.
