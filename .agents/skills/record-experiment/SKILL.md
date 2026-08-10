---
name: record-experiment
description: Plan, close, audit, or reproduce GlossoGen research experiments with program- and study-scoped, machine-checked Markdown records, exact run provenance, resolved-config and JSONL hashes, fork lineage, costs, and validity gates. Use whenever creating or editing an experiment record, launching or forking a research run, interpreting a completed run, updating a research-program index, or checking whether an earlier result can be replicated.
---

# Record Experiment

Keep experimental decisions human-readable while deriving provenance and run
facts from artifacts. Never infer a completed run from round counts: require a
`simulation_ended` event.

## Keep the research hierarchy explicit

Use four levels. Do not treat them as synonyms:

1. **Research program** — the durable agenda, such as `covenant-game`.
2. **Study** — one broad scientific question or experimental series within the
   program, such as `STUDY-004 — Pledge x personal cost`.
3. **Experiment record** — one preregistered, decision-relevant comparison,
   calibration, pilot, replication, stress test, or ablation.
4. **Run** — one simulation trajectory. Multiple arms, seeds, models, and runs
   can belong to one experiment record.

A GlossoGen scenario is an instrument used by a program; it is not another
level in this hierarchy. Do not open a new experiment record merely because a
new run started. Open one when a new result could trigger a different research
decision.

Use this layout for every structured experiment record:

```text
docs/research/<program>/
├── README.md                         # program summary and study index
├── studies/
│   └── STUDY-NNN-<slug>.md           # broad question and linked experiments
└── experiments/
    ├── README.md                     # experiment index for this program
    └── EXP-NNN-<slug>/
        ├── experiment.md
        ├── configs/                  # immutable launch inputs
        └── analysis/                 # checked result derivations
```

Experiment numbers are scoped to the research program. Cite them as
`<program>/EXP-NNN` when context is not already explicit. Operational campaign
assets may live in repository-root `experiments/`; raw outputs live in `runs/`.
Neither replaces the authoritative record above.

## Choose the workflow

- For a new experiment, follow **Plan before running**.
- For a finished or interrupted run, follow **Close a run**.
- For an existing experiment record, follow **Audit reproducibility**.
- For a replication, audit the source record first, then create a new experiment
  record; do not overwrite the source result.

Read [references/experiment-record-schema.md](references/experiment-record-schema.md)
before creating or changing an experiment record.

## Use the helper

Set the helper path from the skill directory:

```bash
EXPERIMENT_RECORD=.agents/skills/record-experiment/scripts/experiment_record.py
```

The helper is read-only. It renders templates, inspects artifacts, and validates
records to stdout. Apply resulting Markdown changes with the normal file-editing
workflow so the diff remains reviewable.

## Plan before running

1. Resolve the research program, study, and experiment role before assigning an
   ID. Recommended roles include `calibration`, `pilot`, `replication`,
   `stress-test`, `ablation`, `compatibility`, and `confirmatory`.
2. Resolve the next experiment ID from that program's
   `experiments/README.md` and bundled `EXP-*/experiment.md` records. Do not use
   a repository-global counter.
3. Render a skeleton:

   ```bash
   python3 "$EXPERIMENT_RECORD" render-template \
     --experiment-id EXP-022 \
     --research-program covenant-game \
     --study-id STUDY-004 \
     --study-title "Pledge x personal cost" \
     --role pilot \
     --title "Short descriptive title" \
     --repo-root .
   ```

4. For every new experiment, create a self-contained bundle:

   ```text
   docs/research/<program>/experiments/EXP-022-<slug>/
   ├── experiment.md
   ├── configs/          # exact launch inputs owned by this experiment
   └── analysis/         # checked scripts added when results are closed
   ```

   Put the rendered output in `experiment.md`. Copy the exact resolved source
   presets into `configs/` before hashing and launch the run from those bundled
   paths, so later edits to scenario-wide presets cannot change the recorded
   design silently. Do not duplicate secrets or generated run logs in a bundle.
5. Replace every placeholder above `Result` before launching:
   - one decision-relevant question;
   - outcome gates and stopping rules;
   - conditions, controls, invariants, model/provider, seed, rounds, and
     replication unit;
   - exact command, config paths, source run, and fork boundary;
   - intended alignment outcomes and measurements.
6. Add each configuration's current bundle `path`, command-facing
   `launch_path`, and SHA-256 to the embedded `experiment-record:v2` JSON block.
   For new experiments, `path` and `launch_path` are identical. Never store API
   keys, environment values, tokens, or other secrets.
7. Record the current commit. A dirty worktree is allowed for exploration but
   is not fully reproducible; either commit before the run or state explicitly
   that the record is provisional.
8. Link the planned experiment from both the program's experiment index and its
   study document. Keep program, study, role, and experiment ID consistent
   across the Markdown header and machine-readable block.
9. Run `validate-record --phase planned`. Do not launch if it reports errors.

## Close a run

1. Inspect every included and excluded run directly:

   ```bash
   python3 "$EXPERIMENT_RECORD" inspect-run \
     runs/<scenario>/<run-id> --repo-root . --format markdown
   ```

2. Require `completed: true` for any run used in reported outcome metrics. An
   interrupted run may be documented with `included: false`; do not invent its
   API cost.
3. Copy the helper's run facts into the embedded JSON record, including:
   - run directory and role;
   - inclusion status;
   - exact JSONL and resolved-config hashes;
   - model/provider, seed, configured rounds, completion reason, and cost;
   - source run and fork boundary when present.
4. Compute claims from JSONL events or a checked analysis script stored in the
   bundle's `analysis/` directory. Distinguish:
   - observed facts from interpretation;
   - stressor activation from treatment effect;
   - service accuracy from hidden effort/compliance;
   - operational recovery from financial recovery;
   - one trajectory from independent replication.
5. Complete `Result`, `Outcome`, `Validity limitations`, `What it changed`, and
   `Traps found`. Preserve negative and unactivated results.
6. Update the status, close date, cost, and outcome in the program's experiment
   index. Update the study synthesis only with claims supported by closed
   records.
7. Run `validate-record --phase complete`. Resolve errors; retain meaningful
   warnings in `Validity limitations`.

## Audit reproducibility

Run:

```bash
python3 "$EXPERIMENT_RECORD" validate-record \
  docs/research/<program>/experiments/EXP-022-<slug>/experiment.md \
  --repo-root . --phase auto
```

Treat the record as:

- **Design-replicable** when question, conditions, exact commands, configs,
  seeds, model/provider, rounds, and analysis rules are present.
- **Artifact-verifiable** when run logs exist, finish with `simulation_ended`,
  and their hashes match the record.
- **Code-replicable** only when the recorded commit is available and the run was
  made from a clean worktree or a preserved source snapshot.
- **Behaviorally repeatable**, never exactly deterministic, when LLM sampling
  may produce a different trajectory under the same design.

Do not rewrite exact launch commands. Mark unavailable information as a
validity limitation.

## Integrity rules

- Write preregistered decisions before seeing results.
- Keep program, study, experiment record, and run distinct in prose and paths.
- Use one record for one decision-relevant experiment, not one record per run.
- Do not alter earlier gates to make a result look supported.
- Do not report a causal contrast when a stressor did not activate.
- Do not count rounds within one multi-agent trajectory as independent
  replications.
- Record fork semantics precisely, including any replayed boundary round.
- Use resolved run configuration as authoritative over remembered CLI defaults.
- Hash artifacts; do not paste large JSON configs or prompts into the record.
- Launch new experiments from their bundled `configs/` files; scenario-level
  presets may be cited as ancestry, but are not the authoritative launch input.
- Never commit run logs containing secrets without an explicit storage policy.
