# No-swap baseline budget=250 · postmortem in Phase A only — 2026-05-25

## Cohort

- **Variant**: no swaps + postmortem enabled rounds 1-10, then off via `set_postmortem(at_round=11, enabled=False)`
- **Sibling cohorts**:
  - same budget, postmortem always on: [`2026-05-25_no_swap_baseline_pm_always_budget250_sonnet`](../2026-05-25_no_swap_baseline_pm_always_budget250_sonnet/)
  - same pm schedule, budget=450: [`2026-05-25_no_swap_baseline_pm_phase_a_budget450_sonnet`](../2026-05-25_no_swap_baseline_pm_phase_a_budget450_sonnet/)
- **Replicas**: 10 fully independent sonnet runs (`claude-sonnet-4-6`, seed=42, `claude-haiku-4-5-20251001` judge) — initial 5 (reps 1–5) plus a 5-rep backfill on 2026-05-26 to reach n=10 for the budget=250 baseline comparison
- **Rounds**: 40 total, **no swaps**
- **Time budget per round**: 250 s

## Labels applied

```json
["baseline_no_swap", "pm=phase_a_only", "budget=250"]
```

## Runs

| Rep | Run ID | Status |
|---|---|---|
| 1 | [veyru/1779748306](http://localhost:3000/runs/veyru/1779748306) | ✓ ended |
| 2 | [veyru/1779751972](http://localhost:3000/runs/veyru/1779751972) | ✓ ended |
| 3 | [veyru/1779753025](http://localhost:3000/runs/veyru/1779753025) | ✓ ended |
| 4 | [veyru/1779756902](http://localhost:3000/runs/veyru/1779756902) | ✓ ended |
| 5 | [veyru/1779761532](http://localhost:3000/runs/veyru/1779761532) | ✓ ended |
| 6 | [veyru/1779825433](http://localhost:3000/runs/veyru/1779825433) | ✓ ended (backfill) |
| 7 | [veyru/1779825441](http://localhost:3000/runs/veyru/1779825441) | ✓ ended (backfill) |
| 8 | [veyru/1779825449](http://localhost:3000/runs/veyru/1779825449) | ✓ ended (backfill) |
| 9 | [veyru/1779834418](http://localhost:3000/runs/veyru/1779834418) | launched 2026-05-26 (replaces deleted 1779825417, too slow) |
| 10 | [veyru/1779834426](http://localhost:3000/runs/veyru/1779834426) | launched 2026-05-26 (replaces deleted 1779825425, too slow) |

## Launch

Launched by the shared orchestrator [`/tmp/no_swap_baseline_launcher.sh`](file:///tmp/no_swap_baseline_launcher.sh) once the in-flight 2026-05-25 budget=250 multi-swap cohorts complete. Shares sonnet cap=6.

## Evaluation

Same pipeline as the multi-swap cohorts — handled by the same `/tmp/budget250_eval_parallel.sh` + `/tmp/budget250_probe_parallel.sh` (they discover run IDs from all launcher logs).

Comparison appears as a row in [`analysis/budget_comparison_table.py`](../../analysis/budget_comparison_table.py) output.
