# Exporting runs

Two exports, both covering any number of runs and neither needing per-scenario code:

- **Raw run folders** — one zip holding the selected runs' directories, for handing to a
  coding agent or archiving.
- **CSV tables** — a flat data frame for R, Pandas, or a journal's supplementary
  materials.

Available from the **Export** button on the runs page, from `glossogen export`, and from
three REST endpoints.

## What the CSV columns are

Column names are prefixed by where they came from, because a scenario is free to declare a
knob called `status` or `perplexity` and those are also a run field and a metric name.

| Prefix | Holds |
|---|---|
| *(none)* | `run_id`, `scenario_name`, and run metadata: status, timestamp, message count, cost, duration, provider, models, labels |
| `knob.` | the run's recorded `scenario_config`, flattened |
| `label.` | labels of the form `key=value`, split out (`budget=800` becomes `label.budget` = `800`) |
| `agent_model.` / `agent_provider.` / `agent_role.` | one column per agent id |
| `lineage.` | where a derived run came from, plus `derivation_type` |
| `metric.` | one column per evaluator |

Neither the knob columns nor the metric columns come from a list anyone maintains. Knobs
come from what each run recorded, metrics from the names its report carries. Add a scenario
or a metric and the export covers it with no change here.

`run_id` and `scenario_name` are always emitted and cannot be deselected, because every
other table joins back on them.

### Knobs of any shape

One rule, no per-knob cases:

- a scalar is its own column
- a mapping is exploded with dotted keys, so `model_overrides` becomes
  `knob.model_overrides.field_observer.model`
- a list becomes one column holding compact JSON

Lists stay whole because the ones that appear have no sane column expansion.
`scheduled_events` varies in length per run, so exploding it by index would invent columns
that mean different things in different rows.

The column set therefore depends on values, not only on top-level keys: two runs of one
scenario whose `model_overrides` name different agents contribute different columns.

## Cells a spreadsheet would misread

Control characters are stripped from text cells, and newlines inside them become spaces.
Both are legal in quoted CSV, and both break line-oriented tools: `wc -l` overcounts and a
naive split lands half a row in the next record.

A cell whose text begins `=`, `+`, `@`, or a tab is prefixed with an apostrophe, which a
spreadsheet reads as "this is text" and does not display. Without it, a real judge note
beginning `@ notation established: '@B' means ...` renders as `#NAME?` and the note is lost
with no indication. A leading `-` is left alone, since it is far more often a negative
number.

## An empty cell is not a zero

**A blank metric cell means no number exists.** Three situations produce it: the metric
decided it did not apply to that run, the metric was never run on it, or the run has no
evaluation report.

**A `0.0` metric cell means the metric ran and counted zero**, which is a real observation
for every metric that counts occurrences (`round_ended_idle`, `content_filter_refusal`,
`neologism`).

Filling blanks with zeros would merge the two and bias any average taken over the column.
To tell the three blank cases apart, read the `has_evaluation` column, and the
`runs_without_report` count on the export preview.

The long tables express the same rule structurally: a row exists per observation a metric
reported, and a metric reports a round only when it has something to say about it. A
missing `(run, metric, round)` row means no observation, not zero.

## The three tables

| Table | Shape |
|---|---|
| `run_level.csv` | one row per run, wide: run context plus one score column per metric |
| `round_level.csv` | one row per run, metric, and round observed |
| `agent_level.csv` | one row per run, metric, and agent observed |

One table comes back as a bare CSV. Two or three come back as a zip, with a
`columns.csv` legend alongside them naming each column's family, its unit, and how many
runs filled it.

The legend is the recoverable half of a blank cell. A knob a scenario never declared and a
knob it declared as null both render empty; the coverage count is the only thing that says
which columns were sparse.

`agent_level.csv` is often just a header. Per-agent numbers are opt-in for a metric and
most do not report them. The per-agent roster is on `run_level.csv` in the `agent_model.*`
columns, so it survives regardless.

`repeat_run_columns` copies the run context onto every row of the long tables, so each row
stands alone with no join back to `run_level.csv`. On by default.

## Selecting runs

Either specific runs or everything matching a filter, never a mix of the two. In the UI
that is a radio button; over the wire it is a tagged union, so there is no precedence rule
to get wrong.

Checking rows in the runs list builds an explicit selection. "Select all loaded" covers
the pages fetched so far, because the list is paginated and virtualized and runs past those
pages have no id on the client yet. Filter mode covers everything matching; it resolves
server-side, where the whole set is known.

## Limits

Three ceilings, each bounding a different thing and measured differently:

| Ceiling | Value | Counts | How |
|---|---|---|---|
| runs per export | 5000 | runs in the selection | before the build |
| raw zip | 4 GiB | the run folders, **uncompressed** | estimated before the build |
| CSV tables | 512 MiB | bytes the **client receives** | counted during the write |

The run ceiling sits above the largest labelled cohort here, so an export of real work is
not refused.

The raw ceiling is deliberately conservative. It sizes the run folders on disk, and the zip
a client receives is smaller: measured across three scenarios here, 5.7x to 7.0x smaller. So
4 GiB of counted bytes is roughly 600 MiB delivered, and some selections a browser could
have held are refused. Sizing before the build is what makes the refusal cheap, since
nothing is compressed to find out.

The CSV ceiling counts what the client receives, compressed inside a zip and raw for a
single CSV. Counting the rows' own bytes would hold the two shapes to wildly different
delivered sizes, because CSV deflates heavily. Row count is a poor stand-in for the same
reason: repeating the run columns onto the long rows is a sixfold difference in uncompressed
bytes and about a fifth in delivered ones, since repetition is exactly what deflate removes.

A single CSV is the one shape where counted equals delivered, so 512 MiB is the size that
ceiling really permits there. One cohort's `round_level.csv` alone reaches 273 MiB, which is
a large object for a browser tab to hold before saving. Anything near that belongs on the
CLI.

The CSV ceiling applies to the REST endpoint only, since `glossogen export` writes to a
directory and holds no table in memory. The raw ceiling does apply to the CLI, because
`--raw` goes through the same writer; `--max-runs` raises the run ceiling locally.

The preview reports all three, so an interface quotes the limit the endpoint enforces
instead of its own copy. Only the raw ceiling comes with an estimate to compare against,
which is why the raw tab can warn before a click and the CSV tab can only name its limit.

Past any ceiling the download refuses, and the message says which limit and what to change.
The preview still answers, so the UI can show the count beside the ceiling instead of an
error.

The archive is built into a temporary file under `TMPDIR`; point that at a larger volume if
the default is small.

## CLI

Reads the runs directory directly, so it needs no server and no database. It covers runs
that were never evaluated and runs still in progress.

```bash
glossogen export --runs-dir ./runs --out ./export \
  --label baseline_oss --label budget=800 \
  --frames run_level,round_level \
  --raw
```

| Flag | Effect |
|---|---|
| `--out DIR` | where to write (required) |
| `--scenario NAME` | only these scenarios (repeatable) |
| `--label LABEL` | only runs carrying every one of these (repeatable) |
| `--run-id-contains SUB` | substring of `scenario/run_dir_name` |
| `--contains-agent-id ID` | only runs that registered this agent |
| `--status STATE` | only runs in one state, e.g. `scenario_complete` to skip crashed runs |
| `--run-id ID` | exactly these runs (repeatable); cannot be combined with any filter flag |
| `--frames` | which tables, comma-separated |
| `--include-metric-summaries` | add each metric's unit and summary text |
| `--no-repeat-run-columns` | keep the long tables narrow |
| `--raw` | also write `runs.zip` |
| `--include-logs` | keep debug and stdout logs in that zip |
| `--max-runs N` | override the 5000-run ceiling |

Every column and metric available for the selection is included; the flags trim tables, not
columns. Use the REST endpoint to pick columns.

## REST

All three are POSTs, because a selection can carry hundreds of run ids and a column list a
hundred keys, which is more than a query string reliably holds.

| Endpoint | Returns |
|---|---|
| `POST /api/g/{slug}/runs/export/preview` | JSON: run count, scenarios, available columns and metrics with per-column coverage, row counts per metric, and the limits |
| `POST /api/g/{slug}/runs/export/csv` | one CSV, or a zip of tables plus the legend |
| `POST /api/g/{slug}/runs/export/raw` | zip of the run folders |

The preview and the downloads share one selection model, so the preview describes what the
download produces, with no approximation in between. Both are computed from the same records.

```bash
curl -X POST "$API/api/g/local/runs/export/csv" -H 'content-type: application/json' -d '{
  "selection": {"kind":"filters","scenario":["veyru"],"labels":["baseline_oss"],
                "run_id_contains":null,"status":null},
  "frames": ["run_level"],
  "columns": ["status","knob.round_count","label.budget"],
  "metrics": ["round_success","mean_chars_per_round"],
  "repeat_run_columns": false,
  "include_metric_summaries": false
}' -o run_level.csv
```

An explicit id that no longer resolves shows up on the preview, and a download refuses it
with a 404. Refusing is the safer failure here, because a table with one row fewer than
asked for looks exactly like a correct one. The modal closes most of that gap: it drops such
ids from the request and reports how many it dropped, leaving the 404 for a run deleted
between the preview and the download.

## What the raw zip holds

Each run nests under `{scenario_name}/{run_dir_name}/`, so extracting at `runs/` reproduces
the layout. A `manifest.csv` at the root names what went in.

Debug and stdout logs are left out by default, since a run's `_debug.jsonl` is routinely
larger than the event log; `--include-logs` or the modal checkbox puts them back.
`stream.json` and `eval_in_progress.json` are always left out: they describe work in
flight, so a re-imported run carrying them reads as still running.

A run still being written is safe to export. Members are streamed into the archive rather
than pre-declaring a size, so a JSONL that grows mid-read does not corrupt its entry.

## Not covered here

A long-format **events** CSV, one row per message or tool call with the ground-truth
meaning behind it, needs a scenario contract for declaring that meaning. Until that exists
it cannot be scenario-agnostic, so it is tracked separately.
