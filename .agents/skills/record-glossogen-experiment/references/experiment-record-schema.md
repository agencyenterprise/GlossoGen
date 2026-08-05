# Experiment record schema

## Required Markdown sections

Every record must contain these headings in order:

1. `Question`
2. `Expected decision`
3. `Design`
4. `Outcomes inspected`
5. `Provenance`
6. `Result`
7. `Outcome`
8. `Validity limitations`
9. `What it changed`
10. `Traps found`

Write `Question`, `Expected decision`, `Design`, `Outcomes inspected`, and the
planned portion of `Provenance` before running. Complete the remaining sections
only from artifacts.

## Machine-readable block

Place one JSON block after the dates and before `Question`:

```markdown
<!-- experiment-record:v1
{
  "schema_version": 1,
  "experiment_id": "EXP-018",
  "base_commit": "<40-character Git SHA>",
  "worktree_dirty": false,
  "commands": ["<exact command without secrets>"],
  "configs": [
    {"path": "path/from/repo/root.json", "sha256": "<64 hex>"}
  ],
  "runs": [
    {
      "role": "treatment",
      "included": true,
      "run_dir": "runs/scenario/id",
      "event_log_sha256": "<64 hex>",
      "resolved_config_sha256": "<64 hex>",
      "completed": true,
      "total_cost_usd": 1.23
    }
  ]
}
-->
```

The block is provenance, not interpretation. Keep paths repository-relative.
Use one run entry for every run mentioned in quantitative results. Mark failed,
interrupted, smoke, or excluded runs with `included: false` and a `reason`.

## Provenance requirements

Record:

- base commit and whether the worktree was dirty;
- exact launch or resume command;
- source config and override hashes;
- resolved config and event-log hashes for each run;
- model, provider, seed, rounds, and replica definition;
- source run, rewind boundary, replayed boundary round, and replacement details;
- completion reason and exact API cost from `simulation_ended`;
- analysis script or event-selection rule used for each reported number.

If the worktree was dirty, the commit alone cannot reproduce the code. Preserve
a source snapshot or explicitly classify the result as not code-replicable.

## Outcome vocabulary

- `supported`: the preregistered gate activated and passed.
- `not supported`: the gate activated and failed.
- `inconclusive`: the gate, measurement opportunity, or replication evidence
  was insufficient.
- `invalid`: execution or instrumentation prevents use of the run.
- `unactivated`: the intended stressor did not occur; never relabel this as
  successful containment.

## Index row

Keep `docs/experiments/README.md` synchronized:

```markdown
| [EXP-018](EXP-018-slug.md) | short experiment name | planned | pending | — |
```

On closure, update status, concise outcome, and cost. Do not include costs from
interrupted runs unless a canonical final-cost event exists.
