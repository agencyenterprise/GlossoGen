# Experiment log

One file per experiment. Entries are written **before** the run (question,
expected decision, design) and completed after it. Negative and inconclusive
results are recorded with the same care as positive ones — an experiment that
rules something out saves the next person from repeating it.

## Index

| ID | Experiment | Status | Outcome | Cost |
|---|---|---|---|---|
| [EXP-001](EXP-001-c0-calibration.md) | bonded_counter C0 — strategic calibration | complete | supported | $8.85 |
| [EXP-002](EXP-002-c1-no-covenant.md) | bonded_counter C1 — no covenant (control) | complete | supported, with two design problems found | $18.44 |
| [EXP-003](EXP-003-c2-full-covenant.md) | bonded_counter C2 — full covenant (treatment) | complete | changes behaviour; **not supported** that it improves any alignment outcome | $10.92 |

Total API spend logged: **$38.21** (plus $0.73 in phase-4 smoke tests not logged
individually).

**Cycle 1 is closed.** C0 → C1 → C2 on `gpt-5.4`, seed 42, one replica each. The
pivot criterion that fired is recorded in EXP-003: C2 differs from C1 only in
effort and cost, never in an alignment property, because one paid count yields
certainty and leaves the covenant no problem to solve.

## Template

Copy this for a new entry. Fill everything above `Result` **before launching**.

```markdown
# EXP-NNN — <title>

**Status:** planned | running | complete | invalid
**Date opened:** YYYY-MM-DD
**Date closed:** YYYY-MM-DD

## Question
What this experiment decides. One sentence.

## Expected decision
What we will do differently depending on how it comes out. Written before the
run, so the result cannot retro-fit the question.

## Design
Scenario, condition, the knobs that differ from the comparison arm, model,
provider, seed, rounds, replicas. State what is held constant.

## Provenance
- Commit: `<sha>` — `<subject>`
- Config: path to the preset, plus any inline overrides verbatim
- Runs: run directory paths

## Result
The numbers. No interpretation in this section.

## Outcome
supported | not supported | inconclusive

## Validity limitations
What this run cannot establish. Replica count, model coverage, seeds, ceilings,
confounds.

## What it changed
What we do differently because of this. If nothing changed, say so and say why —
either the question was not decision-relevant, or the result was ignored.

## Traps found
Things that broke, misled, or cost time. The field with the highest long-run
value: it is what stops the same mistake twice.
```

## Conventions

- **Canonical seed is 42** across matched arms, so the case sequence and audit
  draws are identical and replicas measure model stochasticity on the same
  workload.
- **Do not treat a single replica as evidence of stability.** 15 rounds is one
  trajectory of four interacting agents, not 15 independent observations. The
  independent unit is the run.
- **Only `simulation_ended` means a run finished.** Round counts do not.
- Run directories are gitignored. Paths recorded here are the pointer to the raw
  data on the machine that produced it; the JSONL event log is the canonical
  record and every number in these entries is recomputable from it.

## Recalibration budget

Adopted after EXP-002 to prevent open-ended tuning of an environment until it
produces a desired result:

1. Finish the current condition set (C0, C1, C2).
2. Allow **at most one** significant environment revision.
3. If a ceiling, absent measurement opportunities, or C1 ≈ C2 persist after that
   revision, pivot the scenario.
4. Record the reason for the pivot **before** starting the next scenario.
