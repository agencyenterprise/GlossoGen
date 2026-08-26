# Example export data

Real exports, committed so [04_analyze_an_export.ipynb](../04_analyze_an_export.ipynb)
runs without a runs directory. Every file is exactly what `glossogen export`
wrote; nothing was edited afterwards.

The cohort is veyru's `baseline_oss` sweep: `meta-llama/Llama-3.3-70B-Instruct`
and `Qwen/Qwen3-32B` crossed with `round_time_budget_seconds` in
{150, 250, 450, 800, 2000} and `postmortem_enabled` on and off, 15 rounds per
run at `seed=42`, judged by `claude-haiku-4-5-20251001`. Two replicas per cell
were selected by run id, the earliest two completed runs of each, 40 in total.

## `veyru_baseline_oss/`

`run_level.csv`, `round_level.csv`, `agent_level.csv` and the `columns.csv`
legend for the 40-run cohort:

```bash
glossogen export --runs-dir <runs> --out veyru_baseline_oss \
  --frames run_level,round_level,agent_level --no-repeat-run-columns \
  --run-id veyru/1780595722 --run-id veyru/1781093735 --run-id veyru/1780571887 \
  --run-id veyru/1780572066 --run-id veyru/1781098190 --run-id veyru/1781098198 \
  --run-id veyru/1780591851 --run-id veyru/1780592371 --run-id veyru/1780597225 \
  --run-id veyru/1781088778 --run-id veyru/1780576077 --run-id veyru/1780576803 \
  --run-id veyru/1780598642 --run-id veyru/1781085906 --run-id veyru/1780578775 \
  --run-id veyru/1780580283 --run-id veyru/1780602168 --run-id veyru/1780665907 \
  --run-id veyru/1777920823 --run-id veyru/1780585532 --run-id veyru/1781095644 \
  --run-id veyru/1781096024 --run-id veyru/1781086390 --run-id veyru/1781090859 \
  --run-id veyru/1781083391 --run-id veyru/1781083394 --run-id veyru/1780571883 \
  --run-id veyru/1781084463 --run-id veyru/1781083378 --run-id veyru/1781085124 \
  --run-id veyru/1781083377 --run-id veyru/1781083400 --run-id veyru/1781083385 \
  --run-id veyru/1781099000 --run-id veyru/1781086773 --run-id veyru/1781090715 \
  --run-id veyru/1781083399 --run-id veyru/1781091018 --run-id veyru/1780571879 \
  --run-id veyru/1781083398
```

## `veyru_baseline_oss_messages/`

`message_level.csv`, `round_context.csv` and their `columns.csv` for two Llama
runs from the same cohort, budgets 150 and 2000 with the postmortem on. These
frames read event logs, so they are exported per run rather than per cohort:

```bash
glossogen export --runs-dir <runs> --out veyru_baseline_oss_messages \
  --frames message_level,round_context --no-repeat-run-columns \
  --run-id veyru/1781086390 --run-id veyru/1780571883
```

The metric columns carry the names the runs' reports recorded, which is the
research checkout's registry at evaluation time, not this repository's. That is
the export working as designed: metric columns come from each report, not from
a maintained list.
