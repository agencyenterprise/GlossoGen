# Example notebooks

Three notebooks, in order. Each one generates its own simulation with
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

## Why they generate their own run

The alternative is committing a run, or asking the reader to make one first. A
committed run goes stale against the event schema and cannot be re-generated; a
reader without keys is stuck at the first cell.

`run_rounds` avoids both. It drives the real round loop, with the real MCP server,
game clock, world and event logger, and replaces only the model with a script. So
the events these notebooks read are produced by the same code paths a paid run
uses, deterministically and for free.

What that costs in realism is worth stating: scripted agents send fixed text, so
every plot here is flatter than a real one and no language finding can appear. The
notebooks say so where it matters. They teach the shape of the data and the API,
not what agents do under pressure.

## They are executed in CI

`make test-notebooks` runs every cell top to bottom and fails on the first one that
raises, and a CI job does the same on every PR. A notebook that drifts out of date
with the platform fails rather than sitting there looking finished.

Commit them without outputs. The diff of a re-executed notebook is otherwise mostly
regenerated output, which buries the change that was actually made.
