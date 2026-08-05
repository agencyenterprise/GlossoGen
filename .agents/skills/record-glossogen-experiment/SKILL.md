---
name: record-glossogen-experiment
description: Plan, close, audit, or reproduce GlossoGen experiments with machine-checked Markdown records, exact run provenance, resolved-config and JSONL hashes, fork lineage, costs, and validity gates. Use whenever creating or editing docs/experiments/EXP-*.md, launching or forking a research run, interpreting a completed run, updating the experiment index, or checking whether an earlier result can be replicated.
---

# Record GlossoGen Experiment

Keep experimental decisions human-readable while deriving provenance and run
facts from artifacts. Never infer a completed run from round counts: require a
`simulation_ended` event.

## Choose the workflow

- For a new experiment, follow **Plan before running**.
- For a finished or interrupted run, follow **Close a run**.
- For an existing `EXP-*.md`, follow **Audit reproducibility**.
- For a replication, audit the source record first, then create a new experiment
  record; do not overwrite the source result.

Read [references/experiment-record-schema.md](references/experiment-record-schema.md)
before creating or changing an experiment record.

## Use the helper

Set the helper path from the skill directory:

```bash
EXPERIMENT_RECORD=.agents/skills/record-glossogen-experiment/scripts/experiment_record.py
```

The helper is read-only. It renders templates, inspects artifacts, and validates
records to stdout. Apply resulting Markdown changes with the normal file-editing
workflow so the diff remains reviewable.

## Plan before running

1. Resolve the next experiment ID from `docs/experiments/README.md` and existing
   `EXP-*.md` files.
2. Render a skeleton:

   ```bash
   python3 "$EXPERIMENT_RECORD" render-template \
     --experiment-id EXP-018 \
     --title "Short descriptive title" \
     --repo-root .
   ```

3. Create `docs/experiments/EXP-018-<slug>.md` from the rendered output.
4. Replace every placeholder above `Result` before launching:
   - one decision-relevant question;
   - outcome gates and stopping rules;
   - conditions, controls, invariants, model/provider, seed, rounds, and
     replication unit;
   - exact command, config paths, source run, and fork boundary;
   - intended alignment outcomes and measurements.
5. Add configuration file paths and SHA-256 values to the embedded
   `experiment-record:v1` JSON block. Never store API keys, environment values,
   tokens, or other secrets.
6. Record the current commit. A dirty worktree is allowed for exploration but
   is not fully reproducible; either commit before the run or state explicitly
   that the record is provisional.
7. Add the planned experiment to `docs/experiments/README.md`.
8. Run `validate-record --phase planned`. Do not launch if it reports errors.

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
4. Compute claims from JSONL events or a checked analysis script. Distinguish:
   - observed facts from interpretation;
   - stressor activation from treatment effect;
   - service accuracy from hidden effort/compliance;
   - operational recovery from financial recovery;
   - one trajectory from independent replication.
5. Complete `Result`, `Outcome`, `Validity limitations`, `What it changed`, and
   `Traps found`. Preserve negative and unactivated results.
6. Update the status, close date, cost, and outcome in
   `docs/experiments/README.md`.
7. Run `validate-record --phase complete`. Resolve errors; retain meaningful
   warnings in `Validity limitations`.

## Audit reproducibility

Run:

```bash
python3 "$EXPERIMENT_RECORD" validate-record \
  docs/experiments/EXP-018-<slug>.md --repo-root . --phase auto
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

Do not silently repair historical provenance. Mark unavailable information as a
validity limitation.

## Integrity rules

- Write preregistered decisions before seeing results.
- Do not alter earlier gates to make a result look supported.
- Do not report a causal contrast when a stressor did not activate.
- Do not count rounds within one multi-agent trajectory as independent
  replications.
- Record fork semantics precisely, including any replayed boundary round.
- Use resolved run configuration as authoritative over remembered CLI defaults.
- Hash artifacts; do not paste large JSON configs or prompts into the record.
- Never commit run logs containing secrets without an explicit storage policy.
