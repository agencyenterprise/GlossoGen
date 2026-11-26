# What a run holds and how to read it

## The run directory

A local run lives in `<runs dir>/<scenario>/<run id>/`. The files that an analysis reads:

| File | Holds |
|---|---|
| `<scenario>.jsonl` | the event log, one JSON event per line |
| `labels.json` | the run's labels, a JSON list |
| `<scenario>_report.json` | the evaluation report, once `glossogen evaluate` has run |
| `fork_manifest.json`, `replace_manifest.json`, `cross_run_replace_manifest.json` | the source of a derived run: a fork or an agent replacement |
| `history_transfer_manifest.json` | the source run of a run whose agents started with another run's history |

## The events

| Event | What to read from it |
|---|---|
| `simulation_started` | `scenario_config` (every knob value), `glossogen_build` (version and commit), `scenario_description` |
| `agent_registered` | each seat's `model`, `provider`, `system_prompt` and tools. A resumed or derived run logs it again |
| `injection_delivered` | the briefing that an agent got at the start of a round or a discussion phase |
| `message_sent` | a channel message, as its sender wrote it |
| `tool_result_received` | what an agent received, including the delivered text of a message under channel noise |
| `llm_response_received` | an agent's reasoning (`thinking`), text and tool calls |
| `round_result_recorded` | whether the round succeeded, and why |
| `round_ended` | what ended the round (`trigger`) |
| `simulation_ended` | why the run ended |
| events named after the scenario | the scenario's own records, often including each round's ground truth |

A model's reasoning is in the log only when its provider returned it. An empty `thinking` does not show that the model did not reason.

Under channel noise, `message_sent` holds what the sender wrote. What the receiver read is in the receiver's `tool_result_received`, and in the `delivered_text` column of `message_level.csv`.

A derived run's log starts with the rounds that it copied from its source. Its `glossogen_build` is the build that derived it. A history-transfer run's log does not hold the transferred history. That history is in the source run's log, which the manifest names.

## Commands

| Command | Gives |
|---|---|
| `glossogen transcript <scenario> --run-dir <run>` | the log as plain text by round; `--out-dir` writes one file per round |
| `glossogen export --runs-dir <dir> --out <dir> --frames run_level,round_level,agent_level` | one row per run, per round and per agent, with knobs, models and metric values |
| `glossogen export ... --frames message_level,round_context` | one row per message, and each agent's briefing per round |
| `glossogen analyze --runs-dir <dir> ...` | metrics grouped by knob, label or model; `--list-fields` lists what a selection can be grouped by |
| `glossogen evaluate <scenario> --run-dir <run> --metrics <names> --model <judge> --provider <provider>` | runs metrics on a run and writes its report |
| `glossogen export-thread`, `glossogen export-atif` | one agent's history as a provider request body, or as ATIF trajectories |

`export` and `analyze` select runs with `--scenario`, `--label`, `--knob '<knob><op><value>'` and `--run-id`. See the glossogen docs on exporting runs and on analysis for every flag.

A report's metric with no measurement is missing, not zero. The CSV export writes it as an empty cell.

## Runs on a remote server

The glossogen MCP server lists runs (`list_runs`), describes one with its lineage (`get_run_metadata`), returns its messages (`get_run`), and gives a download link for its directory (`export_run_artifacts`). Extract the download into a local runs directory, `<runs dir>/<scenario>/<run id>/`, to use the commands above.
