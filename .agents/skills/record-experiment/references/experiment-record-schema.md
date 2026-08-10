# Experiment record schema

## Research hierarchy

Every structured record belongs to exactly one research program and one study:

```text
research program -> study -> experiment record -> run
```

- A **research program** is a durable agenda.
- A **study** is one broad scientific question or experimental series.
- An **experiment record** preregisters one decision-relevant design.
- A **run** is one trajectory; several runs can implement one record.

The scenario is recorded in `Design` as the experimental instrument. It does
not determine the program or study boundary. Use a new experiment record when
the result can change a research decision, not for every run.

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

## Bundle layout

Structured records live in an experiment-owned directory within their program:

```text
docs/research/<program>/
├── README.md
├── studies/
│   └── STUDY-NNN-slug.md
└── experiments/
    ├── README.md
    └── EXP-NNN-slug/
        ├── experiment.md
        ├── configs/
        └── analysis/
```

`configs/` contains the exact immutable launch inputs for every arm. Whenever a
command names a config explicitly, it must use the corresponding `launch_path`,
not an unrecorded mutable preset; `path` locates the current bundled copy.
`analysis/` contains any checked script used to derive reported claims. Empty
`analysis/` directories need not be committed.

Experiment IDs are scoped to the program. Use `<program>/EXP-NNN` as the fully
qualified reference outside the program's own documents.

## Human-readable classification

Place these fields after the dates and before the machine-readable block:

```markdown
**Research program:** covenant-game
**Study:** STUDY-004 — Pledge × personal cost
**Role:** pilot
```

Recommended roles are `calibration`, `pilot`, `replication`, `stress-test`,
`ablation`, `compatibility`, and `confirmatory`. Use another concise role only
when none describes the decision the record supports.

## Machine-readable block

Every machine-checked record uses schema version 2. Place one JSON block after
the classification fields and before `Question`:

```markdown
<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-004",
  "experiment_role": "pilot",
  "experiment_id": "EXP-022",
  "base_commit": "<40-character Git SHA>",
  "worktree_dirty": false,
  "commands": ["<exact command without secrets>"],
  "configs": [
    {
      "path": "docs/research/<program>/experiments/EXP-022-slug/configs/arm.json",
      "launch_path": "docs/research/<program>/experiments/EXP-022-slug/configs/arm.json",
      "sha256": "<64 hex>"
    }
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

The block is provenance and classification, not interpretation. Keep paths
repository-relative. `path` locates the immutable artifact now;
`launch_path` is the path appearing in the exact command. They are identical
for a newly planned experiment. Keeping both fields preserves an exact command
if documentation is moved later without introducing another schema variant.
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

For fresh runs without a standalone `config.json`, the helper hashes the
canonical `simulation_started.scenario_config` object and identifies it with
the selector `<event-log>#simulation_started.scenario_config`. This is the
authoritative resolved configuration, including defaults that were absent from
the source launch file.

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

Keep the program's `experiments/README.md` synchronized and link the record from
its study document:

```markdown
| [EXP-022](EXP-022-slug/experiment.md) | short experiment name | planned | pending | — |
```

On closure, update status, concise outcome, and cost. Do not include costs from
interrupted runs unless a canonical final-cost event exists.
