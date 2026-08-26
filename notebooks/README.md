# Example notebooks

Read the notebooks in order. The first three generate their own simulation with
`glossogen.testing`; the fourth reads committed CSVs exported from a real cohort.
None needs **an API key or the network**, so all four run in a fresh clone before
you have credentials.

```bash
make install-notebooks   # jupyter, pandas, matplotlib, nbmake
jupyter lab notebooks/
```

| | |
|---|---|
| [01_read_a_run.ipynb](01_read_a_run.ipynb) | The JSONL event log: what a run is made of, one row per message, characters per round, round verdicts |
| [02_score_a_run.ipynb](02_score_a_run.ipynb) | The metric layer through `run_scenario_evaluation`, deterministic metrics and then a judge-backed one against a stub |
| [03_compare_runs.ipynb](03_compare_runs.ipynb) | Two runs differing in one knob, scored the same way, read side by side |
| [04_analyze_an_export.ipynb](04_analyze_an_export.ipynb) | The export CSVs read in pandas: a real 40-run budget sweep, one plot per table, the empty-versus-zero rule in the data |

The example CSVs under `data/` are real exports; [data/README.md](data/README.md)
records the cohort and the commands that produced them.
