# Multi-swap baseline budget=250 · postmortem-always-on — 2026-05-25

## Cohort

- **Variant**: postmortem stays enabled through all 4 phases (no `set_postmortem` event in `scheduled_events`)
- **Sibling cohort**: [`2026-05-25_multi_swap_baseline_budget250_sonnet`](../2026-05-25_multi_swap_baseline_budget250_sonnet/)
- **Budget=450 sibling**: [`2026-05-22_multi_swap_baseline_postmortem_on_sonnet`](../2026-05-22_multi_swap_baseline_postmortem_on_sonnet/)
- **Replicas**: 10 fully independent sonnet runs (`claude-sonnet-4-6`, seed=42, `claude-haiku-4-5-20251001` judge)
- **Rounds**: 40 total, swaps at r=11 (field_observer), r=21 (stabilization_engineer), r=31 (field_observer)
- **Time budget per round**: 250 s (vs 450 s in the sibling cohort)
- **Channel visibility on swap**: `from_round=10` (each swap-in sees only the previous phase's history)

## Labels applied

```json
["multi_swap_baseline_postmortem_on", "budget=250", "phases=A10-B10-C10-D10", "history=10"]
```

## Runs

| Rep | Run ID | Launched | Status |
|---|---|---|---|
| 1 | [veyru/1779729182](http://localhost:3000/runs/veyru/1779729182) | 14:13:03 | ✓ ended |
| 2 | [veyru/1779729190](http://localhost:3000/runs/veyru/1779729190) | 14:13:10 | ✓ ended |
| 3 | ~~veyru/1779729197~~ → [veyru/1779742230](http://localhost:3000/runs/veyru/1779742230) | 14:13:17 (killed at r=24 from `read_notifications` retry loop) → replaced via DELETE+CLI relaunch at 17:50 | in-flight (backfill) |
| 4 | [veyru/1779732962](http://localhost:3000/runs/veyru/1779732962) | 15:16:02 | ✓ ended |
| 5 | [veyru/1779733840](http://localhost:3000/runs/veyru/1779733840) | 15:30:40 | ✓ ended |
| 6 | [veyru/1779734090](http://localhost:3000/runs/veyru/1779734090) | 15:34:51 | ✓ ended |
| 7 | [veyru/1779736442](http://localhost:3000/runs/veyru/1779736442) | 16:14:02 | in-flight |
| 8 | [veyru/1779738253](http://localhost:3000/runs/veyru/1779738253) | 16:44:14 | in-flight |
| 9 | [veyru/1779739193](http://localhost:3000/runs/veyru/1779739193) | 16:59:54 | in-flight |
| 10 | [veyru/1779741034](http://localhost:3000/runs/veyru/1779741034) | 17:30:34 | in-flight |

## Launch

```bash
nohup bash experiments/2026-05-25_multi_swap_baseline_postmortem_on_budget250_sonnet/launch.sh \
  > /tmp/multi_swap_baseline_postmortem_on_budget250_sonnet.stdout 2>&1 &
disown
```

Shared the sonnet cap=6 with the sibling postmortem-off launcher.

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
