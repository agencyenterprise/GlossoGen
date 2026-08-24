# Exporting runs

Two exports, both covering any number of runs and neither needing per-scenario
code:

- **CSV tables** — a flat data frame for R, Pandas, or a journal's supplementary
  materials.
- **Raw run folders** — one zip holding the selected runs' directories, for
  handing to a coding agent or archiving.

Available from the **Export** button on the runs page, from `glossogen export`,
and from three REST endpoints. To chart the same numbers instead of exporting
them, see [analysis and dashboards](analysis.md).

## The tables

| Table | One row per | In the default set |
|---|---|---|
| `run_level.csv` | run | yes |
| `round_level.csv` | run and round | yes |
| `agent_level.csv` | run and agent | yes |
| `message_level.csv` | message | no, reads event logs |
| `round_context.csv` | run and round, one column per agent's briefing | no, reads event logs |

Every table is wide in metrics: a metric is a column, never a value in a
`metric_name` column. A round row carries every metric measured on that round
side by side, so a model can be fitted to it directly.

One table comes back as a bare CSV. Two or more come back as a zip with a
`columns.csv` legend naming each column's family, its unit, and how many runs
filled it. That coverage count matters because a blank is ambiguous: a knob a
scenario never declared and a knob it declared as null both render empty. The
legend is what says which columns were sparse.

`agent_level.csv` is keyed on the run's registered agents rather than on what
the metrics reported. It is the roster of who ran under which model even when no
metric has a per-agent number to add.

`repeat_run_columns` copies the run context onto every row of the round, agent
and message tables, so each row stands alone without a join back to
`run_level.csv`. On by default.

### Column prefixes

Column names are prefixed by where they came from, because a scenario is free to
declare a knob called `status` or `perplexity`, and those are also a run field
and a metric name.

| Prefix | Holds |
|---|---|
| *(none)* | `run_id`, `scenario_name`, and run metadata: status, timestamp, message count, cost, duration, provider, models, labels, `model_class` |
| `knob.` | the run's recorded `scenario_config`, flattened |
| `label.` | labels of the form `key=value`, split out (`budget=800` becomes `label.budget` = `800`) |
| `label_flag.` | bare tags, `True` where the run carries one (`baseline_oss` becomes `label_flag.baseline_oss`) |
| `agent_model.` / `agent_provider.` / `agent_role.` | one column per agent id |
| `lineage.` | where a derived run came from, plus `derivation_type` |
| `metric.` | one column per evaluator |
| `metric_rounds.` | how many rounds that evaluator reported, the denominator behind a fraction |

Neither the knob columns nor the metric columns come from a list anyone
maintains: knobs come from what each run recorded, metrics from the names its
report carries. `run_id` and `scenario_name` are always emitted and cannot be
deselected, because every other table joins back on them.

Knobs flatten under one rule. A scalar is its own column. A mapping explodes
into dotted keys, so `model_overrides` becomes
`knob.model_overrides.field_observer.model`. A list stays one column of compact
JSON: a list like `scheduled_events` varies in length per run, and exploding it
by index would invent columns that mean different things in different rows.

`model_class` is `open`, `closed`, or `mixed`, read from the providers the run's
agents used (`self-hosted` and `ollama` are open weights). Provider rather than
model name, so a family nobody has run yet still classifies. An unrecognized
provider gives an empty cell rather than a guess.

The two label prefixes keep a cohort carrying both `budget` and `budget=800`
from collapsing a flag and a value into one column. They also mean filtering
never substring-matches the joined `labels` cell, where `baseline` also matches
`baseline_oss`.

### An empty cell is not a zero

**A blank metric cell means no number exists**: the metric did not apply, was
never run, or the run has no report. **A `0.0` cell means the metric ran and
counted zero**, a real observation for every metric that counts occurrences.
Filling blanks with zeros would merge the two and bias any average over the
column. To tell the blank cases apart, read `has_evaluation` and the
`runs_without_report` count on the preview.

`round_level.csv` says it twice over: a row exists for a round only when some
selected metric reported it, and within that row a metric that said nothing
leaves its cell empty.

`metric_rounds.<name>` is the denominator as a number. `round_success` of
`0.4667` is a different claim over 15 rounds than over 3, and this column is what
lets `cbind(successes, failures) ~ ...` skip parsing the unit string. A
`metric_rounds` of `0` means a run-level score with nothing per round. Empty
means the metric did not run.

### Cells a spreadsheet would misread

Control characters are stripped from text cells and newlines become spaces. Both
are legal in quoted CSV and both break line-oriented tools.

A cell beginning `=`, `+`, `@`, or a tab is prefixed with an apostrophe, which a
spreadsheet reads as "this is text" and does not display. Without it, a judge
note beginning `@ notation established ...` renders as `#NAME?` and is lost with
no indication. A leading `-` is left alone, since it is far more often a negative
number.

### `message_level.csv`

One row per channel message: the text, who sent it under which model, and the
numbers defined per message. The other tables aggregate this one, so having it
means reading a distribution rather than a mean, and a message next to its own
scores.

| Column | Holds |
|---|---|
| `round_number`, `channel_id`, `message_index_in_round` | where in the run it sits; the index restarts per round and channel |
| `is_primary_channel`, `team_id` | from the scenario's `get_primary_channels`; both empty when it could not be resolved |
| `sender_agent_id`, `sender_role`, `sender_model`, `sender_provider` | resolved from the run's roster, which the message event does not carry |
| `text` | what the sender composed |
| `delivered_text` | what the channel delivered, which differs under a transform like veyru's noise |
| `chars` | `len(text)`, the per-message value `mean_chars_per_message` averages |
| `character_entropy_bits`, `gzip_compression_ratio` | recomputed here with the same helpers those metrics use |
| `repetition_factor` | joined by `message_id` from the `language_repetition` sidecar, empty when the metric never ran |

Every channel is exported, so filter on `is_primary_channel` rather than having
the export decide. Surprisal is not
recomputed here, because it needs the `metrics-ml` extra a browsing server does
not install. Its per-round means are on `round_level.csv`.

### `round_context.csv`

One row per run and round, with `injection.<agent_id>` holding the briefing that
agent got at the start of the round and `postmortem_injection.<agent_id>` the one
that opened its postmortem. This is the per-round prompt: read beside
`message_level.csv` it gives what an agent knew going in against what it then
said. The columns are the roster, so a sheet reads one agent's briefings down a
column instead of pivoting.

It stays separate from `round_level.csv` even though both are keyed on
`(run, round)`. These cells are the largest text in the export, and a table
people join to and filter on should not carry them: in the exporter this mirrors,
repeating the briefings was ~86% of a file. Join on `run_id` + `round_number`.

### How the event-log tables read

`message_level.csv` and `round_context.csv` read every selected run's event log,
which is why neither is in the default set. Runs are read one at a time, so
memory does not grow with the selection. Asking for both reads each log twice.

Only `message_sent`, `tool_result_received` and `injection_delivered` are parsed,
with the postmortem phase tracked from `postmortem_started`. Parsing every line
would fail the export on an event these tables discard, the moment a run predates
a required field some scenario event gained. A line that fails anyway is skipped
and counted in the log, so one damaged run costs its own rows and not the export.

`is_primary_channel` and `team_id` come from rebuilding the scenario from the
run's recorded config. A config predating a newer required knob is backfilled
from the scenario's shipped presets, the run's own values always winning. When no
preset rebuilds, both columns render empty and the log names the last error.

## Selecting runs

Either specific runs or everything matching a filter, never a mix. In the UI that
is a radio button. Over the wire it is a tagged union, so there is no precedence
rule to get wrong. Checking rows in the runs list builds an explicit selection,
and "Select all loaded" covers the pages fetched so far. Filter mode resolves
server-side, where the whole set is known.

### Filtering by knob

`--knob` takes one condition written `<knob><operator><value>`, with the operator
one of `=` `!=` `>=` `<=` `>` `<`. Repeat it to require several, and every condition
must hold.

```bash
glossogen export --out ./out \
  --scenario veyru \
  --knob 'round_time_budget_seconds>=200' \
  --knob postmortem_enabled=true
```

**Quote any condition containing `>` or `<`.** Unquoted, the shell reads them as
redirection: `--knob round_time_budget_seconds>=200` writes a file named `=200`
and the flag never arrives.

The comparison is typed from the value the run recorded, not from the scenario's
knobs schema, so a run recorded before a knob changed type still answers. A
number compares numerically. A boolean takes `true`/`false` and refuses the
ordering operators. A string compares case-insensitively under `=` and `!=` only.
A knob holding a list or a mapping is not filterable. A nested knob is addressed
with dots, the way the CSV names its column:
`--knob 'model_overrides.field_observer.model=gpt-5.4'`.

`null` names a recorded null, and is the only reserved value (`none` and `unset`
are ordinary strings). `swap_round=null` keeps the runs that never swapped,
`swap_round!=null` the ones that did. `swap_round!=16` includes a run that never
swapped, since not swapping at all is not swapping at round 16. The ordering
operators never match a null. `judge_model=` is not a null test, it asks for the
empty string.

A knob the run never recorded keeps nothing, even under `!=`: the run cannot
answer the question, which is not the same as answering it in the negative. That
separates "runs that never swapped" from "runs predating the knob".

A condition with no operator is refused rather than dropped, since dropping it
would export a wider set than was asked for. A condition naming a knob no
scenario in the selection declares is not an error and selects nothing.

The same conditions apply in the UI's filter bar and over REST, as the
selection's `knob` array.

## CLI

Reads the runs directory directly, so it needs no server and no database, and it
covers runs that were never evaluated and runs still in progress.

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
| `--knob COND` | only runs whose recorded config satisfies this condition (repeatable, AND-matched) |
| `--status STATE` | only runs in one state, e.g. `scenario_complete` to skip crashed runs |
| `--run-id ID` | exactly these runs (repeatable); cannot be combined with any filter flag |
| `--frames` | which tables, comma-separated; the default is the first three |
| `--include-metric-summaries` | add each metric's unit and summary at run level, and its per-observation note on the round and agent tables |
| `--no-repeat-run-columns` | keep the round, agent and message tables narrow |
| `--raw` | also write `runs.zip` |
| `--include-logs` | keep debug and stdout logs in that zip |
| `--max-runs N` | override the 5000-run ceiling |

Every column and metric available for the selection is included. The flags trim
tables, not columns. Use the REST endpoint to pick columns.

## REST

All three are POSTs, because a selection can carry hundreds of run ids and a
column list a hundred keys, which is more than a query string reliably holds.

| Endpoint | Returns |
|---|---|
| `POST /api/g/{slug}/runs/export/preview` | JSON: run count, scenarios, available columns and metrics with per-column coverage, row counts per metric, and the limits |
| `POST /api/g/{slug}/runs/export/csv` | one CSV, or a zip of tables plus the legend |
| `POST /api/g/{slug}/runs/export/raw` | zip of the run folders |

The preview and the downloads share one selection model, so the preview describes
exactly what the download produces.

```bash
curl -X POST "$API/api/g/local/runs/export/csv" -H 'content-type: application/json' -d '{
  "selection": {"kind":"filters","scenario":["veyru"],"labels":["baseline_oss"],
                "run_id_contains":null,"status":null,"contains_agent_id":null,
                "knob":["round_time_budget_seconds>=200"]},
  "frames": ["run_level"],
  "columns": ["status","knob.round_count","label.budget"],
  "metrics": ["round_success","mean_chars_per_round"],
  "repeat_run_columns": false,
  "include_metric_summaries": false
}' -o run_level.csv
```

An explicit id that no longer resolves shows up on the preview, and a download
refuses it with a 404. Refusing is the safer failure: a table with one row fewer
than asked for looks exactly like a correct one. The export modal drops such ids
from the request and reports how many, leaving the 404 for a run deleted between
preview and download.

## Limits

| Ceiling | Value | Counts | How |
|---|---|---|---|
| runs per export | 5000 | runs in the selection | before the build |
| raw zip | 4 GiB | the run folders, **uncompressed** | estimated before the build |
| CSV tables | 512 MiB | bytes the **client receives** | counted during the write |

The run ceiling sits above the largest labelled cohort here. The raw ceiling is
conservative on purpose: it sizes folders on disk, and the delivered zip measured
5.7x to 7.0x smaller across three scenarios here, so 4 GiB counted is roughly
600 MiB received.

The CSV ceiling applies to the REST endpoint only. `glossogen export` writes to a
directory and holds no table in memory. For a single CSV, counted equals
delivered, and one cohort's `round_level.csv` alone reaches 273 MiB, which is a
large object for a browser tab to hold. Anything near that belongs on the CLI.
The raw ceiling does apply to the CLI, and `--max-runs` raises the run ceiling
locally.

Past any ceiling the download refuses, naming which limit and what to change. The
preview still answers, and reports all three limits so an interface quotes the
value the endpoint enforces. The archive is built into a temporary file under
`TMPDIR`. Point that at a larger volume if the default is small.

## What the raw zip holds

Each run nests under `{scenario_name}/{run_dir_name}/`, so extracting at `runs/`
reproduces the layout. A `manifest.csv` at the root names what went in.

Debug and stdout logs are left out by default, since a run's `_debug.jsonl` is
routinely larger than the event log. `--include-logs` or the modal checkbox puts
them back. `stream.json` and `eval_in_progress.json` are always left out: they
describe work in flight, so a re-imported run carrying them reads as still
running.

A run still being written is safe to export. Members are streamed into the
archive rather than pre-declaring a size, so a JSONL that grows mid-read does not
corrupt its entry.

## Not covered here

The **ground-truth meaning** behind a round: what the scenario planted, what it
expected, which sub-stage a message belongs to. A hand-written exporter reads a
scenario's own case events to get there. Making that scenario-agnostic needs a
contract for declaring the meaning, so it is tracked separately.

**Pre-aggregated frames**, the per-cell `n` / mean / std a hand-written exporter
ships. That is one `groupby` in R or Pandas, and shipping it would bake in the
grouping keys.
