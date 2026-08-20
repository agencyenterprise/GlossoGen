# Exporting runs

Two exports, both covering any number of runs and neither needing per-scenario code:

- **Raw run folders** — one zip holding the selected runs' directories, for handing to a
  coding agent or archiving.
- **CSV tables** — a flat data frame for R, Pandas, or a journal's supplementary
  materials.

Available from the **Export** button on the runs page, from `glossogen export`, and from
three REST endpoints.

To chart the same numbers instead of exporting them, see
[analysis and dashboards](analysis.md).

## What the CSV columns are

Column names are prefixed by where they came from, because a scenario is free to declare a
knob called `status` or `perplexity` and those are also a run field and a metric name.

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

`round_level.csv` says it twice over. A row exists for a round only when some selected
metric reported it, and within that row a metric that said nothing about the round leaves
its own cell empty.

### `model_class`

`open`, `closed`, or `mixed`, from the providers the run's agents used:
`self-hosted` and `ollama` are weights running on hardware someone chose, and the hosted
APIs are not. A run whose agents span both is `mixed`, which is its own condition rather
than a missing value, since the cross-family pairings are why the column exists.

Provider rather than model name, because a provider is a fixed set the CLI validates, so a
family nobody has run yet still classifies. An unrecognized provider gives an empty cell
rather than a guess.

### Bare tags

`label.<key>` covers `key=value`. A bare tag like `baseline_oss` gets `label_flag.<tag>`
holding `True`, empty where the run is not tagged. Without it, filtering a cohort means
substring-matching the joined `labels` cell, which is how eval-derived labels on 40 runs
were once destroyed: `baseline` also matches `baseline_oss`. The two prefixes are separate
so a cohort carrying both `budget` and `budget=800` does not collapse a flag and a value
into one column.

## The five tables

| Table | One row per |
|---|---|
| `run_level.csv` | run |
| `round_level.csv` | run and round |
| `agent_level.csv` | run and agent |
| `message_level.csv` | message |
| `round_context.csv` | run and round, one column per agent's briefing |

Every table is wide in metrics: a metric is a column, never a value in a `metric_name`
column. A round row therefore carries every metric measured on that round side by side,
which is a row a model can be fitted to directly. The alternative, one row per
`(run, metric, round)`, makes `pivot_wider()` the first line of every analysis.

One table comes back as a bare CSV. Two or more come back as a zip, with a
`columns.csv` legend alongside them naming each column's family, its unit, and how many
runs filled it.

The legend is the recoverable half of a blank cell. A knob a scenario never declared and a
knob it declared as null both render empty; the coverage count is the only thing that says
which columns were sparse.

It also names the structural columns of each table it wrote, `round_number` through
`delivered_text`. Those carry no coverage count, since every row of their table has them,
but they carry the units: nothing else says `character_entropy_bits` is bits per character
or that `repetition_factor` counts encodings per information unit.

`agent_level.csv` is keyed on the run's registered agents, not on what the metrics
reported, so it is the roster of who ran under which model even when no metric has a
per-agent number to add. That is the common case.

`repeat_run_columns` copies the run context onto every row of the round, agent and message
tables, so each row stands alone with no join back to `run_level.csv`. On by default.

### `metric_rounds.<name>`, and why a fraction needs it

`round_success` of `0.4667` is a different claim over 15 rounds than over 3, and the counts
behind it used to be legible only inside the unit string `fraction of rounds succeeded
(7/15)`. `metric_rounds.round_success` is that denominator as a number, so
`cbind(successes, failures) ~ ...` needs no string parsing and no second table.

A `metric_rounds` of `0` means the metric produced a run-level score and nothing per round,
which most of them do. Empty means the metric did not run at all.

## `message_level.csv`

One row per channel message: the text, who sent it under which model, and the numbers that
are defined per message. The other tables aggregate this one, so having it means looking at
a distribution rather than at a mean, and reading a message next to its own scores.

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

Every channel is exported, not only the primary one. A scenario's other channels carry the
coordination that explains what happened on the budgeted one, so filter on `is_primary_channel`
rather than having the export decide.

Surprisal (`perplexity`, `english_ngram_surprisal`) is not recomputed here. It needs the
`metrics-ml` extra, which a server that only browses runs does not install, and an export
that failed on a missing torch would be worse than one that omits a column. Its per-round
means are on `round_level.csv`.

**This and `round_context.csv` are the tables that read event logs**, which is why
neither is emitted by default: the reports the other tables read are small and an event log
is not. Runs are read one at a time, so the memory cost does not grow with the selection.
Asking for both reads each log twice, once per table.

Only `message_sent` and `tool_result_received` are parsed. A run recorded before one of a
scenario's events gained a required field no longer validates against today's model, and
parsing every line would fail the export on an event this table discards. A line that fails
anyway is skipped and counted in the log rather than raised, so one damaged run costs its
own rows and not the export.

`is_primary_channel` and `team_id` come from rebuilding the scenario from the config the
run recorded. When that config predates a knob the scenario has since added, it is
backfilled from each preset the scenario ships until one rebuilds, with the run's own
values always winning. When none does, both columns are empty and the log names the last
error, since "could not rebuild" on its own is unhelpful exactly when a run comes back
with those columns blank.

`team_id` is on these rows even though a `Measurement` carries no such field, because the
scenario's primary-channel declaration ties a channel to a team. At message level the team
is known without parsing it back out of a metric name like `round_success_team_a`.

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
| `--frames` | which tables, comma-separated; `message_level` and `round_context` are not in the default |
| `--include-metric-summaries` | add each metric's unit and summary at run level, and its per-observation note on the round and agent tables |
| `--no-repeat-run-columns` | keep the round, agent and message tables narrow |
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

## `round_context.csv`

One row per run and round, with `injection.<agent_id>` holding the briefing that agent was
given at the start of the round and `postmortem_injection.<agent_id>` the one that opened
the round's postmortem, where a scenario runs one.

This is the per-round prompt, and it is half of what a round is. Read beside
`message_level.csv` it gives what the agent knew going in against what it then said; on its
own a message table shows the answers with the questions missing.

The columns are the roster, so a sheet reading one agent's briefing finds it in a column
rather than pivoting to get there. This is the shape a hand-written exporter produces, where
the same cells are `field_observer_round_event` and `engineer_round_event`, named per
scenario; here the names come from what each run recorded.

Round-start and postmortem briefings are separate column families rather than two values in
one cell. The event does not say which phase delivered it, so the phase is tracked across
the log from `postmortem_started` and reset at each round. Measured across the runs here,
every `(round, agent)` cell carries exactly one of each.

It is a separate table from `round_level.csv` even though both are keyed on
`(run, round)`. These cells are the largest text in the export, and a table people join to
and filter on should not carry them: in the exporter this mirrors, repeating the briefings
was ~86% of a file. Join on `run_id` + `round_number`.

## Not covered here

The **ground-truth meaning** behind a round: what the scenario planted, what it expected,
and which sub-stage of a round a message belongs to. A hand-written exporter carries these
as `symptoms` / `actions` / `substage` / `substage_stabilized`, which is finer than
`message_index_in_round` and reads a scenario's own case events to get there. Making it
scenario-agnostic needs a contract for declaring that meaning, so it is tracked separately.

**Pre-aggregated frames**, the per-cell `n` / mean / std a hand-written exporter ships.
That is one `groupby` in R or Pandas, and shipping it would bake in the grouping keys.
