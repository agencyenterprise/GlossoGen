# Veyru stabilization-judge validation set

A small, balanced, labeled dataset for checking whether a candidate stabilization
judge (a new prompt, or a new model) gives the right verdicts. Run a candidate
judge over the rows, compare its answer to `is_match`, and measure accuracy /
precision / recall per class.

## Files

| File | Purpose |
|---|---|
| `build_judge_validation_set.py` | Regenerates the CSV from the judge-replay cache. |
| `judge_validation_set.csv` | The dataset: 500 rows, 3 columns. |

## Schema

Three columns only:

| Column | Meaning |
|---|---|
| `expected_input` | The stabilization procedure the engineer had to convey (`expected_actions`). |
| `input` | What the field observer reported (`observer_action`). |
| `is_match` | Reference answer key: `True` if the input correctly performs the expected procedure, else `False`. |

## What `is_match` means and where the rows come from

Every row is sourced from `runs/_judge_replay/pair_cache.jsonl` — the output of
`scripts/replay_veyru_judge.py`, which re-judged (under the **fixed** prompt)
every `(expected, observer)` pair the **original** judge had accepted. The fixed
judge is the reference. The 500 rows are balanced **250 `True` / 250 `False`**,
made of three kinds:

| Kind | Count | `is_match` | How it's labeled |
|---|---|---|---|
| **Agreed match** | 250 | `True` | Both the original and the fixed judge accepted the pair — a confident genuine match. |
| **Flip** | 150 | `False` | The original judge accepted but the fixed judge rejected — a subtle over-acceptance the prompt fix corrected. |
| **Clear-negative** | 100 | `False` | **Synthesized**: a real procedure's `expected_input` paired with a well-formed observer action borrowed from a *clearly different* procedure (low token overlap). The action is natural text but performs the wrong procedure, so it is an unambiguous non-match. |

The clear-negatives exist because the replay cache only contains pairs the old
judge *accepted*, so on its own it has no blatant non-matches — only borderline
ones. The synthesized rows add obvious negatives so a judge can't score well just
by being lenient.

### Caveats

- **Labels are the fixed judge's verdicts, not human-verified gold.** Agreed-match
  and flip labels are high-confidence (two judges agreeing, or a deliberate
  correction), and clear-negatives rely on no judge at all — but if you need
  certified ground truth, spot-check the CSV by hand.
- **No real garbage inputs.** The negatives are either subtle (flips) or
  wrong-procedure (clear-negatives); there are no malformed / empty observer
  actions (those are filtered out).

## Regenerating

The input cache must already exist (see
[docs/judge-replay-and-rerun-pipeline.md](../../docs/judge-replay-and-rerun-pipeline.md),
steps 1–2). Then:

```bash
VIRTUAL_ENV= uv run --no-sync python analysis/judge_validation_set/build_judge_validation_set.py
```

Flags:

- `--per-class N` — number of `True` and of `False` examples each (default 250).
- `--clear-negatives K` — how many of the `False` half are synthesized
  clear-negatives; the rest are real flips (default 100).
- `--output PATH` — where to write the CSV (default: this folder).

Sampling and synthesis are seeded (`SAMPLE_SEED = 42`), so re-running against the
same cache reproduces the same set.
