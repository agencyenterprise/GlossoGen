# No-swap baseline budget=250 · postmortem always on — 2026-05-25

## Cohort

- **Variant**: no swaps + postmortem enabled throughout all 40 rounds (empty `scheduled_events`)
- **Sibling cohorts**:
  - same budget, postmortem off after r=11: [`2026-05-25_no_swap_baseline_pm_phase_a_budget250_sonnet`](../2026-05-25_no_swap_baseline_pm_phase_a_budget250_sonnet/)
  - same pm schedule, budget=450: [`2026-05-25_no_swap_baseline_pm_always_budget450_sonnet`](../2026-05-25_no_swap_baseline_pm_always_budget450_sonnet/)
- **Replicas**: 10 fully independent sonnet runs (`claude-sonnet-4-6`, seed=42, `claude-haiku-4-5-20251001` judge) — initial 5 (reps 1–5) plus a 5-rep backfill on 2026-05-26 to investigate a Phase D dip in the cohort's mean round_success
- **Rounds**: 40 total, **no swaps**
- **Time budget per round**: 250 s

## Labels applied

```json
["baseline_no_swap", "pm=always", "budget=250"]
```

## Runs

| Rep | Run ID | Status |
|---|---|---|
| 1 | [veyru/1779748299](http://localhost:3000/runs/veyru/1779748299) | ✓ ended |
| 2 | [veyru/1779751785](http://localhost:3000/runs/veyru/1779751785) | ✓ ended |
| 3 | [veyru/1779752927](http://localhost:3000/runs/veyru/1779752927) | ✓ ended |
| 4 | [veyru/1779756684](http://localhost:3000/runs/veyru/1779756684) | ✓ ended |
| 5 | [veyru/1779759660](http://localhost:3000/runs/veyru/1779759660) | ✓ ended |
| 6 | [veyru/1779817727](http://localhost:3000/runs/veyru/1779817727) | launched 2026-05-26 |
| 7 | [veyru/1779817734](http://localhost:3000/runs/veyru/1779817734) | launched 2026-05-26 |
| 8 | [veyru/1779817741](http://localhost:3000/runs/veyru/1779817741) | launched 2026-05-26 |
| 9 | [veyru/1779817748](http://localhost:3000/runs/veyru/1779817748) | launched 2026-05-26 |
| 10 | [veyru/1779817756](http://localhost:3000/runs/veyru/1779817756) | launched 2026-05-26 |

## Launch

Launched by the shared orchestrator [`/tmp/no_swap_baseline_launcher.sh`](file:///tmp/no_swap_baseline_launcher.sh) once the in-flight 2026-05-25 budget=250 multi-swap cohorts complete. Shares sonnet cap=6.

## Evaluation

Same pipeline as the multi-swap cohorts — handled by the same `/tmp/budget250_eval_parallel.sh` + `/tmp/budget250_probe_parallel.sh` (they discover run IDs from all launcher logs).

Comparison appears as a row in [`analysis/budget_comparison_table.py`](../../analysis/budget_comparison_table.py) output.
