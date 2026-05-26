# No-swap baseline budget=450 · postmortem in Phase A only — 2026-05-25

## Cohort

- **Variant**: no swaps + postmortem enabled rounds 1-10, then off via `set_postmortem(at_round=11, enabled=False)`
- **Sibling cohorts**:
  - same budget, postmortem always on: [`2026-05-25_no_swap_baseline_pm_always_budget450_sonnet`](../2026-05-25_no_swap_baseline_pm_always_budget450_sonnet/)
  - same pm schedule, budget=250: [`2026-05-25_no_swap_baseline_pm_phase_a_budget250_sonnet`](../2026-05-25_no_swap_baseline_pm_phase_a_budget250_sonnet/)
- **Replicas**: 5 fully independent sonnet runs (`claude-sonnet-4-6`, seed=42, `claude-haiku-4-5-20251001` judge)
- **Rounds**: 40 total, **no swaps**
- **Time budget per round**: 450 s

## Labels applied

```json
["baseline_no_swap", "pm=phase_a_only", "budget=450"]
```

## Runs

| Rep | Run ID | Status |
|---|---|---|
| 1 | [veyru/1779748292](http://localhost:3000/runs/veyru/1779748292) | ✓ ended |
| 2 | [veyru/1779748321](http://localhost:3000/runs/veyru/1779748321) | ✓ ended |
| 3 | [veyru/1779752769](http://localhost:3000/runs/veyru/1779752769) | ✓ ended |
| 4 | ~~veyru/1779755895~~ → [veyru/1779788124](http://localhost:3000/runs/veyru/1779788124) | ended (backfill — original died at r=40 in a `stabilize_veyru` retry loop after 9h wall time; agent never gave up because every round stayed under the 1200s round-duration cap. Deleted via API + relaunched.) |
| 5 | [veyru/1779757819](http://localhost:3000/runs/veyru/1779757819) | ✓ ended |

## Launch

Launched by the shared orchestrator [`/tmp/no_swap_baseline_launcher.sh`](file:///tmp/no_swap_baseline_launcher.sh) once the in-flight 2026-05-25 budget=250 multi-swap cohorts complete. Shares sonnet cap=6.

## Evaluation

Same pipeline as the multi-swap cohorts — handled by the same `/tmp/budget250_eval_parallel.sh` + `/tmp/budget250_probe_parallel.sh` (they discover run IDs from all launcher logs).

Comparison appears as a row in [`analysis/budget_comparison_table.py`](../../analysis/budget_comparison_table.py) output.
