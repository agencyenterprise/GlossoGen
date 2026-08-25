# Example notebooks

Read the notebooks in order. Each generates its own simulation with
`glossogen.testing`, so they need **no API key and no network** and can be run in a
fresh clone before you have credentials.

```bash
make install-notebooks   # jupyter, pandas, matplotlib, nbmake
jupyter lab notebooks/
```

| | |
|---|---|
| [01_read_a_run.ipynb](01_read_a_run.ipynb) | The JSONL event log: what a run is made of, one row per message, characters per round, round verdicts |
| [02_score_a_run.ipynb](02_score_a_run.ipynb) | The metric layer through `run_scenario_evaluation`, deterministic metrics and then a judge-backed one against a stub |
| [03_compare_runs.ipynb](03_compare_runs.ipynb) | Two runs differing in one knob, scored the same way, read side by side |
