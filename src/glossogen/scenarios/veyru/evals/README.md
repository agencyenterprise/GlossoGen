# Veyru stabilization-judge accuracy eval

Measures how well the **stabilization judge** (`stabilization_judge.py`) classifies
observer actions, by comparing the live judge's `match` verdict against a
human-curated golden label set.

## Files

- `veyru_judge_golden_labels.tsv` — 500 golden samples (tab-separated). Columns:
  | column | meaning |
  |---|---|
  | `expected_input` | ground-truth stabilization procedure handed to the judge |
  | `input` | observer action under test (what the judge classifies) |
  | `is_match` | the current judge's actual verdict (for reference) |
  | `expected_match` | **golden label** — the correct verdict; the scoring target |
  | `split_vote` | `TRUE` if the golden label came from a 2-1 (non-unanimous) labeling vote — i.e. a borderline case |
  | `explanation` | justification, populated only on rows where `expected_match` differs from `is_match` |
- `judge_accuracy_eval.py` — the Inspect AI eval.

## How the golden labels were generated

The `expected_input`, `input`, and `is_match` columns came from a live capture of
the running judge: each row is a real `(expected procedure, observer action)`
pair fed to the stabilization judge, with `is_match` recording the judge's actual
verdict at capture time.

The `expected_match`, `split_vote`, and `explanation` columns are the
human-curated ground truth, produced as follows:

1. **Triple-pass majority vote.** Every row was independently re-classified
   three times by an LLM applying the judge's own rubric (the "naive-reader"
   test from `prompts/stabilization_judge.jinja`) from scratch, ignoring the
   existing `is_match`. For each row:
   - `expected_match` = the majority verdict across the three passes.
   - `split_vote` = `TRUE` when the three passes were not unanimous (a 2-1
     vote), marking the row as borderline. 33 of 500 rows are split votes.
   - `explanation` = a one-sentence justification, written only for rows where
     the golden `expected_match` ended up disagreeing with the captured
     `is_match` (i.e. rows where the judge looks wrong).
2. **Manual adjudication of stable disagreements.** Rows where the judge
   *consistently* (across repeated runs) disagreed with the golden label were
   re-reviewed by hand. Where the judge was right and the majority vote was
   wrong, the golden was corrected and its `explanation` rewritten to record the
   override (e.g. row 51). Most stable disagreements were left as-is — they are
   genuine judge over-rejections, which is the judge's dominant failure mode.

The net result: `expected_match` reflects the *correct* classification a careful
reviewer would assign, which on this dataset trends slightly more lenient than
the live judge on synonym/paraphrase matches. `split_vote=TRUE` rows are where
"correct" is most contestable and warrant the most scrutiny — hence the separate
`accuracy_split` metric below.

## How it works

The eval bypasses Inspect's model interface: a custom solver calls the project's
own `judge_stabilization(...)` per sample (using the project's `LLMProvider`),
and a custom scorer compares the judge's `TRUE`/`FALSE` verdict to the golden
`expected_match`. Inspect's `--model` is therefore just a placeholder
(`mockllm/model`) — it is never actually queried.

Metrics:
- `accuracy` / `stderr` — overall agreement with the golden labels.
- `accuracy_unanimous` — accuracy over rows labeled by a unanimous vote.
- `accuracy_split` — accuracy over the 33 borderline (split-vote) rows.

## Running

Requires `ANTHROPIC_API_KEY` (read from `.env`). Install the eval dependency group:

```bash
VIRTUAL_ENV= uv sync --group eval
```

Then run:

```bash
VIRTUAL_ENV= uv run --no-sync inspect eval \
  src/glossogen/scenarios/veyru/evals/judge_accuracy_eval.py \
  --model mockllm/model
```

Useful flags: `--limit N` (first N samples), `--max-samples K` (concurrency),
`--epochs N` (run each sample N times).
View results with `inspect view`.

The judge model/provider default to the canonical judge
(`claude-haiku-4-5-20251001` / `anthropic`); override with `VEYRU_JUDGE_MODEL`
and `VEYRU_JUDGE_PROVIDER`.
