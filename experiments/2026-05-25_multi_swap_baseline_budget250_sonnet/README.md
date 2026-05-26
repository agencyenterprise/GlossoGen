# Multi-swap baseline budget=250 — 2026-05-25

## Cohort

- **Variant**: postmortem-off after r=11 (`set_postmortem(at_round=11, enabled=False)`)
- **Sibling cohort**: [`2026-05-25_multi_swap_baseline_postmortem_on_budget250_sonnet`](../2026-05-25_multi_swap_baseline_postmortem_on_budget250_sonnet/)
- **Budget=450 sibling**: [`2026-05-22_multi_swap_baseline_sonnet`](../2026-05-22_multi_swap_baseline_sonnet/)
- **Replicas**: 10 fully independent sonnet runs (`claude-sonnet-4-6`, seed=42, `claude-haiku-4-5-20251001` judge)
- **Rounds**: 40 total, swaps at r=11 (field_observer), r=21 (stabilization_engineer), r=31 (field_observer)
- **Time budget per round**: 250 s (vs 450 s in the sibling cohort)
- **Channel visibility on swap**: `from_round=10` (each swap-in sees only the previous phase's history)

## Labels applied

```json
["multi_swap_baseline", "budget=250", "phases=A10-B10-C10-D10", "history=10"]
```

## Runs

| Rep | Run ID | Launched | Status |
|---|---|---|---|
| 1 | [veyru/1779729181](http://localhost:3000/runs/veyru/1779729181) | 14:13:02 | ✓ ended |
| 2 | [veyru/1779729189](http://localhost:3000/runs/veyru/1779729189) | 14:13:09 | ✓ ended |
| 3 | [veyru/1779729196](http://localhost:3000/runs/veyru/1779729196) | 14:13:16 | ✓ ended |
| 4 | [veyru/1779731548](http://localhost:3000/runs/veyru/1779731548) | 14:52:28 | ✓ ended |
| 5 | [veyru/1779733810](http://localhost:3000/runs/veyru/1779733810) | 15:30:10 | ✓ ended |
| 6 | [veyru/1779734089](http://localhost:3000/runs/veyru/1779734089) | 15:34:50 | ✓ ended |
| 7 | [veyru/1779736351](http://localhost:3000/runs/veyru/1779736351) | 16:12:31 | ✓ ended |
| 8 | [veyru/1779737170](http://localhost:3000/runs/veyru/1779737170) | 16:26:10 | ✓ ended |
| 9 | [veyru/1779738861](http://localhost:3000/runs/veyru/1779738861) | 16:54:22 | in-flight |
| 10 | [veyru/1779740972](http://localhost:3000/runs/veyru/1779740972) | 17:29:33 | in-flight |

## Launch

```bash
nohup bash experiments/2026-05-25_multi_swap_baseline_budget250_sonnet/launch.sh \
  > /tmp/multi_swap_baseline_budget250_sonnet.stdout 2>&1 &
disown
```

Shared the sonnet cap=6 with the sibling postmortem-on launcher.

## Evaluation

After sims complete, run probes:

```bash
for c in 1 2 3; do
  nohup bash /tmp/budget250_probe_parallel.sh "$c" 3 > "/tmp/budget250_probe_${c}.stdout" 2>&1 &
  disown
done
```

Then build the comparison table:

```bash
VIRTUAL_ENV= uv run --no-sync python analysis/budget_comparison_table.py
```
