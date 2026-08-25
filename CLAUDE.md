# glossogen

## Setup

```bash
make install           # installs both server (uv sync) and frontend (npm ci)
make install-server    # server only
make install-frontend  # frontend only
```

## Linting

```bash
make lint              # runs both server and frontend linters
make lint-server       # server only (black, isort, ruff, pyright, vulture, custom linters)
make lint-frontend     # frontend only (prettier --write, eslint, stylelint, tsc)
make check-frontend    # frontend CI mode (prettier --check, no auto-fix)
```

## Project Structure

- For a step-by-step guide on adding a new scenario, see [docs/creating-a-scenario.md](docs/creating-a-scenario.md).
- For adding a metric, in this repo or in your own package, see [docs/creating-a-metric.md](docs/creating-a-metric.md).
- `src/` — application source code
- `src/glossogen/scenarios/<scenario_name>/` — one folder per scenario, containing:
  - `README.md` — scenario documentation
  - `scenario.py` — scenario class (channels, timing, tools, injections, turn logic, knobs schema)
  - `prompts/` — Jinja2 templates for agent system prompts and injection messages
  - `evaluation/` — scenario-specific metrics (optional)
  - `events.py` — scenario-specific `EventBase` subclasses (auto-discovered)
  - `run_detail_extension.py` — optional hook for surfacing scenario-specific data on the run-detail API
  - `scripts/` — one-off scripts that import directly from this scenario (smoke runners, probe-bank generators, etc.). Cross-scenario tools live in the repo-root `scripts/` instead.
- `src/glossogen/runtime/` — autonomous mode runtime (MCP server + coordination):
  - `simulation_state.py` — shared state: channels, sessions, locks, callbacks, world context, token counters, current round, injection delivery (`deliver_round_injections`, `deliver_postmortem_injections`, `has_postmortem_for_round`)
  - `mcp_tools.py` — MCP tool definitions (read_notifications, read_channel, send_message, etc.)
  - `mcp_server.py` — starts FastMCP over Streamable HTTP
  - `game_clock.py` — round progression and termination detection (delegates injection delivery to `SimulationRuntime`)
  - `agent_session.py` — per-agent notification queue, reaction delay, idle tracking
  - `scenario_mcp_tool.py` — ScenarioMcpTool for scenario-specific tool registration
  - `scenario_world.py` — ScenarioWorld ABC, WorldContext, MessageEvent, RoundAdvancedEvent
- `src/glossogen/runners/` — autonomous mode agent runners:
  - `agent_runner_base.py` — abstract base class for agent runners
  - `pydantic_ai_runner.py` — Pydantic AI agent runner via pydantic-ai framework
  - `pydantic_ai_model_factory.py` — per-provider mapping from `(model, provider)` to a pydantic-ai `model=` argument and default `ModelSettings`; shared by the runner and the platform's post-simulation `protocol_probe` helper
  - `communication_protocol.py` — shared prompts and constants for the agent communication protocol
- `src/glossogen/config_overrides.py` — Hydra-style dot-notation config override parser
- `src/glossogen/knob_filter.py` — the `<knob><operator><value>` filter grammar, parsed and applied against a run's recorded `scenario_config`. The knob name ends at the **first** operator and the longest one there wins, so a value may itself contain one (`judge_model=gpt>=5`). Comparison is typed from the recorded value rather than the knobs schema, so it imports no scenario class and a run predating a schema change still answers. A knob recorded as null is a value (`swap_round=null` selects the runs that never swapped); a knob the run never recorded matches nothing, even under `!=`. At the root because the listing, the export request model and the CLI's selection resolver all read it
- `src/glossogen/scenario_registry.py` — maps scenario name strings to the `SimulationScenario` classes shipped here; lives outside `glossogen.scenarios` package init so importing event-related modules doesn't trigger eager loading of every scenario
- `src/glossogen/scenario_loader.py` — the only way anything resolves a scenario name. Checks `SCENARIO_REGISTRY`, then scenarios other installed distributions declared. `get_scenario_class` raises, `find_scenario_class` returns `None`, `available_scenario_names` lists without importing, `iter_scenario_classes` imports every one
- `src/glossogen/scenario_entry_points.py` — reads the versioned `glossogen.scenarios.v<N>` entry-point group from installed metadata. Reading imports nothing, which is what lets event discovery cover external scenarios without re-entering the `models.event` import cycle
- `src/glossogen/scenario_api.py` — `SCENARIO_API_VERSION`, the scenario contract's version. Bumped when a change to the contract cannot be caught by Python itself (a hook whose required behaviour changed while its signature did not); the loader refuses an external scenario declaring a different one
- `src/glossogen/autonomous_supervisor.py` — autonomous mode orchestrator (supports resume via `RewindState`)
- `src/glossogen/message_rewind.py` — reconstructs simulation state at any message for fork/resume
- `src/glossogen/run_archive.py` — run directory helpers: `claim_run_dir`, `find_event_offset`/`find_message_offset` (linear JSONL scans), `copy_run_at_event` (copy + JSONL truncate), `strip_legacy_git_dir` (one-shot cleanup of pre-rewrite runs)
- `src/glossogen/run_export/` — exporting many runs at once, as raw run folders or as CSV tables. Imports no FastAPI, so the same code answers a REST request and a `glossogen export` that never starts a server. Scenario-agnostic by construction: knob columns come from each run's recorded `scenario_config`, evaluator columns from the metric names its report carries, so neither is a list anyone maintains
  - `export_request_models.py` — `ExportFrame`, and the selection as a tagged union (`FilterRunSelection` | `ExplicitRunSelection`) so "both were given" is unrepresentable; the three request bodies. The `knob` field validates on the model, which is what makes a malformed condition a 422 on all three POSTs and a startup error in the CLI rather than a 500 or a silently dropped filter
  - `export_preview_models.py` / `export_column_catalog.py` — `MultiRunExportPreview` and `build_export_preview`, computed from the same records the export reads, with per-column coverage counts
  - `metric_column_projection.py` — **where the empty-vs-zero rule lives**: a missing measurement renders `""` (no number exists), a present one renders its score including `"0.0"` (the metric ran and counted zero). Never default-fill a missing metric to `0`. Every table is **wide in metrics**: a metric is a column (`metric.<name>`), never a value in a `metric_name` column, so a round row is a design-matrix row rather than something to pivot first. `metric_rounds.<name>` carries the per-round observation count, which is the denominator behind a fraction like `round_success`
  - `knob_flattening.py` — one rule: scalar → own column, mapping → dotted keys, list → one JSON cell
  - `label_value_columns.py` — labels shaped `key=value` become `label.<key>` columns (`budget=800` → `label.budget`); a bare tag becomes `label_flag.<tag>` = `True`, so filtering a cohort never means substring-matching the joined `labels` cell
  - `model_weight_class.py` — `model_class` = `open` / `closed` / `mixed`, from the agents' **providers** (`self-hosted`/`ollama` are open weights) rather than model-name substrings, so a family nobody has run yet still classifies; an unrecognized provider gives an empty cell rather than a guess
  - `run_metadata_columns.py`, `agent_identity_columns.py`, `lineage_columns.py`, `run_context_columns.py` — the other column families, namespaced by prefix so a knob named `status` or `perplexity` cannot collide
  - `run_level_frame.py` / `round_level_frame.py` / `agent_level_frame.py` — one row per run, per (run, round), and per (run, agent). A round row exists only when some selected metric reported that round, so a missing row still means no observation rather than zero. The agent table is keyed on the run's registered roster rather than on what metrics reported, so it lists who ran under which model even when no metric has a per-agent number
  - `round_context_frame.py` — one row per (run, round), with `injection.<agent_id>` holding that agent's round-start briefing and `postmortem_injection.<agent_id>` its postmortem one. The per-round prompt, so a message table has the questions behind its answers. **Wide in agents**, matching the hand-written exporters' `<role>_round_event` columns, so a sheet reads a column instead of pivoting; the column set is the roster, so the header is known before any log is opened. The two phases are separate families because the event does not say which delivered it: the scan tracks phase from `postmortem_started` and resets each round. Reads event logs, so it is opt-in like the message table
  - `message_level_frame.py` / `run_message_records.py` / `message_event_scan.py` / `primary_channel_resolution.py` / `message_repetition_sidecar.py` — one row per channel message, with `text` (pristine) beside `delivered_text`, per-message `chars` / `character_entropy_bits` / `gzip_compression_ratio` recomputed with the metrics' own helpers, and `repetition_factor` joined from the `language_repetition` sidecar by `message_id`. **The only frame that reads event logs**, so it is never emitted by default and reads one run at a time. `message_event_scan` parses only `message_sent`, `tool_result_received` and `injection_delivered` and skips a line that fails: a run recorded before one of a scenario's events gained a required field no longer validates, and parsing every line failed the whole export on an event this table discards. `primary_channel_resolution` asks the scenario for `get_primary_channels()`, backfilling knobs the run predates from a shipped preset (the run's own values always win); when the merged config trips a cross-field validator it gives up and both columns render empty
  - `csv_frame.py`, `csv_frame_writer.py`, `csv_export_archive.py`, `csv_cell_text.py` — streaming CSV writing (UTF-8 with no BOM, `\n` endings), the `columns.csv` legend, and cell sanitizing for the control characters model output carries
  - `archive_member_filter.py` / `runs_zip_archive.py` — the shared include/exclude predicate (logs excluded by default, live-state files always) and the zip writer used by both the single-run and multi-run exports
  - `run_selection_resolution.py` — resolves a selection against a `list[RunSummary]`, sorted by run id so the same selection emits the same CSV bytes every time (archives still stamp each member with its write time). Applies every filter itself, including the knob conditions: the CLI reaches it from a filesystem walk with no listing in front, so a filter this module skips is one the CLI ignores
  - `export_limits.py` — `MAX_EXPORT_RUN_COUNT` (5000, above the largest labelled cohort here), `MAX_RAW_EXPORT_BYTES` (4 GiB) and `MAX_CSV_EXPORT_BYTES` (512 MiB), each bounding a different thing and measured differently. The run ceiling bounds request duration. The CSV ceiling counts the bytes a client receives, compressed inside a zip, checked during the write. The raw ceiling is estimated before the build by sizing the run folders uncompressed, so it is conservative: the zip delivered is 5.7x to 7.0x smaller here, making 4 GiB counted roughly 600 MiB received. The CSV ceiling applies to the HTTP path only, since the CLI writes to a directory

- `src/glossogen/run_analysis/` — grouped, aggregated answers over many runs, for the charts and for `glossogen analyze`. Imports no FastAPI, like `run_export`, and reads the same `ExportRunRecord`s, so a chart and the CSV it could have come from cover the same observations. Nothing here names a scenario or a metric
  - `analysis_run_record.py` — the projection every other module reads: one run reduced to its dimension cells, its roster, its numeric run columns, and each metric's score plus per-round and per-agent values. Judge notes and rollups are dropped, which is 18 KB a run against the 156 KB the full report costs (measured: 1,200 veyru runs, 22 MB against 187 MB), and is what lets a scenario-wide cohort sit in the server's cache while someone edits a chart over it
  - `analysis_grain.py` / `observation_table.py` — the grains and the rows each produces. Run, round and agent reproduce the corresponding CSV frame's row rule; `keyed` is one row per number a metric wrote along an axis of its own, with that metric's keys as dimensions under `key.`. **A measure with no measurement is `None`, never `0.0`**
  - `metric_inventory.py` — which metrics a selection carries and each one's unit, read off the runs' reports rather than off a registry. The unit is not claimed at the keyed grain: it describes the run-level score, and the keyed values are a different quantity
  - `measure_resolution.py` — a measure is an evaluator metric or a numeric run column (`total_cost_usd`, `duration_seconds`, `total_messages`, `current_round`); at the round and agent grains a run column repeats the run's own value
  - `aggregation.py` — mean / median / sum / count / min / max / stddev / sem. Missing values are dropped before the aggregate and counted beside it, so a blank never enters a mean; spread over one observation is nothing rather than zero
  - `dimension_filter.py` — `in`, `not_in`, `contains`, `is_empty`, `is_not_empty`, and numeric `gte` / `lte` that parse the cell; a cell that is not a number fails a range filter rather than passing it
  - `analysis_query_models.py` / `analysis_result_models.py` — the query (grain, filters, group-by, measures, sort, limit) split from the selection it runs over, so a dashboard re-points every chart by changing one field. Every aggregate travels with its observation and missing counts
  - `analysis_query_engine.py` — filter, group, aggregate, sort, cap. Groups whose values are numbers sort numerically, so a knob sweep charts in sweep order
  - `analysis_field_catalog.py` — what a selection can be sliced and measured by, built from the same table a query reads, with each dimension's distinct values capped and the true count reported beside them
  - `analysis_spec_parsing.py` / `analysis_text_table.py` — the CLI's `key:aggregate` and `key:operator:values` forms, and the aligned table it prints
- `src/glossogen/dashboards/` — a saved analysis: a selection, filters, and the charts over them. Charts store their query, not their numbers, so reopening one re-runs it
  - `dashboard_models.py` — `Dashboard`, `ChartSpec`, `ChartKind` (bar / line / scatter / heatmap / table). The dashboard's selection and filters are inherited by every chart, with chart-level filters merged on top
  - `dashboard_store.py` + `postgres_dashboard_store.py` + `filesystem_dashboard_store.py` — one contract, two backings: Postgres when `DATABASE_URL` is set, JSON under `<runs-dir>/_dashboards/<group-id>/` when it is not, so single-tenant local mode keeps the feature. `dashboard_store_resolution.py` picks by `app.state.db_pool is None`, the same test run lookup uses. Names are unique per group, enforced by the index rather than by a check-then-insert
- `src/glossogen/label_descriptions/` — a group's label glossary: what each label means, keyed on the exact label string, so it applies to every run carrying the label without touching any run directory. Labels themselves stay plain strings in `labels.json`. Same two-backing contract as dashboards: Postgres (`label_descriptions` table, `(group_id, label)` primary key) when `DATABASE_URL` is set, one JSON file per group under `<runs-dir>/_label_descriptions/` when it is not. Served by `server/runs/label_description_router.py` (`GET`/`PUT`/`DELETE /labels/descriptions`; the label travels in the body or a query parameter, never the path, because labels like `src=veyru/123` carry path separators). The CLI's `describe-label` / `list-label-descriptions` write and read the local group's file directly, no server needed. Frontend label chips show the description on hover via `use-label-descriptions.ts`
- `src/glossogen/message_history_builder.py` — reconstructs pydantic-ai ModelMessage history from JSONL events for fork/resume
- `src/glossogen/llm/` — LLM provider abstraction + Anthropic/OpenAI/HuggingFace implementations
- `src/glossogen/evaluation/` — generic metrics and evaluation infrastructure
  - `metric_core/` — the Metric contract + I/O types
    - `metric_protocol.py` — `Metric` ABC; `compute(events, agent_configs, scenario, llm_provider, run_dir, options)` is the only entry point. Most metrics ignore `options`; metrics that need per-invocation flags (e.g. `protocol_probe`) read them off the passed `MetricRunOptions`.
    - `metric_run_options.py` — `MetricRunOptions` Pydantic model carrying per-invocation flags (`probe_round`, `probe_replicas`); built by the CLI from argparse and threaded into `run_scenario_evaluation(...)`.
    - `metric_registry.py` — `GENERIC_METRIC_REGISTRY` maps the metric names shipped here to their classes; `cls()` builds an instance and `cls.compute(..., options=options)` runs it. `available_metrics()` merges in metrics other installed distributions declare and is what the evaluation runner reads
    - `metric_entry_points.py` — the `glossogen.metrics` entry-point group, by name only. It cannot import `Metric`: the scenario contract asks it which metrics to advertise, and a metric module imports the scenario contract, so importing classes here would close that cycle (the same reason `generic_metric_names.py` exists)
    - `measurement.py` — `Measurement`, `RoundObservation`, `AgentObservation`, and judge-side `RoundNote` Pydantic models
    - `keyed_observation.py` / `keyed_observation_reader.py` / `sidecar_reading.py` — the second half of the metric contract. A metric that writes numbers to a file beside its report (per category, per probe question, per message) implements `read_keyed_observations(run_dir)` to read them back, and the reader walks the registry so the analysis layer still names no metric. Reading is tolerant by design: a cohort spans months of metric versions, and one truncated file costs that run's numbers rather than the sweep. The numbers stay in the sidecar rather than moving into the report, because re-evaluating thousands of runs to relocate a number is not a migration worth paying for
    - `generic_metric_names.py` — canonical name list (avoids circular imports with `scenario_protocol`)
  - `reports/` — on-disk report shape
    - `evaluation_report.py` — `EvaluationReport` schema, plus `load_report` / `write_report` / `merge_evaluation_costs` helpers
    - `evaluation_cost.py` — `EvaluationTokenUsage`, `EvaluationCost`, and `compute_evaluation_cost`
  - `metrics/` — concrete Metric implementations
    - `language_repetition_metric.py` — LLM judge, **per message**: for each round it feeds that round's `#link` messages (pristine) as an enumerated list and the judge returns one redundancy factor per message (≥1.0; captures repeated tokens, digit+word dual-encoding, abbreviation+expansion). Judged `rounds × 3` calls (3 replicas/round, averaged per message). Per-message factors → `language_repetition_messages.jsonl` sidecar (keyed by `message_id`); the `Measurement` carries the per-round mean factor and run-level mean
    - `language_strangeness_metric.py` — detects unusual grammar, structure, formatting (not codes/slang/neologisms)
    - `slang_emergence_metric.py` — detects informal register shifts and colloquial expressions
    - `neologism_metric.py` — detects genuinely invented words (not abbreviations or codes)
    - `shorthand_codes_metric.py` — detects abbreviation systems and symbol-to-meaning mappings
    - `content_filter_refusal_metric.py` — counts ``ContentFilterError`` refusals across the run, with per-round + per-agent breakdowns
    - `perplexity_metric.py` — mean per-token surprisal of primary-channel messages under `gpt2`
    - `mcr_metric.py` — mean total characters per round on the primary channel
    - `mcm_metric.py` — mean characters per message on the primary channel
    - `round_success_metric.py` — generic; reads `RoundResultRecorded` events written by the game clock from `SimulationScenario.judge_round_result` (a required abstract method). Single-team scenarios emit one Measurement (`metric_name="round_success"`); multi-team scenarios emit one per `team_id` (`round_success_team_a`, etc.). Returns `[]` only when a scenario's `judge_round_result` yields no verdicts.
    - `round_success_after_resume_metric.py` — generic; re-scores `round_success` over the post-resume window. Reads `replace_manifest.json` / `cross_run_replace_manifest.json` and every `AgentSwappedMidRun` event; the per-window scoring delegates to the same `RoundResultRecorded` events as `round_success`. Returns `[]` on non-resume runs.
    - `protocol_explanation_metric.py` — generic; probes each agent under its own model with its full end-of-run history to describe (free-text) the communication protocol it remembers. Renders the scenario's per-role template from `get_protocol_explanation_config()` when present, else a generic prompt. Writes `protocol_explanation_responses.jsonl` + `protocol_explanation_usage.json`; answers also land in `per_agent[].note`.
    - `probe_usage_report.py` — shared per-(model, provider) token-usage aggregation (`ProbeUsageReport`, `accumulate_probe_usage`, `build_probe_usage_report`) used by both `protocol_probe` and `protocol_explanation`.
    - `protocol_learned_after_swap_metric.py` — generic LLM-judge; calls the scenario's `detect_protocol_boundary_window` to find the pre/post split and `build_communication_rounds` to render transcripts. Returns `[]` when either hook opts out.
    - `protocol_probe/` — generic protocol-probe metric family. Reads `SimulationScenario.get_protocol_probe_config()` for the per-scenario question bank and probe-prompt templates; returns `[]` when the hook returns `None`.
      - `protocol_probe_metric.py` — runs the probe LLM calls and writes `protocol_probe_responses.jsonl`
      - `protocol_probe_replica_self_similarity_metric.py` — within-(agent, question, cutoff) replica self-similarity
      - `protocol_probe_agent_pair_similarity_metric.py` — agent × agent matrix per (question, cutoff); skips on single-team runs
      - `protocol_probe_cutoff_trajectory_metric.py` — adjacent-cutoff drift per (agent, question)
      - `probe_agent.py`, `similarity_core.py`, `response_models.py` — shared helpers
    - `round_ended/` — round-end trigger metrics
      - `round_ended_idle_metric.py` — flags rounds whose main phase ended via the `all_agents_idle` trigger
      - `round_ended_timeout_metric.py` — flags rounds whose main phase ended via the `round_timeout` trigger
      - `postmortem_ended_timeout_metric.py` — flags rounds whose *postmortem* phase ended via `postmortem_timeout` (wall-clock) rather than all agents going idle. Reads `PostmortemEnded` events (authoritative; covers the final round) with a fallback to `RoundAdvanced(trigger="postmortem_timeout")` for runs predating that event
      - `trigger_detection.py` — shared helpers for reading `RoundEnded` / `PostmortemEnded` / `RoundAdvanced` trigger events
  - `metric_core/` (additions):
    - `round_result_index.py` — `per_round_joint_success(events)` builds round→bool from `RoundResultRecorded` events (multi-team joint = all teams succeeded)
    - `protocol_boundary.py` — `ProtocolBoundaryWindow` NamedTuple returned by `detect_protocol_boundary_window`
    - `protocol_explanation_config.py` — `ProtocolExplanationConfig` NamedTuple returned by `get_protocol_explanation_config`
    - `protocol_probe_config.py` — `ProtocolProbeConfig` NamedTuple returned by `get_protocol_probe_config`
    - `resume_anchors.py` — manifest + `AgentSwappedMidRun` reading helpers shared by `round_success_after_resume`
  - `log_reader.py` — JSONL event loading + scenario/agent config extraction (cross-cutting; used by CLI, server, runtime, and metrics)
  - `round_transcript_builder.py` — builds per-round message transcripts from events (used by all generic LLM-judge metrics)
  - `prompts/` — Jinja2 templates for LLM judge prompts + the `prompt_renderer.py` loader
- `src/glossogen/server/` — FastAPI web server exposing simulation data via REST and SSE streaming
  - `identity/middleware.py` — provider-agnostic ASGI identity middleware; extracts the active group slug from the URL (`/api/g/{slug}/...` or `/mcp/g/{slug}/...`), pulls the bearer credential, resolves the slug to a `groups` row, asks the installed provider for an `Identity`, and attaches it to `request.state`. With no provider installed it short-circuits to a synthetic `local` group / `local-user`. Also carries the MCP OAuth-token fallback.
  - `identity/identity_provider.py` — the `IdentityProvider` ABC and `IdentityRejected`. The platform ships no implementation: authentication is a plug-in.
  - `identity/identity_provider_loader.py` — resolves the one installed provider, or `None` for single-tenant mode. Unlike the scenario and metric loaders it **raises** on ambiguity (two providers, or one declared under an unread group version), because falling back would mean serving unauthenticated.
  - `identity/identity_entry_points.py`, `identity/identity_api.py` — the `glossogen.identity_provider.v<N>` group and the contract version, mirroring the scenario plumbing.
  - `identity/bearer_credential.py` — `bearer_from_header` and `bearer_from_header_or_query`; the second is the `?token=` variant SSE needs.
  - `identity/identity_model.py` — the `Identity` Pydantic model attached to every request.
  - `identity/provider_services.py` — the other half of the seam: what the platform offers a provider (`approve_parked_consent`, `frontend_base_url`, and the two `groups` query helpers). Nothing in-tree calls these, which is why they carry vulture whitelist entries.
  - `identity/bootstrap.py` — boots the synthetic `local` group at startup (idempotent upsert into `groups`).
  - `runs/listing.py` — Postgres-backed `list_runs_for_group(request, scenario_filter)`; the active group's `group_id` is read from `request.state.identity`. `_apply_enriched_filters` holds the filters that need a built summary (status, agent, knobs), shared by the paginated and the unpaginated listing.
  - `runs/lookup.py` — `resolve_run_or_404` (queries `runs` table on `(group_id, scenario, run_dir_name)` before touching disk) and `register_new_run` (inserts a row after `claim_run_dir`).
  - `runs/multi_export_router.py` — `POST /runs/export/preview` / `/csv` / `/raw`. POST because a selection carries hundreds of run ids and a column list a hundred keys. The preview and the downloads share one selection model
  - `runs/export_selection.py` — resolves a selection within the active group; a filter selection goes through `list_runs_matching_filters_for_group`, an explicit one enumerates the group to check ownership
  - `runs/archive_streaming_response.py` — builds an archive into a `TemporaryFile` then streams it. O(1) RAM, and a real `Content-Length` so a client can show true progress. Building in a worker thread leaves the event loop responsive: measured on the widest 500-run export, 2.37s to build with a worst loop gap of 12ms. `TMPDIR` is the operational knob
  - `runs/analysis_router.py` — `POST /runs/analysis/fields` and `/runs/analysis/query`, on the same selection resolution and run ceiling the exports use. A selection matching nothing is answered with an empty result rather than refused, and ids that no longer resolve come back on the answer, because a saved dashboard outlives its runs
  - `runs/analysis_record_cache.py` — a minute of loaded records per selection, so editing a chart does not re-read one report per run on every keystroke. Concurrent requests for one selection share a load; time is a parameter, so a test states what "later" means instead of waiting for it
  - `runs/dashboard_router.py` — list / create / read / replace / delete, scoped to the active group. A name another dashboard in the group holds is a 409
  - `scenarios/filterable_knobs.py` — reads a knobs JSON Schema and keeps the scalar knobs, unwrapping `T | None` and following `$ref` into `$defs` for enums. Behind `GET /scenarios/{name}/filterable-knobs`, which is how the runs list learns what it can filter on without knowing any scenario's knob names
- `src/glossogen/db/` — Postgres data layer (raw SQL via psycopg3 async; alembic for migrations)
  - `pool.py` — async connection pool wrapper
  - `queries.py` — typed query helpers returning Pydantic rows (`get_group_by_slug`, `list_runs_for_group`, `insert_run`, `upsert_group`, `soft_delete_group_by_external_org_id`, `set_last_active_group`, etc.)
  - `rows.py` — `GroupRow`, `RunRow`, `UserLastActiveGroupRow` Pydantic models
  - `local_tenant.py` — canonical constants `LOCAL_USER_ID = "local-user"`, `LOCAL_GROUP_SLUG = "local"`, `LOCAL_GROUP_NAME = "Local"`
  - `run_registry.py` — standalone (own connection) variants used by the CLI / scripts that run outside the FastAPI lifespan
  - `migrations/` — alembic env + raw-SQL revisions
  - `runs/scenario_extension.py` — `ScenarioRunDetailExtension` ABC + auto-discovery of every scenario's optional `run_detail_extension.py`; powers the discriminated-union `scenario_extras` field on `RunDetailResponse`
  - `runs/run_detail_types.py` — leaf DTOs (`AgentDetail`, `ChannelMessage`) shared by `models.py` and scenario-side extensions so extensions can import them without re-entering `models.py` during its discovery-time import
  - `mcp/browser.py` — MCP server mounted at `/mcp` for programmatic run browsing and launching (Claude Code, Cursor)
  - `mcp/oauth_provider.py` — OAuth 2.0 authorization server provider for MCP
  - `mcp/oauth_storage.py` — Postgres-backed storage for OAuth clients, codes, and tokens
  - `mcp/oauth_login_page.py` — login form for the MCP OAuth authorization flow
  - `run_launcher.py` — shared simulation launch helper used by REST and MCP run-start flows
- `linter/` — custom linting scripts
- `modal/` — self-hosted LLM endpoint (Modal-hosted Llama 3.3 70B by default)
  - `serve_llama.py` — Modal app launching vLLM's OpenAI-compatible HTTP server on `H100:2`
  - `tool_chat_template_llama3.1_json.jinja` — vLLM tool-calling chat template (Llama 3.1/3.3)
  - `smoke_test_llama.py` — end-to-end smoke test (runs inside Modal so the API key never leaves)
  - `README.md` — deploy + integration instructions
- `frontend/` — Next.js web application
  - `src/features/auth/` — authentication gate and login page
  - `src/features/mcp-config/` — MCP integration modal with connection instructions
  - `src/features/analysis/` — the analysis surface at `/g/<group>/analysis`: cohort selection, filter builder, chart builder, saved dashboards. `series-palette.ts` holds the validated series slots and heatmap ramp (assigned in fixed order, never cycled, defined as tokens in `globals.css` so a chart follows the theme without reading it); `chart-series.ts` reshapes one result into rows; `charts/` draws bar / line / scatter with Recharts and the heatmap as a table. A group with no observations renders as a gap, never as a zero mark, and every chart carries its table and a CSV of the rows behind it
  - `src/features/runs/scenario-plugin.ts` — `ScenarioPlugin` interface (round-detail panel, tool-metadata renderer, tool-verdict summary, live-judge SSE wiring, timeline markers, round-trigger classification). `extras` is `unknown` at the boundary so the registry can hold every plug-in under a single type
  - `src/features/runs/scenario-registry.ts` — eager-imports each scenario's optional `<scenario>/plugin.tsx`; `getScenarioPlugin(name)` resolves an unknown name to the default no-op plug-in. Compiled in, so a scenario installed from another distribution renders with the platform UI

### Prompt Templates

All prompts (agent system prompts, round injections) use Jinja2 templates stored in `prompts/` inside each scenario folder. Never hardcode prompt text in Python code.

## Code Design Principles

### API & Schema Design

- **Strict API schemas.** Never return raw dicts. Always define a Pydantic response model. Use enums for status-like fields.
- **Non-optional when always set.** If a field is always populated, declare it as required, not `Optional`.
- **Web server responses must be structured Pydantic models.** Every FastAPI endpoint must declare a `response_model` and return an instance of that model. Never return plain dicts, strings, or untyped JSON.

### File & Module Organization

- **No generic file names.** Never name a file `services.py`, `utils.py`, `helpers.py`, or `common.py`. The file name must describe its content.
- **Same for classes and functions.** `BaseHelper`, `CommonUtils`, `MiscOperations` are red flags. Name things after what they do.

### Python Style

- **Always use named arguments** when calling functions.
- **Never return dicts from functions.** When returning multiple values, use a `NamedTuple` or Pydantic model.
- **No default parameter values.** All callers must pass all arguments explicitly. Refactor callers instead of adding defaults.
- **Prefer async.** When both sync and async options exist (database, HTTP, file I/O), use the async variant.
- **No `TYPE_CHECKING` or `from __future__ import annotations`.** Use direct imports. If there's a circular import, fix the cycle by restructuring.
- **No string type annotations.** Never use quotes around type hints.
- **No inline ternary expressions.** Use `if`/`else` blocks instead of `x if condition else y`.
- **Remove dead code aggressively.** Unused fields, stale imports, commented-out code — delete them.
- **Always use `logger.exception` in except blocks.** Every `except` clause that handles an error must call `logger.exception(...)` so the full stacktrace is visible in logs.

### LLM Output Parsing

- **Always use output schemas to enforce structured LLM responses.** Never parse free text from LLM responses. Define a Pydantic model for the desired output shape, pass it to `generate_structured()`, and use the validated instance directly.

### Tests and time

**No test may depend on wall-clock time.** No `sleep`, no waiting for a duration
to elapse, no assertion that rests on a timeout firing on its own. A test that
races real time passes on a quiet machine and fails under load, and the failure
reads as a bug in the code under test rather than in the test.

Monkeypatching a duration to a small number is not a fix. It narrows the race
without removing it, and the smaller the number the tighter the race gets
against scheduling jitter.

Where the platform uses time as a proxy for a question, the test answers the
question directly instead. The game clock waits `MIN_ROUND_DURATION_SECONDS`
after the last message to guess whether the agents have finished; a test with
scripted agents knows when they have finished, because it wrote the scripts. If
the production path has no injection point for that, add one rather than tune
the wait.

A test that has to exercise a timeout drives the clock rather than waiting for
one: advancing time is an explicit statement in the test.

This was measured, not assumed. With that floor patched to 50ms,
`container_yard_stacking` dropped a message roughly one full-suite run in six
under `-n auto`, which changed what its world announced and broke a recorded
baseline. Nothing about the scenario or the platform was wrong; the test was
racing.

### Tests and files the repo ships

**No test may write to a file the repo ships**, even if it restores it afterwards.
Test processes share one filesystem: under `-n auto` the restore protects the test
that made the edit and nothing else, so any test reading that file inside the
window sees the edit and reports the thing it read as broken.

Break a copy instead. Copy the package to `tmp_path`, edit the copy, and point the
code under test at it: `monkeypatch.setattr(scenario_cls,
"scenario_package_files", classmethod(...))`. Copy the whole package rather than
the one file, because the other checks read from that directory too.

This was measured, not assumed. `test_an_events_module_importing_the_event_union_is_reported`
prepended an import to `prisoners_dilemma/events.py` and restored it in a
`finally`. Roughly one full-suite run in eighteen, `validate prisoners_dilemma`
read the file mid-window and failed with `events.py imports from
glossogen.models.event at line 1`. Nothing was wrong with prisoners_dilemma; two
tests were racing on one file.

### Writing

This applies to every word committed here: docstrings, comments, markdown, commit
messages, PR descriptions.

Write like an engineer explaining something to the next engineer. The habits below
read as machine-written and are not wanted:

- **Em-dashes mid-sentence.** "The log is what everyone reads — so a thing that
  wasn't logged didn't happen." Use a comma, a colon, or two sentences. A dash
  introducing a definition in a list is fine and common here:
  `` - `src/` — application source code ``.
- **Announcing importance instead of stating fact.** "These are the tests that
  matter", "this is the whole point", "deliberately loud". Say what the thing
  does and let the reader judge.
- **Restating the heading** in the first sentence under it. Add information.
- **Inflated words**: leverage, harness, seamless, robust, powerful, unlock,
  streamline, empower, at scale, cutting-edge. Use the plain one.
- **"Not just X, it's Y"** and **rule-of-three lists** when three isn't the real
  count. State the point; say the true number.
- **Every sentence the same medium length.** Vary it. Some should be short.

Read it back before committing. If you would not say it out loud to a colleague,
rewrite it.

### Docstrings

- **Every module needs a module-level docstring** describing what it defines.
- **Every public class and important function needs a docstring.**
- **Be factual only.** Describe what the code does, not assumptions about why. Never use subjective language.
- **Be concise.** One to three sentences for most docstrings.
- **Never state a count of things that can change.** "Six scenarios build a judge",
  "the four probe metrics", "28 questions per agent". Every one of these becomes a
  lie the next time someone adds a scenario, a metric, or a question, and nothing
  fails when it does. Name the property instead: "scenarios that judge their own
  rounds", "the probe metrics", "the whole question bank". Counts that describe a
  fixed design ("three agents share one channel") are fine, because changing them
  means redesigning the thing being described.

## Frontend

Stack: Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4, TanStack React Query, openapi-fetch.

### API Client & Type Safety

All API calls must use the generated typed client from `@/shared/lib/api-client`. Raw `fetch()` is forbidden, enforced by ESLint.

To regenerate types after changing backend endpoints:

```bash
make gen-api-types
```

CI fails if `frontend/src/types/api.gen.ts` drifts from the backend schema.

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (for simulations) | Anthropic API key |
| `OPENAI_API_KEY` | Optional | OpenAI API key |
| `HF_TOKEN` | Optional | HuggingFace token |
| `DATABASE_URL` | No (single-tenant) / Yes (multi-tenant, prod) | Postgres connection string for the tenancy + runs index (e.g. `postgresql://localhost:5432/glossogen_dev`). Leave unset or blank for no-database single-tenant mode (runs index derived from the filesystem, OAuth state in memory). Required whenever an identity provider is installed. |
| `ALLOWED_ORIGINS` | Optional | Comma-separated CORS origins (defaults to `http://localhost:3000`) |
| `GLOSSOGEN_RUNS_DIR` | Optional | Directory for simulation run data (defaults to `./runs`) |
| `ENABLE_EVALUATIONS` | Optional | Whether the REST evaluate endpoint (the frontend "Run Eval" button) is enabled. Defaults to enabled; set to `false`/`0`/`no`/`off` to disable (endpoint returns 403, frontend hides the button via `GET /api/server-config`). Does not affect the CLI `glossogen evaluate` command. |
| `FRONTEND_URL` | Optional | Base URL the MCP OAuth consent flow redirects to. Falls back to the first `ALLOWED_ORIGINS` entry, then `http://localhost:3000`. Required in multi-tenant mode for the `/mcp-consent` redirect to reach the right host. |
| (identity provider vars) | Yes (multi-tenant) | Whatever the installed provider reads. The platform ships none; see the Authentication section. |
| `OAUTH_ISSUER_URL` | Yes (for MCP) | Public backend URL for MCP OAuth (MCP is disabled if unset) |
| `SELF_HOSTED_BASE_URLS` | Required for `--provider self-hosted` | JSON object mapping model name → OpenAI-compatible `/v1` base URL. Example: `{"meta-llama/Llama-3.3-70B-Instruct":"https://....modal.run/v1","Qwen/Qwen3-32B":"https://....modal.run/v1"}` |
| `SELF_HOSTED_API_KEY` | Required for `--provider self-hosted` | Bearer token shared across all entries in `SELF_HOSTED_BASE_URLS` (matches each server's `--api-key`) |
| `LOG_LEVEL` | Optional | Stdlib logging level for `glossogen` CLI commands (`DEBUG`/`INFO`/`WARNING`/`ERROR`). Set to `DEBUG` to capture verbatim LLM-judge system prompt, user prompt, and structured-output JSON in stderr. Defaults to `INFO`. |
| `LLM_MAX_TOKENS` | Optional | Per-call output-token cap applied uniformly to the Claude (`max_tokens`), OpenAI (`max_output_tokens`), and HuggingFace (`max_tokens`) providers. Defaults to `16384`; bump higher if structured-output JSON truncates. Note: this does **not** cap the simulation agents — those use the `agent_max_tokens` knob (see below). |
| `LANGFUSE_PUBLIC_KEY` | Optional | Langfuse project public key. When both this and `LANGFUSE_SECRET_KEY` are set, `glossogen run` exports every simulation agent's LLM calls (prompts, completions, tool calls, token usage) to Langfuse as OpenTelemetry traces. `.env.example` pre-fills `pk-lf-local-dev` to match the local Docker stack. Only the `run` path is instrumented — `glossogen evaluate` stays untraced. |
| `LANGFUSE_SECRET_KEY` | Optional | Langfuse project secret key. Pre-filled `sk-lf-local-dev`. Blank both keys to disable telemetry. |
| `LANGFUSE_HOST` | Optional | Langfuse base URL. Defaults to `http://localhost:3001` (the local `make langfuse-up` stack; 3001 because the frontend dev server owns 3000). If the stack isn't running, the run logs one `auth_check` warning and proceeds untraced — telemetry never blocks a simulation. |

Frontend environment variables go in `frontend/.env.local` (see `frontend/.env.local.example`):

| Variable | Default | Description |
|---|---|---|
| `API_URL` | (required) | Backend API base URL. Read at request time and forwarded to the browser by the root layout — never compiled into the bundle. |

## Development

```bash
make dev            # start FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # start Next.js dev server on port 3000
```

## Local Langfuse (observability)

Simulation agents' LLM calls are traced to a **local, self-hosted Langfuse** (never cloud)
via pydantic-ai's OpenTelemetry instrumentation. The stack runs from a vendored compose file.

```bash
make langfuse-up     # start the full Langfuse stack (web, worker, postgres, clickhouse, redis, minio)
make langfuse-down   # stop it
make langfuse-logs   # tail the langfuse-web logs
```

- UI at **http://localhost:3001** (3001 because the Next.js frontend owns 3000); first boot
  takes ~2-3 min. Log in with `local@glossogen.dev` / `local-dev-password` (seeded via
  `LANGFUSE_INIT_*` in `docker-compose.langfuse.yml`). Langfuse's internal postgres is mapped
  to host 5433 to avoid clashing with a local 5432 Postgres.
- The `glossogen` org + project and the API keys (`pk-lf-local-dev` / `sk-lf-local-dev`) are
  headlessly seeded on first boot, so there is no UI setup. Those keys are pre-filled in
  `.env.example`, so `glossogen run` traces to this instance out of the box.
- Each run is one Langfuse **session** keyed by `run_id`; every agent's cycles trace under it,
  tagged with `agent_id` / `role_name` / `model` / `provider` / `scenario`.
- Telemetry is initialized only in the `glossogen run` path (`init_langfuse_telemetry` in
  [telemetry_bootstrap.py](src/glossogen/telemetry_bootstrap.py)), so `glossogen evaluate`'s
  probe/judge LLM calls are not traced. If the stack is down or keys are unset, the run logs
  one warning and proceeds untraced. Telemetry never blocks a simulation.
- Docker Desktop needs adequate resources for the full stack (Langfuse suggests ~4 cores /
  16 GiB). The stack exposes `langfuse-web` on host :3001 and `minio` on :9090; the other
  services (postgres :5433, redis, clickhouse) bind to localhost only.

## Authentication

The backend is multi-tenant. Each **organization in the installed identity provider** corresponds to a study **group**; every run is owned by exactly one group, never shared across groups except via the export/import flow. The active group is identified by the URL slug: `/g/<slug>/...` on the frontend maps to `/api/g/<slug>/...` on the backend.

Authentication itself is a plug-in. The platform ships no provider, so there are two run-time modes, switched by whether one is installed.

### Single-tenant mode (no provider installed)

Default for a clone.

- `IdentityMiddleware` resolves every request to a synthetic `local` group / `local-user`. The `local` row is upserted into `groups` at server startup by `identity/bootstrap.py:ensure_local_group`.
- The frontend renders without a sign-in flow; `<GroupProvider>` is hard-coded to `LOCAL_GROUP_SLUG = "local"`.
- Postgres is optional. Unset `DATABASE_URL` and the runs index comes from the filesystem with OAuth state in memory; set it and the `local` group plus the runs index live in Postgres.
- All endpoints except the unauthenticated ones still pass through the identity middleware; they just receive the synthetic identity.
- **It performs no authentication.** Do not expose it to a network.

### Multi-tenant mode (a provider installed)

A provider is a separate installed distribution declaring one entry point under `glossogen.identity_provider.v1`, implementing `IdentityProvider` (`src/glossogen/server/identity/identity_provider.py`).

- The platform does the parts a provider must not get wrong: it extracts the bearer credential (header, or `?token=` for SSE), parses the URL's group slug, and resolves that slug to a `groups` row. Only then does it call `resolve_identity(credential, group)`.
- A provider therefore answers one question, whether this credential grants access to this group and as whom, and never queries the `groups` table. It raises `IdentityRejected` with 401 for a credential that does not verify and 403 for one that verifies but does not cover the group.
- A provider also declares `unauthenticated_path_prefixes()` for the endpoints its own service calls (a webhook has no user session), contributes `routers()`, and supplies `deferred_consent_url()` for the MCP flow.
- **Ambiguity is fatal.** Two declared providers, or one declared under a group version this platform does not read, refuses to boot. The scenario and metric loaders warn and continue in the same situation; here that would mean running with no authentication while an operator believes a provider is installed.
- `DATABASE_URL` is required: resolving a slug needs Postgres, and the lifespan refuses to start a provider without it.
- SSE endpoints use the `?token=<credential>` query parameter, since `EventSource` cannot set headers; the middleware accepts either.

Frontend side: `frontend/src/features/auth/auth-adapter.ts` is the contract and `frontend/src/features/auth/adapter/` the implementation, which a deployment replaces. Four modules split by runtime (`proxy.ts`, `server.ts`, `browser.ts`, `client.tsx`), because one module cannot be imported from the edge runtime, a Server Component, a directive-free browser module, and a client component at once. `/sign-in`, `/sign-up`, `/select-org` and `/mcp-consent` stay here as shells rendering one adapter component each, since the App Router resolves pages by file path. Public adapter config travels through `AUTH_PUBLIC_*` and the existing request-time runtime config.

### MCP OAuth 2.0 Authentication

The MCP server at `/mcp` uses OAuth 2.0 with PKCE and dynamic client registration. It is controlled by the `OAUTH_ISSUER_URL` environment variable.

- **Enabled**: Set `OAUTH_ISSUER_URL` to the public base URL of the backend (e.g. `https://backend.up.railway.app`). The MCP server is mounted and protected by OAuth.
- **Disabled**: Leave `OAUTH_ISSUER_URL` unset. The MCP server is not mounted and the `/mcp` endpoint is unavailable.

OAuth configuration:
- Clients auto-register via `POST /mcp/register` (dynamic client registration, RFC 7591).
- Authorization uses the code flow with PKCE (RFC 7636) via `GET /mcp/authorize`.
- With no provider installed the authorize endpoint auto-approves and binds the issued token to the synthetic `local` group.
- In **multi-tenant mode** the authorize endpoint parks the request as a `pending_oauth_consents` row keyed by an opaque `request_id` (migration `0003_pending_oauth_consent`) and redirects the browser to the provider's `deferred_consent_url`, which is `{FRONTEND_URL}/mcp-consent?request_id=<id>`. The page's shell renders the adapter's `ConsentGate`, which signs the user in and settles which group is being authorized; the platform's consent panel then POSTs `/mcp/consent/approve` with a session token. That endpoint is contributed by the provider, which verifies the caller and calls `approve_parked_consent(request, request_id, group_id)` from `identity/provider_services.py` to materialise the code bound to that `group_id`. That wrapper is the provider-facing call; it reaches the OAuth provider off `app.state` so a provider never does, and it raises `ConsentNotApprovable` for a link that expired or was already used, which is a 4xx rather than a server error. The parking machinery is platform code: it is about having more than one group to choose from, not about any one vendor.
- Token exchange at `POST /mcp/token` issues access tokens (1 hour) and refresh tokens (30 days). Each row carries a `group_id` so every tool call is scoped via the `RunContext` contextvar primed by `mcp/asgi_context.py`.
- [`IdentityMiddleware`](src/glossogen/server/identity/middleware.py) accepts MCP OAuth access tokens as a Bearer fallback on `/api/g/<slug>/...` requests, so the CLI can address REST endpoints with the same token issued for MCP.
- OAuth metadata is discoverable at `GET /mcp/.well-known/oauth-authorization-server`.
- Token state lives in Postgres (`access_tokens`, `refresh_tokens`, `authorization_codes`, `pending_oauth_consents`).

CLI surface (uses the same OAuth flow):
- `glossogen login` — walks the user through the OAuth handshake, stores `{access_token, refresh_token, group_slug}` in `~/.glossogen/credentials.json`. See `src/glossogen/oauth_client.py`.
- `glossogen whoami` — round-trips through `GET /mcp/whoami` to print the token's bound group.
- `glossogen push-to-prod` — bulk-uploads local runs to a configured remote via `/api/g/<slug>/runs/import`. Filters by label / scenario / report-present; idempotent on `run_id`. See `src/glossogen/prod_push.py`.
- `glossogen sync-metadata-to-prod` — for every local-evaluated run that's *already* on prod: PUTs the local labels onto `/api/g/<slug>/runs/{scenario}/{run_dir_name}/labels` when they differ, and PUTs the local evaluation report onto `/api/g/<slug>/runs/{scenario}/{run_dir_name}/evaluation` unconditionally (local is the source of truth — every PUT replaces the on-disk copy). Also syncs the label glossary: PUTs every local label description the remote is missing or records differently onto `/api/g/<slug>/labels/descriptions`; descriptions only the remote has are left alone. Use `push-to-prod` for runs not yet on prod. See `src/glossogen/prod_metadata_sync.py`.
- `glossogen analyze` — groups and aggregates many runs' metrics into one table. Same selection flags as `glossogen export`, plus `--grain`, `--group-by`, `--measure key:aggregate`, `--filter key:operator:values`, and `--list-fields`. Reads the runs directory directly, so no server and no database, and it is what a chart's numbers are checked against. See [docs/analysis.md](docs/analysis.md).
- `glossogen export` — exports many runs as CSV tables (`run_level` / `round_level` / `agent_level` / `message_level` / `round_context`, the last two opt-in since they read every run's event log) and optionally a zip of their run folders. Reads the runs directory directly, so it needs no server and no database, and it covers unevaluated and in-progress runs. Filter with `--scenario` / `--label` / `--run-id-contains` / `--knob`, or name runs with `--run-id`; the two forms cannot be combined. `--knob` takes one `<knob><operator><value>` condition on the run's recorded `scenario_config` and is repeatable; quote it when it contains `>` or `<`. See [docs/exporting-runs.md](docs/exporting-runs.md).

Implementation files:
- `src/glossogen/server/mcp/oauth_provider.py` — `OAuthAuthorizationServerProvider` implementation; `authorize` auto-approves when no provider is installed, otherwise parks the request and sends the browser to `provider.deferred_consent_url(...)`. The provider's own endpoint then reaches `approve_pending_consent` through `provider_services.approve_parked_consent`, never directly.
- `src/glossogen/server/mcp/whoami_router.py` — `GET /mcp/whoami` (OAuth token auth). Provider-agnostic: the token was minted here. `POST /mcp/consent/approve` is contributed by the identity provider instead.
- `src/glossogen/server/mcp/oauth_storage.py` — Postgres-backed storage for clients, codes, tokens, and pending consents.
- `src/glossogen/server/mcp/asgi_context.py` — ASGI wrapper that reads the bearer token, resolves its `group_id`, and primes `RunContext` for every tool call.
- `frontend/src/app/mcp-consent/` — the consent page. A shell around the auth adapter's `ConsentGate`; `features/mcp-consent/consent-panel.tsx` carries the copy and the Approve button.

## MCP Integration

The backend exposes an MCP (Model Context Protocol) server at `/mcp` for programmatic access to simulation data from LLM clients like Claude Code or Cursor. The MCP server is mounted inside the existing FastAPI app and uses OAuth 2.0 for authentication. Requires `OAUTH_ISSUER_URL` to be set.

### Available Tools

- `list_scenarios` — lists available scenarios with knobs files, metrics, and supported models/providers
- `list_runs` — paginated run listing with filtering by scenario, model, fork status, run status, and labels (AND-matched)
- `get_run_metadata` — lightweight metadata for a single run: agents, channels, configuration, evaluation summary, labels, and full lineage provenance (`parent_run_id` plus the structured `fork_source` / `replace_agent_source` / `fork_at_round_source` / `cross_run_replace_agent_source`)
- `list_derived_runs` — lists every run derived from a parent run (replace-agent, fork-at-round, cross-run-replace-agent), with derivation type, round boundaries, swapped/imported models, labels, and headline `round_success` scores. Uses the runs-index timeline-parent linkage; this can return fewer runs than an orchestrator `src=<run_id>` grouping label, which may span an entire experiment family
- `get_run` — full run content with messages; opt-in sections for reasoning, tool use, debug logs, and system prompts; filtering by agent or channel
- `get_knobs_schema` — returns a scenario's knobs JSON Schema and available knobs preset files
- `get_knobs_preset` — loads a knobs preset JSON payload by scenario and preset name
- `start_run` — launches a simulation subprocess with scenario, model, provider, and optional knobs
- `export_run_artifacts` — returns a relative download URL for a tar.gz bundle of the run's artifacts
- `export_agent_thread` — reconstructs one agent's thread (optional exclusive `cutoff_round`) and returns a drop-in provider-native request body (Anthropic Messages / OpenAI Chat); `output_format` defaults to the agent's own provider. Thin MCP wrapper over `thread_export.export_agent_thread_from_run_dir` (same orchestrator as the `glossogen export-thread` CLI and the `/runs/.../agents/{agent_id}/thread` REST endpoint)

### Connecting

From the web UI, click the **MCP** button on the runs page to see connection instructions. Clients discover OAuth automatically via the well-known metadata endpoint, so the config needs no auth headers.

**Claude Code:**

```bash
claude mcp add-json glossogen-runs '{"type":"http","url":"<API_URL>/mcp"}'
```

**Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "glossogen-runs": {
      "url": "<API_URL>/mcp"
    }
  }
}
```

Replace `<API_URL>` with the backend URL (e.g. `http://localhost:8000` for local development). The client handles OAuth registration, authorization, and token refresh automatically. In single-tenant mode the consent step auto-approves to the synthetic `local` group. In multi-tenant mode the client's browser tab opens `/mcp-consent`, where the auth adapter signs the user in and settles which group to bind the issued token to. See the **MCP OAuth 2.0 Authentication** section above for the full flow.

## Deployment

The application deploys to Railway as two services from a single repository.

### Docker

- `Dockerfile` (repo root) — Backend: Python 3.12, uv, weasyprint system dependencies
- `frontend/DockerfileFrontend` — Frontend: Node 22, three-stage build with Next.js standalone output

### Railway Configuration

The frontend service carries `frontend/railway.toml` (Dockerfile builder). The
backend is deployed from a published image rather than built from this repo, so
it has no config-as-code file here.

### Railway Dashboard Setup

**Backend service**: root directory `/`, volume mounted at `/data/runs`. Attach a Railway Postgres database. Its connection string becomes `DATABASE_URL`. The Dockerfile runs `alembic upgrade head` before starting the server.

Environment variables:
- `DATABASE_URL` — Postgres connection string (required; backend won't boot without it)
- whatever the installed identity provider reads — required for multi-tenant auth
- `ANTHROPIC_API_KEY` — required for simulations
- `ALLOWED_ORIGINS` — comma-separated frontend URLs for CORS (e.g. `https://frontend.up.railway.app`)
- `OAUTH_ISSUER_URL` — public backend URL to enable MCP OAuth (e.g. `https://backend.up.railway.app`)
- `OPENAI_API_KEY`, `HF_TOKEN` — optional provider keys

**Frontend service**: root directory `frontend`.

Runtime variables:
- `API_URL` — backend service URL (runtime variable, not a build arg)
- `AUTH_PUBLIC_*` — public values the auth adapter needs (browser-visible)
- the adapter's server-side secrets, read by `adapter/server.ts` / `adapter/proxy.ts`

**Deploy order**: Backend first (get URL) → set it as the frontend's `API_URL` variable → deploy frontend → update backend `ALLOWED_ORIGINS` with the frontend URL.

## Run Output Directory Structure

All simulation outputs use a standard directory layout. The JSONL event log is the canonical state ledger for a run. Every fork, replace-agent, cross-run, and fork-at-round operation locates the target event in the JSONL and writes a truncated copy into a new run directory.

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl              # Event log (messages, reasoning, round transitions)
├── {scenario_name}_debug.jsonl        # Debug log (JSON lines from Python logger)
├── {scenario_name}_report.json        # Evaluation report (written by evaluate)
├── {scenario_name}_stdout.log         # (pipe stdout here)
├── labels.json                        # JSON array of label strings (e.g. ["baseline_oss"])
├── note.md                            # Optional free-text note for the run
├── fork_manifest.json                 # (forked runs only) provenance: source_run_id, target_message_id
├── replace_manifest.json              # (replace-agent or fork-at-round runs) provenance + post-swap channel visibility; replaced_agent_id/replacement_model/replacement_provider are null for fork-at-round
├── cross_run_replace_manifest.json    # (cross-run replace-agent runs only) source_a/source_b/imported_model + post-swap channel visibility
├── imported_history_source.jsonl      # (cross-run replace-agent runs only) verbatim copy of Sim B's JSONL used to mount the imported agent's history
├── replace_config.json                # (replace-agent / cross-run / fork-at-round runs) merged scenario_config + model_overrides written by the orchestrator
├── resume_context_{agent_id}.json     # (resume / fork / replace-agent / cross-run runs) per-agent reconstructed pydantic-ai message history dumped at resume time for inspection
├── resume_context_{agent_id}_round_{R}.json  # (in-run scheduled swap) one file per AgentSwappedMidRun event capturing the swapped-in agent's seed history
├── language_repetition_messages.jsonl # (language_repetition metric) one row per primary-channel message: its per-message redundancy factor (judge, replica-averaged), keyed by message_id
├── protocol_explanation_responses.jsonl  # (protocol_explanation metric) one row per agent: its own free-text description of the protocol
├── protocol_explanation_usage.json    # (same) per-model token usage + cost for the explanation probe batch
├── protocol_probe_responses.jsonl     # (scenarios that implement get_protocol_probe_config) one row per (agent, question, replica)
├── protocol_probe_usage.json          # (same) per-model token usage + cost for that probe batch
├── protocol_probe_replica_self_similarity.json  # (same) within-run replica × replica matrices per (agent, question, cutoff)
├── protocol_probe_agent_pair_similarity.json    # (same) within-run agent × agent matrices per (question, cutoff); two-team runs
├── protocol_probe_cutoff_trajectory.json        # (same) per (agent, question) adjacent-cutoff series; multi-cutoff JSONLs
├── communication_open_coding.json               # (when communication_open_coding metric is run) free-form open-coding labels for this run
├── communication_feature_presence.json          # (when communication_feature_presence metric is run) per-category confidence vector against a consolidated ontology
└── multi_swap_cache.json              # cached per-phase round_success for multi-swap runs; regenerated whenever the JSONL's size or mtime changes
```

### Run Labels

Labels are short tags attached to a run for filtering and grouping in the UI and in evaluation queries. They live in `labels.json` inside the run dir as a JSON array of strings, and that file is the source of truth. When a database is present the server also mirrors each run's labels into the `runs.labels` column (`src/glossogen/server/runs/label_mirror.py`): the label union and label filtering read the mirror instead of opening one file per run, rows never mirrored are backfilled at server startup, and drift from direct file writes is repaired whenever the server reads the run's file anyway (a listed page row, or the run's detail).

A label can optionally carry a description, recorded once per group in the label glossary (`src/glossogen/label_descriptions/`) rather than per run: `glossogen describe-label <label> --description "what it means"`, or `PUT /api/g/{group_slug}/labels/descriptions` with body `LabelDescription{label, description}`. The UI shows it when hovering a label chip. Record one when creating a cohort label, so the next reader does not have to reverse-engineer what the cohort was for.

Two ways to apply them:

1. **Backend API**: `PUT /api/g/{group_slug}/runs/{scenario}/{run_dir_name}/labels` with body `UpdateLabelsRequest{labels: list[str]}` — see [router.py:409](src/glossogen/server/runs/router.py#L409). The PUT replaces all labels (it does not append), so include any existing labels you want to keep.
2. **Direct file write** (orchestrator scripts): write `labels.json` directly to the run dir as soon as the dir exists. Faster than the API and avoids needing the backend to be running. Example:
   ```bash
   echo '["baseline_oss"]' > "runs/veyru/<timestamp>/labels.json"
   ```

**Important**: the PUT replaces the whole list, so read the current labels first when adding to them. (`glossogen evaluate` no longer writes `labels.json`; eval-derived `eval:*` labels only exist on runs evaluated before that changed.)

### DO NOT use substring matching to bulk-relabel runs

I (Claude) once destroyed eval-derived labels on 40 runs by writing this:

```bash
# ❌ NEVER do this. Will match runs with ANY of these substrings, including
#    legitimately-evaluated runs that just happen to have "baseline" + the
#    budget tier in their labels list.
for d in ./runs/veyru/*/; do
  content=$(cat "$d/labels.json")
  if [[ "$content" == *'"baseline"'*'"budget=2000"'* ]]; then
    echo '["baseline_oss", "budget=2000"]' > "$d/labels.json"   # WIPES eval labels
  fi
done
```

The pattern matched runs labeled `["baseline", "budget=2000", "eval:content_filter_refusal:0", "eval:round_success:pass", ...]` and overwrote all of those eval-derived labels. They have to be regenerated via `glossogen evaluate`.

**Rules when bulk-modifying labels.json:**

1. **Always parse as JSON, never substring-match the file contents.** Use Python (`json.load`) and compare list membership precisely (`labels == ['baseline_oss', 'budget=2000']` not `'baseline_oss' in content`).
2. **Scope by run identity, not by label content.** If you're modifying runs you just created in this session, list those run dirs by mtime or by tracking the run IDs at launch. Don't infer them from current label state.
3. **Never overwrite — append.** If you must modify labels, read existing JSON, append/remove specific entries, write back. Only blow away the whole list if you're certain the run has no eval-derived labels (i.e. you just created it and `glossogen evaluate` has not run on it).
4. **If unsure, dry-run first.** Print which runs you'd modify and their current labels; ask the user to confirm before writing.

### JSONL-Backed Run History

The `{scenario_name}.jsonl` file is the canonical event log for a run. `EventLogger` appends one line per event and never mutates earlier lines, so every event has a stable byte offset for the lifetime of the run.

Forks, replace-agent, cross-run replace-agent, and fork-at-round all locate their target event in the source JSONL (via `find_event_offset` / `find_message_offset` in `src/glossogen/run_archive.py`), copy the source run directory, and truncate the JSONL in the new directory to end at that event. Run dirs created before this change carry a legacy `.git/` subdirectory; `load_events` removes it on first read (`strip_legacy_git_dir`).

## Running Simulations

Agents connect to a shared MCP server via the Pydantic AI framework. A game clock manages round progression. Always run simulations as a background process, piping all output to a log file.

**Canonical seed: `seed=42`.** Always use `seed=42` when launching comparison runs so results are comparable against the baseline. Do not vary the seed across replications. The seed fixes the case set, so running multiple times with the same seed measures LLM stochasticity on an identical workload. Only change the seed if the user explicitly asks for it.

**Canonical judge: `claude-haiku-4-5-20251001`.** Set `judge_model: "claude-haiku-4-5-20251001"` and `judge_provider: "anthropic"` in every scenario knobs file. Keeping the judge fixed across runs holds judge-side noise constant so cross-run comparisons measure agent behavior, not judge variance. Only change the judge if the user explicitly asks for it.

### Hydra-Style Config & Overrides

The `run` subcommand uses a unified config system inspired by Hydra. `--config` provides the scenario knobs, and trailing `key=value` arguments override individual fields using dot-notation. The `agents.*` namespace is reserved for per-agent model/provider overrides.

`--config` takes the name of a preset the scenario ships (`knobs_default`, `knobs_intern`, ...), or a path to a JSON file of your own; a file wins when the argument is one. It is required: nothing picks a configuration on your behalf. Naming the preset rather than its path is what makes the same command work from this checkout and from an installed package, and `--knobs` on the swap and resume flows resolves the same way.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --config <preset-name> \
  [key=value overrides...] \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

Required flags: `--model`, `--provider` (`anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted`), `--runs-dir`, `--config <preset-name|path>`.
Optional flags: `--max-agent-turns` (default: 200).

The `self-hosted` provider points pydantic-ai at any OpenAI-compatible chat-completions endpoint. `SELF_HOSTED_BASE_URLS` is a JSON map from model name → `/v1` URL, so multiple self-hosted models can coexist; `SELF_HOSTED_API_KEY` is the bearer token shared across them. Reference deployments are in `modal/` (Llama 3.3 70B + Qwen3-32B, both vLLM with tool calling); see `modal/README.md` for deploy steps. Once deployed and the env vars are set:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config knobs_default \
  > ./runs/veyru_stdout.log 2>&1 &
```

The pricing entry in `src/glossogen/token_pricing.py` is keyed by the literal model name (case-sensitive prefix match after dots→dashes); add a new entry there if you serve a different model.

**Self-hosted context budget (`agent_max_tokens` knob).** Simulation agents' per-cycle output cap is the `agent_max_tokens` knob (`BaseKnobs`, default `16384`), not `LLM_MAX_TOKENS`. Self-hosted models are served at a small fixed context (Llama 3.3 70B is `--max-model-len 24576` in `modal/serve_llama.py`), and `input + agent_max_tokens` must stay under it or vLLM 400s with `"maximum context length is 24576 tokens"` and the run stalls. For **replace-agent / swap / cross-run** runs with a self-hosted agent, the swapped-in agent's *reconstructed history accumulates* (the veyru observer grows to ~18k tokens over a 10-round swap), so the default `16384` output cap overflows. **Set `agent_max_tokens: 2048` in the `--knobs` for self-hosted swap runs** (veyru outputs are short tool calls, so it truncates nothing). Raising `--max-model-len` instead risks KV-cache OOM on H100:2; see `modal/README.md`. The platform also serializes parallel tool calls in reconstructed history for self-hosted agents automatically (vLLM rejects multi-tool-call turns); no action needed there.

Examples:

```bash
# Veyru on its default preset
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  > ./runs/veyru_stdout.log 2>&1 &

# Veyru with per-agent model overrides
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  agents.stabilization_engineer.model=gpt-5.4 agents.stabilization_engineer.provider=openai \
  > ./runs/veyru_stdout.log 2>&1 &

# Override knobs inline on top of a base config
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_intern \
  max_round_duration_seconds=120 round_count=20 \
  > ./runs/veyru_stdout.log 2>&1 &
```

Override values are auto-parsed as JSON: `rounds=5` becomes int, `enabled=true` becomes bool, `name=alice` stays string.

Check progress by reading the stdout log file or the JSONL event log.

#### Knob co-dependencies: watch for cross-field validators

Scenarios' knob Pydantic models can have cross-field validators that reject otherwise-valid-looking inline overrides. Toggling one knob without its sibling fails preflight validation, the glossogen run subprocess exits before claiming a run directory, and any orchestrator that simply launches and polls for a new dir will silently lose the spec.

Known cases:

- **veyru**: `postmortem_after_swap=true` requires `postmortem_enabled=true`. When sweeping with `postmortem_enabled=false`, also pass `postmortem_after_swap=false` (the default knobs JSON has it set to true).

Defensive launcher pattern: when overriding a knob, also override every knob the scenario's `model_validator` checks against it. If you're unsure, run one foreground launch first to surface validation errors before queueing a sweep. Those errors land in the launch's stdout/stderr log, not in the orchestrator log.

### Live Streaming

Every `glossogen run` starts an embedded streaming server on an ephemeral port and writes a `stream.json` manifest to the run directory. The `glossogen serve` process discovers this file and proxies the simulation's SSE stream to connected frontends. When the simulation ends, `stream.json` is deleted and the server falls back to JSONL tailing for the completed run.

### Resuming Failed Simulations

If a simulation errors midway through, resume from the last checkpoint using the `--resume` flag pointing at the existing run directory.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> \
  --resume ./runs/<scenario>/<timestamp> \
  --config <same-preset-or-file-as-the-original> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The `--resume` flag requires the same `--config` as the original run. `--runs-dir` is not needed when resuming; `--resume` names the directory.

### Replacing an Agent (Round-Level Rewind)

Fork a finished run after a chosen round with one specific agent restarted on a fresh history while every other agent keeps its full reconstructed history. `--after-round N` keeps rounds 1..N complete, verdict and postmortem included, and the replacement enters round N+1. Useful for asking "could a fresh agent follow the engineer from here on?". It answers empirically what a judge only estimates.

```bash
glossogen replace-agent veyru \
  --source-run-dir ./runs/veyru/<timestamp> \
  --after-round 4 \
  --replaced-agent-id field_observer \
  --model claude-sonnet-4-6 --provider anthropic \
  --runs-dir ./runs \
  [--rounds-after K] \
  [--visible-history-channel CHANNEL ...] \
  [--knobs path/to/overrides.json]
```

Internals: `resolve_fork_boundary` picks the truncation anchor for `--after-round N`: the source's `RoundAdvanced(N+1)` when one exists, or the last event before `SimulationEnded` when N was the source's final round. `copy_run_at_event` then copies the run directory with the JSONL truncated there. The clone therefore contains round N fully ended (game phase, postmortem, both `round_ended` events) but no `injection_delivered` events for round N+1. On resume the game clock opens round N+1 (recording a fresh `RoundAdvanced(trigger="fork_after_round")` on a final-round fork) and fires that round's injections fresh. The replaced agent's full event log is preserved on disk; its reconstructed pydantic-ai history is stripped of `text` / `thinking` parts and any tool calls targeting blocked channels (e.g. veyru's postmortem channels). The veyru world's per-team `outcomes` list is seeded from the source's `veyru_case_started` / `veyru_stabilization_judged` / `round_ended` events via `restore_state_from_events`, so the entry round's "PREVIOUS VEYRU RESULT" block reflects the source's actual round-N outcome. `--after-round` must be >= 1. Non-replaced agents stay on their exact original models.

`--rounds-after` defaults to `source_round_count - after_round` (the source rounds past the boundary); forking after the source's final round requires an explicit value. A `round_count` carried by `--knobs` (every shipped preset has one) sets the fork's total rounds when the flag is omitted, and must agree with it when both are given, so a full preset passed to `--knobs` alongside `--rounds-after` errors unless the numbers line up; drop `round_count` from override files. The fork's `round_count` is set to `after_round + rounds_after`. The manifest keeps the frozen on-disk schema: `round_start` is the entry round (`after_round + 1`) and `rounds_after_swap` is `round_count - round_start`.

**Per-channel history visibility (platform feature).** The replace-agent flow chooses, per channel the replaced agent is a member of, whether that channel's prior messages remain visible after resume.

- `--visible-history-channel CHANNEL` (repeatable): channels listed here keep their pre-resume history visible to the replaced agent. All other channels they belong to have `member_join_index` bumped to the current message count, so `read_channel` returns only post-resume messages there.
- When the flag is omitted, the CLI consults the source run's `replace_agent_default_channel_visibility: dict[str, bool]` knob (defined on `BaseKnobs`). Channels not listed in that map default to visible. Scenarios encode their per-channel defaults in the preset knob JSON files; no scenario code is required.

**Per-scenario knob overrides.** `--knobs` takes a preset name or a path to a JSON file, merged onto the source's `scenario_config` before validation. Veyru exposes `postmortem_disabled_at_start: bool` for this flow: setting it to `true` flips `world.disable_postmortem_globally()` at world construction, dropping the postmortem channel for the rest of the resumed simulation (no postmortem injections, no postmortem phase, sends to postmortem are rejected).

Replace-agent runs appear in the run list with a "Replaced" badge.

### Cross-Run Replacing an Agent (Round-Level Rewind, Different Source for the Imported Agent)

Cross-run replace-agent is a sibling of replace-agent that imports an agent from a *different* completed run (Sim B) into a target run (Sim A) at a chosen round boundary. Same scenario and same `agent_id` only. The imported agent retains its **full pydantic-ai history** (text + thinking + tool calls) from Sim B; non-replaced agents in Sim A continue with their full Sim A history.

```bash
glossogen cross-run-replace-agent veyru \
  --source-a-run-dir ./runs/veyru/<sim_a_timestamp> \
  --source-b-run-dir ./runs/veyru/<sim_b_timestamp> \
  --replaced-agent-id field_observer \
  --after-round 14 \
  --runs-dir ./runs \
  [--source-b-round-end N] \
  [--model M --provider P] \
  [--knobs path/to/overrides.json] \
  [--rounds-after K] \
  [--visible-history-channel CHANNEL ...]
```

**Default for `--source-b-round-end`** is `min(after_round, B_max_round)` — temporally aligned with Sim A's fork boundary but clamped to the last round Sim B actually played, so the imported agent always gets the largest possible slice of B's history without exceeding what B reached. Example: `after_round=19` against a Sim B that only ran 15 rounds → `source_b_round_end=15`.

**Default for `--model`/`--provider`** is to read Sim B's `AgentRegistered` for the imported agent (so the imported agent runs under the same model it used in Sim B). Override with `--model M --provider P` to test cross-team behaviour with a different model. Both must be provided together.

**Imported agent history reconstruction.** The cross-run flow extends `AgentHistoryFilter` with an `imported: ImportedHistory | None` slot (events + target_timestamp + cutoff_round). When set, that agent's history is rebuilt from Sim B's `imported_history_source.jsonl` (a verbatim copy of Sim B's JSONL placed inside the new run dir) and the agent's system prompt is taken from Sim B's `AgentRegistered`. All other agents continue to use Sim A's events. Channel-blocking on the reconstructed history covers the scenario's default blocked channels (e.g. veyru's postmortem) plus any channel the imported agent had in Sim B but is missing in Sim A.

**Postmortem on cross-run runs.** The CLI does not auto-set `postmortem_disabled_at_start` — pass `--knobs /tmp/cross_team_knobs.json` with `{"postmortem_disabled_at_start": true}` for veyru cross-team experiments so opus and gpt-5.4 don't have a backchannel to re-align protocols after the swap. Forgetting this contaminates cross-team experiments.

**Manifest + provenance.** Persisted as `cross_run_replace_manifest.json` (parallel to `replace_manifest.json`). Carries both `source_a_run_id` (target timeline) and `source_b_run_id` (where the imported agent came from), plus `imported_model`/`imported_provider`, `round_start` (the entry round), `source_b_round_end`, `rounds_after_swap`, `replaced_agent_id`, `channels_with_visible_history`, `blocked_tool_call_channels`. The discovery layer surfaces this on `RunSummary` / `RunDetailResponse` as `cross_run_replace_agent_source`. Cross-run runs appear in the run list with a violet "Cross-run" badge that links back to both sources.

**Verifying the imported history.** Each resumed run writes `resume_context_{agent_id}.json` to the new run dir capturing the exact reconstructed pydantic-ai messages handed to that agent on its first turn. For cross-run runs, `resume_context_<replaced_agent_id>.json`'s tail should match Sim B's last few `field_observer` (or whichever role) messages verbatim, which confirms the cross-run history is being mounted from Sim B and not contaminated by Sim A.

**Label convention.** Cross-run runs are labelled `cross_team` plus a range tag like `15-25` (rounds played post-swap). That label lets analysis tooling group cross-team runs and compare `round_success_after_resume` per `(imported_model, after_round)` bucket against both Source A and Source B accuracy on the same rounds. Apply labels by writing `labels.json` directly *before* `glossogen evaluate` runs (the eval-derived labels merge into that file).

**`round_success_after_resume` works for both flows.** The metric reads either `replace_manifest.json` or `cross_run_replace_manifest.json` and projects to a common `ResumeAnchor` (`resume_anchors.py`), whose `round_start` / `rounds_after_swap` window uses the manifests' frozen field names. For cross-run runs, the comparison is against Sim A (`source_a_*`): "did the imported agent perform better/worse than what the original agent achieved over the same window?".

### Fork at a Round (Post-Hoc, No Agent Replacement)

Fork-at-round clones a finished run keeping rounds 1..N complete and plays round N+1 onward without restarting any agent. Every agent keeps its full reconstructed history; the fork differs from the source only through merged knob overrides. Useful for post-hoc multi-swap studies (inject new `scheduled_events`), toggling `postmortem_enabled` mid-experiment, or replaying a run's remaining rounds on a different configuration. `--rounds-after` sets how far the fork plays, past the source's own end included. A `round_count` carried by `--knobs` (every shipped preset has one) does the same when the flag is omitted, and must agree with it when both are given.

```bash
glossogen fork-at-round veyru \
  --source-run-dir ./runs/veyru/<source_timestamp> \
  --after-round 15 \
  --runs-dir ./runs \
  [--knobs path/to/overrides.json] \
  [--rounds-after K]
```

Required: `scenario_name` (positional), `--source-run-dir`, `--after-round` (≥ 1), `--runs-dir`. Optional: `--knobs <preset-name|path>` (shallow-merged onto source `scenario_config`), `--rounds-after K` (`round_count` is set to `after_round + rounds_after`; default is `source_round_count - after_round`; forking after the source's final round requires an explicit value, and the resumed clock then records the advance fresh as `RoundAdvanced(trigger="fork_after_round")`).

**Mechanism.** The flow reuses the `replace-agent` machinery with `replaced_agent_id=None`. `resolve_fork_boundary` picks the anchor (the source's `RoundAdvanced(after_round + 1)`, or the last event before `SimulationEnded` on a final-round fork), the run directory is copied with the JSONL truncated there, `model_overrides` is built by pinning every agent to its source-active registration, the merged config writes `replace_config.json`, and the resumed subprocess launches via `glossogen run --resume`. A boundary behind an already-fired `scheduled_events` swap is refused: the swap's history filters and swapped-in model live only in its config and `AgentSwappedMidRun` event, so the fork would rebuild that seat with its predecessor's full turns under the pre-swap model. Fork before the swap fires (post-hoc swap studies inject new `scheduled_events` into a clean source), or replace that same agent. The manifest is the standard `replace_manifest.json` with `replaced_agent_id`, `replacement_model`, `replacement_provider` all `null` and `channels_with_visible_history` / `blocked_tool_call_channels` empty; `round_start` records the entry round and `rounds_after_swap` records `round_count - round_start`.

**Resume ordering on the boundary round.** The game clock's resume branch defers `deliver_round_injections` until after agent runners are launched and the boundary hook fires. The supervisor calls `dispatch_resume_boundary_events()` (which executes any `scheduled_events` bucketed at the entry round) then `deliver_initial_round_injections()`. This mirrors the normal `_advance_round` order (boundary hook → injection delivery) and ensures that when a `swap_agent` event fires exactly at the entry round, the round's injection lands in the post-swap session rather than the cancelled predecessor's queue. The `RoundBoundaryScheduler` is pre-seeded from `RewindState.rounds_with_fired_scheduler_events` (set of round numbers carrying `AgentSwappedMidRun` or `PostmortemDisabledMidRun` in the loaded events) so boundaries that already fired in the source, or in a crashed-and-resumed run, are not re-dispatched.

**Inherited `scheduled_events` semantics.** When the source's config carries `scheduled_events`, those entries are preserved unless overridden. Events at `at_round <= after_round` never re-fire: the fork keeps those rounds as the source played them. An event at `after_round + 1` fires on resume, by design, because the cloned JSONL is captured *before* the source's scheduler dispatches that boundary. Pass `--knobs '{"scheduled_events": [...]}'` to override the list (e.g. add a post-hoc swap at a later round, or clear the schedule entirely).

**Picking the subprocess `--model`/`--provider`.** Since every agent is pinned via `model_overrides`, the top-level `--model`/`--provider` flags are unused. The CLI selects the first source-active registration's pair as the defaults so `glossogen run`'s required argparse flags are satisfied.

**Knob-schema evolution caveat.** If the scenario's knobs schema gained a required field after the source was created, validation will reject the merged config until the missing key is supplied. Pass it via `--knobs` for that fork (example: veyru's `easy_round_numbers: frozenset[int]` was added later, so older veyru runs need `--knobs '{"easy_round_numbers": [1, 2, 3, 6, 13]}'` to fork).

**Discovery.** The manifest is surfaced as `RunSummary.fork_at_round_source` / `RunDetailResponse.fork_at_round_source` (`ForkAtRoundSource { source_run_id, after_round, rounds_after, target_event_id, forked_at }`, translated from the stored window); when `replaced_agent_id` is null, `replace_agent_source` is suppressed in favour of this field.

**FE surfaces.** The run-detail header shows a green `Forked after round N (+K)` badge linking back to the source. The runs-list row shows a green `↺R{N}` badge naming the boundary round. Multi-swap runs render one `AgentSwapPointFab` per scheduled swap so users can scroll directly to any boundary.

**Crash recovery.** `--resume` on a fork whose log grew past its boundary anchors at the log's end, keeping every advance, injection, and verdict the crashed launch already recorded; a fork with only agent re-registrations past its boundary (never launched, or crashed during startup) resumes at the boundary. Play means the agents' own event types (messages, LLM cycles, tool calls); scenario and world events the clock flushes while opening a round count as recoverable progress, not play. A cross-run fork recovers the same way unless it actually played: the imported agent's post-boundary turns cannot be re-seeded from source B, so a played cross-run fork must be re-created. Forking a cross-run run is refused, and so is any boundary behind an already-fired in-run swap. A replace-agent run accepts only a re-replacement of the same seat: any other derivation would rebuild the replaced seat pass-through from a log whose history filters live only in the source's manifest, which clones do not inherit. Fork clones carry no `simulation_ended` lines and no inherited derivation manifests, so a fork of a crashed-then-recovered source never trips the `simulation_ended` evaluation gate early.

**Lineage chain.** `replace_manifest.json` carries `source_run_id` + `source_run_dir`, so chaining fork-of-fork-of-fork is traceable: walk `source_run_id` recursively to reach the root. The same field powers the badge's link target.

### In-Run Agent Swaps via `scheduled_events`

The in-run scheduler swaps agents at scheduled round boundaries inside a single live simulation. Multiple swaps fire across the same run on one continuous timeline (Phase A → B → C → D for three swaps).

Configure via the `scheduled_events` knob (defined on `BaseKnobs`). Two event types:

```jsonc
{
  "scheduled_events": [
    { "type": "set_postmortem", "at_round": 16, "enabled": false },
    { "type": "swap_agent", "at_round": 16, "agent_id": "field_observer",
      "model": "claude-sonnet-4-6", "provider": "anthropic",
      "channel_visibility": { "link": { "kind": "full" } } },
    { "type": "swap_agent", "at_round": 31, "agent_id": "stabilization_engineer",
      "model": "claude-sonnet-4-6", "provider": "anthropic",
      "channel_visibility": { "link": { "kind": "from_round", "round_floor": 16 } } }
  ]
}
```

`channel_visibility` is a discriminated union per channel ID:
- `{"kind": "full"}` — full predecessor history visible to the swapped-in agent.
- `{"kind": "none"}` — channel hidden entirely (no reads, no sends, history not retained in seed).
- `{"kind": "from_round", "round_floor": R}` — predecessor `read_channel` returns dropped; `send_message` calls retained from round `R` onward.

Channels not listed in `channel_visibility` default to `Full`.

**Globally disabled channels** (e.g. Veyru's postmortem after `set_postmortem`) are forced to `none` by the runtime regardless of the swap config. The swap logic queries `ScenarioWorld.get_globally_disabled_channels()` and overrides each entry's visibility before reconstructing the seed history. Globally disabled channels are also excluded from the swapped-in agent's wake-up `NewMessagesNotification`.

**Notification round floor**: `read_notifications` is not channel-scoped, so its tool returns are not filtered by `channel_visibility`. The history builder derives a notification floor as `min(v.round_floor for v in channel_visibility.values() if v.kind == "from_round")` and drops `read_notifications` calls whose source `ToolCallInvoked.round_number` falls below it. The filter applies to every history-reconstruction caller (replace-agent, fork, cross-run, in-run swap).

**Per-swap resume context**: each swap writes `resume_context_<agent_id>_round_<R>.json` to the run directory. The file captures the swapped-in agent's pydantic-ai message history at swap time.

**FE viewer**: the run viewer renders one tab per `(agent_id, generation)`. Single-instance agents render a flat sidebar row; multi-instance agents render a parent role row with indented `Gen k · rA-B` sub-rows. The chat pane renders a dashed indigo `agent-swap-divider` between adjacent rounds that straddle a swap.

**Evaluation**: `round_success_after_resume` walks every `AgentSwappedMidRun` event and emits one Measurement per swap (`round_success_after_resume_round_<R>_<agent_id>`). The baseline window for each anchor is the previous phase in the same run; the summary carries `Δ vs source: ±N pp` between adjacent phases.


### Per-Agent Model Overrides

Each agent uses the default `--model` and `--provider` unless overridden. Per-agent overrides live in `model_overrides` inside scenario knobs/config. The CLI also supports `agents.*` dot-notation overrides, which are normalized into `model_overrides`.

**CLI usage:** Pass dot-notation overrides:

```bash
glossogen run veyru --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  agents.stabilization_engineer.model=gpt-5.4 agents.stabilization_engineer.provider=openai
```

Or embed in the `--config` JSON file under `model_overrides`:

```json
{
  "max_round_duration_seconds": 300,
  "model_overrides": {
    "stabilization_engineer": {"model": "gpt-5.4", "provider": "openai"},
    "field_observer": {"model": "claude-opus-4-6", "provider": "anthropic"}
  },
  "round_count": 12
}
```

**MCP `start_run`:** the MCP tool accepts a knobs/config payload containing `model_overrides` (no top-level override field). Preflight validation reads `model_overrides` from knobs/config, validates provider names, and validates agent IDs against scenario roles before launch.

### IMPORTANT: Monitoring Long-Running Processes

When running simulations, evaluations, or any long-running background process, **always** follow this pattern:

**No `sleep`. Use a background heartbeat wake-up and do the checks yourself on wake.** Never run a foreground `sleep` (including any sleep→check→report loop). It blocks the whole session so the user cannot chat. The working mode:

1. Launch the process in the background (with `run_in_background` or `&`).
2. Arm a **periodic heartbeat** monitor whose only job is to wake you every ~30–60s — the Monitor tool with `while true; do echo "$(date) tick"; sleep 45; done`, or an equivalent `run_in_background` loop that keeps emitting. Each emitted line is a notification. The internal `sleep` inside a *background* watcher is fine; only a *foreground* block is forbidden.
3. On EACH heartbeat notification, run the real check yourself in your turn — an instant snapshot (parse the JSONL with Python/`json`, tail the log, count rounds, grep for errors) — report briefly, and stop the heartbeat (TaskStop) once done.
4. **Do NOT gate the wake-up on a single condition** (`until grep -q '<pattern>' <file>; do sleep; done`). A condition embeds an assumption — a grep string that doesn't match the real (often compact, no-space) JSONL serialization, a guessed event field, a wrong path — and if it's wrong the monitor fires **never** and you hang silently. A heartbeat can't silently fail: a bad assumption costs one wasted tick, not an infinite hang. Only use a condition-based exit when you've *verified* the exact match string against real output first. See memory `feedback_monitor_heartbeat_not_condition`.
5. For on-demand status, run a single instant snapshot command — never a sleep loop.

**Sim runs cost money and time, so monitor them rather than waiting.** Every 1–2 minutes while a launcher or eval is running, tail its log, count running sims per model, and verify no errors / no stuck sims / no duplicate launches. Long unattended gaps are not acceptable: a launcher that's silently looping on a misconfigured spec, a sim caught in a death-spiral retry loop, or a duplicate launch can burn through hours of API spend before the user notices. If you've already launched something and have downtime, fill it with a check rather than waiting for the user to ask.

**Per-launch sanity checks** (after every launcher iteration, not just at the end):

- Tail the orchestrator log (last 5-10 lines). Look for `WARN`, `ERROR`, `Traceback`, or empty `new_run_id=` (failed launch). Any of those = investigate immediately.
- `pgrep -f "Python -m glossogen run veyru --model <model>"` for each provider. If a queue's count is below cap and there are unlaunched specs in that queue, the launcher is stuck or misconfigured — diagnose now.
- For each launched run, audit `(labels.json, source_run_id, model)` against the spec list. Per-cell replica counts must match the plan exactly. Duplicates from re-launching, restarts, or buggy queue logic are the #1 wasted-spend bug.
- Tail at least one sim's `<scenario>_stdout.log` to confirm rounds are advancing — `grep -c '"round_advanced"' <jsonl>` and verify the count is climbing between checks.

**Never set wakeups longer than ~10 min while runs are active** unless the runs themselves take many hours. The user expects active oversight: short-interval checks that catch bugs in their first iteration, not 30-min snoozes that let 20 mis-specced sims run to completion before the next look.

### Launching Replace-Agent Runs in the Background

`glossogen replace-agent` is a one-shot CLI that prepares the new run directory and spawns the simulation as a detached subprocess (`subprocess.Popen` with `start_new_session=True`). The CLI returns immediately with `new_run_id=...` and `new_run_dir=...`; the simulation runs independently and writes its own `<scenario>_stdout.log` inside the new run directory.

Single replace-agent run, monitor pattern:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
  --source-run-dir ./runs/veyru/<source_timestamp> \
  --after-round 14 \
  --replaced-agent-id field_observer \
  --model gpt-5.4 --provider openai \
  --runs-dir ./runs \
  --knobs /tmp/replace_knobs.json
# CLI prints new_run_id=veyru/<new_timestamp>; that subprocess is now running detached.
# Monitor via a background wake-up (run_in_background until-loop or Monitor tool) on
# ./runs/veyru/<new_timestamp>/veyru_stdout.log — never a foreground sleep loop.
```

### Parallel Replace-Agent Orchestration

To run several replace-agent variants while keeping at most N simulations live, use a small bash orchestrator. Each `glossogen replace-agent` call returns in ~25s after spawning its detached `python -m glossogen run veyru ... --resume` subprocess; the orchestrator polls active simulations via `pgrep` against the `Python -m glossogen run ... --resume` cmdline, sleeps when full, and launches the next spec when a slot frees up.

**Parallelism policy: per-provider, never shared.** Each provider has independent rate limits and capacity, so the orchestrator must:

- **Cap per model at 15 concurrent sims** (the Anthropic + OpenAI accounts comfortably sustain this).
- **Run a separate queue per model in parallel** so a paused `gpt-5.4` queue (waiting for an OpenAI slot) never holds back the `claude-sonnet-4-6` queue. Strict-sequential single-queue orchestrators are a bug: with mixed-model specs, the queue blocks on the current spec's model and idles every slot on the other provider until the current spec launches. Always use per-provider parallel queues — typically two background subshells joined by `wait`.

Reference shape for a per-provider parallel orchestrator (save as `/tmp/replace_orchestrator.sh` or anywhere outside the repo):

```bash
#!/bin/bash
cd "$(git rev-parse --show-toplevel)"

RUNS_DIR=runs
LOG=/tmp/replace_orchestrator.log

# Per-model specs (entries are scenario-specific — at minimum source + knobs).
declare -a GPT_SPECS=(
  "<source_a> /tmp/replace_knobs.json"
  "<source_b> /tmp/replace_knobs.json"
)
declare -a SONNET_SPECS=(
  "<source_c> /tmp/replace_knobs.json"
  "<source_d> /tmp/replace_knobs.json"
)

count_running_for_model() {
  # Match python simulation processes only — capital "Python" comes from the
  # homebrew python.framework binary path, so bash/pgrep subshells that quote
  # the pattern literally do not false-match.
  pgrep -f "Python -m glossogen run veyru --model $1" 2>/dev/null | wc -l | tr -d ' '
}

launch_one() {
  local model=$1 provider=$2 source=$3 knobs=$4
  echo "$(date) [$model] launching source=$source knobs=$knobs" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
    --source-run-dir "runs/veyru/$source" \
    --after-round 14 --rounds-after 11 \
    --replaced-agent-id field_observer \
    --model "$model" --provider "$provider" \
    --runs-dir "$RUNS_DIR" \
    --knobs "$knobs" >> "$LOG" 2>&1
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

process_queue_gpt() {
  for spec in "${GPT_SPECS[@]}"; do
    read -r source knobs <<< "$spec"
    while [ "$(count_running_for_model gpt-5.4)" -ge 6 ]; do sleep 30; done
    launch_one gpt-5.4 openai "$source" "$knobs"
  done
  echo "$(date) [gpt-5.4] queue complete" >> "$LOG"
}

process_queue_sonnet() {
  for spec in "${SONNET_SPECS[@]}"; do
    read -r source knobs <<< "$spec"
    while [ "$(count_running_for_model claude-sonnet-4-6)" -ge 6 ]; do sleep 30; done
    launch_one claude-sonnet-4-6 anthropic "$source" "$knobs"
  done
  echo "$(date) [sonnet] queue complete" >> "$LOG"
}

echo "=== Started at $(date) ===" >> "$LOG"
process_queue_gpt &
process_queue_sonnet &
wait
echo "$(date): all launches complete" >> "$LOG"
```

**Key points:**
- Two background subshells (`process_queue_gpt &`, `process_queue_sonnet &`) + `wait` to join — gpt and sonnet queues advance fully in parallel.
- Each `count_running_for_model` query is tightly anchored on `--model <name>` so the two queues never count each other's sims.
- `-ge 6` per model means at most 12 concurrent sims total across both providers.
- If you only have a single-model workload, just remove the unused queue function — but never go back to a single shared `count_running` that mixes models.

Launch the orchestrator detached so it survives the session:

```bash
nohup bash /tmp/replace_orchestrator.sh > /tmp/replace_orchestrator.stdout 2>&1 &
disown
```

Monitoring pattern (every ~30s):

```bash
tail -20 /tmp/replace_orchestrator.log
pgrep -af "Python -m glossogen run veyru .* --resume"
```

`pgrep` pitfalls:
- The pattern **must** anchor on `Python` (capital) so bash/zsh subshells that contain the string verbatim don't false-match. The same applies to any wrapper command (e.g. a `Bash` tool call running `pgrep` on a string that quotes the pattern — that command's argv contains the pattern, and a loose pattern like `glossogen run veyru` will count it).
- Same caveat for the orchestrator's `count_running` function — keep it in a function (not inlined into a wrapping command) and use the tight pattern.

The orchestrator has no automatic recovery: if it dies, simulations keep running but no further launches happen. To resume, recompute the remaining queue (subtract already-launched specs from your full plan) and relaunch with the trimmed `queue=(...)`.

## Running Evaluations

### NEVER evaluate a run before it has emitted `simulation_ended`

**The only safe "this run is finished" signal is the `simulation_ended` event in the JSONL.** Do not gate evaluation (or any "completed" check) on a round count such as `grep -c '"round_advanced"' >= round_count` or `round_advanced.round_number == <last>`. `round_advanced` to round N fires when round N **starts**; round N's `RoundResultRecorded` is not written until round N **ends** (after its game phase + postmortem). So a count-based gate fires while the final round is still running and evaluates a run that is missing its last round. `round_success` then reads `N-1` rounds (e.g. `6/14` instead of `7/15`), and any per-round export keyed off `round_success` silently drops the final round's data.

This exact bug clipped the last round from 13 veyru `channel_noise` runs (their `rolling_eval.sh` used a `round_advanced >= 15` gate); re-evaluating the untouched JSONL produced the correct `/15`. The data was always complete; only the premature eval was wrong.

Rules for any launch-then-evaluate or scan-for-complete orchestration:

- Wait for / filter on `simulation_ended`, e.g. `grep -q '"simulation_ended"' <run>/<scenario>.jsonl`. Any launch-then-evaluate orchestration should gate on that event, not on a round count.
- `round_advanced` counts are fine only for *progress monitoring* (watching rounds climb), never for *completion*.

After a simulation completes, score the log with one or more **metrics**. Deterministic and LLM-as-judge metrics both live behind the same `Metric` abstraction, returning a `Measurement` (`score`, `score_unit`, `summary`, `per_round`, `per_agent`). Evaluation uses `--provider` to select the LLM judge for the LLM-driven metrics; deterministic metrics ignore it. The evaluate command reads the scenario configuration from the JSONL event log, so no scenario-specific flags (like `--knobs`) are needed.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate <scenario> \
  --run-dir ./runs/<scenario>/<timestamp> \
  --metrics <comma-separated metric names> \
  --model <model> --provider <provider> \
  > ./runs/<scenario>/<timestamp>/eval_stdout.log 2>&1 &
```

Each metric returns zero or more `Measurement` entries written into `<scenario>_report.json` under the `measurements` field. The shape:

- `metric_name` — the registered metric name (e.g. `perplexity`, `round_success`, `round_success_team_a`).
- `score` — overall scalar measurement (mean, fraction, count — meaning depends on the metric).
- `score_unit` — short free-form label describing what `score` represents.
- `summary` — one-line human-readable rollup.
- `per_round[]` — structured `RoundObservation` entries (`round_number`, `value`, `note`). Pure metrics like perplexity emit one per round with messages; flag-style metrics like `neologism` emit one per round where the phenomenon was observed.
- `per_agent[]` — structured `AgentObservation` entries; populated by metrics that have per-agent breakdowns (e.g. `content_filter_refusal`).

**Not-applicable metrics return `[]`.** When a metric detects it cannot apply to the current run (e.g. `protocol_probe_agent_pair_similarity` on a single-team run, `round_success_after_resume` on a non-resume run, `perplexity`/`mcr`/`mcm` on a scenario with no primary channel, the LLM-judge metrics on runs with no link messages, `protocol_learned_after_swap` on runs without a swap boundary, `communication_*` on runs with no link data), it returns an empty list and logs an INFO-level skip line. No zero-score sentinel Measurement is written. Existing entries from prior invocations are preserved via `merge_measurements` until the next invocation that produces a real Measurement for that metric_name replaces them. To forcibly drop stale not-applicable entries from a report, delete the report file before re-evaluating.

Metrics that DO emit a zero-score Measurement keep doing so when the count is a legitimate observation: `round_ended_idle`, `round_ended_timeout`, and `content_filter_refusal` all use `score = 0` to mean "this run had zero rounds/refusals with the trigger." (`postmortem_ended_timeout` is a hybrid: `score = 0` when postmortem ran but never timed out, but `[]` when the run had no postmortem phase at all.)

**`evaluation_cost` accumulates across invocations.** Each call to `glossogen evaluate` adds its provider usage onto the existing report's `evaluation_cost.usage` (via `merge_evaluation_costs` in [evaluation_report.py](src/glossogen/evaluation/reports/evaluation_report.py)) when the `(model, provider_name)` pair matches. Mismatched model/provider resets the cumulative cost to the new invocation's value (a mid-stream judge swap invalidates the running total). The `estimated_cost_usd` is recomputed each write from the summed usage. Implication: a re-run with no real LLM calls (e.g. a metric that errors before generating, or a not-applicable invocation) no longer clobbers prior cost data to zero.

Metrics no longer write `eval:` labels into `labels.json` — filter on `score` or on the `per_round` list directly.

Available metrics per scenario:

Generic metrics (available to all scenarios):

- `language_repetition` — how much each message redundantly re-encodes information on the primary channel under noise (repeated tokens like `Lf Lf 12 12`, digit+word dual-encoding like `12 twelve`, abbreviation+expansion like `gnt gentle`). **Per-message LLM judge**: for each round, that round's `#link` messages (pristine pre-noise text) are fed as an enumerated list and the judge returns one `repetition_factor` per message (≥1.0; 1.0 = each piece of info once, 2.0 ≈ twice, 3.0 ≈ thrice). Each round is judged **3 times** (`rounds × 3` calls/run) and per-message factors are averaged across replicas. Per-message factors are written to a `language_repetition_messages.jsonl` sidecar keyed by `message_id`. `score` = mean per-message factor across rounds (run mean); `per_round[].value` = that round's mean per-message factor. Within-message only (cross-message repetition is not counted). Not bit-reproducible (judge-derived), but per-message framing + 3-replica mean make it far more stable than round-level lumping.
- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style (NOT codes, slang, or new words). LLM judge; `score` = number of rounds with detected anomalies.
- `slang_emergence` — informal register shifts, existing-word repurposing (NOT codes or new words). LLM judge; `score` = number of rounds with detected slang.
- `neologism` — genuinely invented words with new meanings (NOT abbreviations or code mappings). LLM judge; `score` = number of rounds with detected neologisms.
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding (NOT new words or slang). LLM judge; `score` = number of rounds with detected codes.
- `perplexity` — mean per-token surprisal of primary-channel messages under `gpt2`, reported per round (deterministic, no LLM judge). `score` = overall mean nats; `per_round` carries per-round mean+std+message count. Skips scenarios with no primary channel.
- `mean_chars_per_round` — total characters of all primary-channel messages in a round, averaged across rounds (deterministic, no LLM judge). `score` = mean chars/round; `per_round` carries per-round total + message count. Skips scenarios with no primary channel. The headline throughput number — in Veyru this maps directly to `time_budget_seconds` (one char = one second).
- `mean_chars_per_message` — characters per primary-channel message, averaged across all messages (deterministic, no LLM judge). `score` = overall mean chars/message; `per_round` carries per-round mean+std+message count. Skips scenarios with no primary channel. Normalizes MCR by message count: rounds that need more back-and-forth no longer inflate the score, so MCM isolates per-message verbosity from message density.
- `round_ended_idle` — flags rounds whose main phase ended because all agents went idle on `read_notifications` (deterministic, no LLM). `score` = count of idle-ended rounds. Requires `round_ended` events in the log.
- `round_ended_timeout` — flags rounds whose main phase ended because the wall-clock duration limit was reached (deterministic, no LLM). `score` = count of timeout-ended rounds. Requires `round_ended` events in the log.
- `postmortem_ended_timeout` — flags rounds whose *postmortem* phase ended because the wall-clock duration limit was reached, rather than because all agents went idle (deterministic, no LLM). `score` = count of postmortem phases that hit the timeout; `per_round` lists the flagged rounds. Reads `PostmortemEnded` events (authoritative; includes the final round, whose postmortem end is otherwise unrecorded) and falls back to `RoundAdvanced(trigger="postmortem_timeout")` for runs predating that event — attributing each such advance to the round before it. **Returns `[]`** when the run had no postmortem phases (no `PostmortemStarted` events).
- `content_filter_refusal` — counts `ContentFilterError` refusals across the run (deterministic, no LLM). `score` = total refusal count; `per_round` lists rounds with at least one refusal; `per_agent` lists per-agent counts.
- `communication_open_coding` — pass 1 of the open-coding → ontology → relabel pipeline. One LLM call per run feeds the judge every primary-channel message plus the scenario-rendered per-round ground truth (via `SimulationScenario.build_communication_rounds`), and asks for free-form short labels naming communication-pattern features (multi-label per run, no pre-specified vocabulary). Writes `communication_open_coding.json` to the run dir with each label's evidence round and quote. `score` = number of free-form labels. Followed by `scripts/consolidate_communication_ontology.py` (one LLM call across N runs of one scenario, writing a versioned ontology under `runs/<scenario_name>/_ontology/<version>.json`) and then `communication_feature_presence` for relabel. **Returns `[]` (no Measurement)** when the scenario does not implement the `build_communication_rounds` hook.
- `communication_feature_presence` — pass 3 of the same pipeline. Accepts `--ontology-path PATH` to pin a specific ontology JSON; when omitted the metric auto-resolves the most recently modified ontology JSON under `runs/<scenario>/_ontology/`. One LLM call per run re-reads the same per-round transcript view against the ontology's categories and emits a 0–1 confidence per category. Writes `communication_feature_presence.json` (full feature-presence vector + ontology provenance). `score` = number of categories scoring ≥0.5. Passes 1 and 3 read the same `CommunicationRoundView` rows so confidences are commensurable with the open-coding labels. **Returns `[]` (no Measurement)** when the scenario does not implement the `build_communication_rounds` hook.
- `round_success` — generic; reads `RoundResultRecorded` events. Single-team scenarios emit one Measurement (`metric_name="round_success"`); multi-team scenarios emit one per `team_id` (`round_success_team_a`, etc.). `judge_round_result` is a required abstract method; **returns `[]`** only when a scenario's `judge_round_result` yields no verdicts.
- `round_success_after_resume` — generic; same accounting as `round_success` over the post-resume window. Reads `replace_manifest.json` / `cross_run_replace_manifest.json` and every `AgentSwappedMidRun` event; the comparison in `summary` is against the source run's same-window `round_success`. **Returns `[]`** on non-resume runs.
- `protocol_explanation` — generic; probes each agent post-simulation under its own original model (read from `AgentRegistered`), not the eval `--model`, with its full end-of-run reconstructed history, asking it to describe in free text the communication protocol it remembers. When the scenario implements `get_protocol_explanation_config()` the metric renders that scenario's per-role template; otherwise it uses a generic prompt, so it runs on any scenario where agents communicate. Writes one row per agent to `protocol_explanation_responses.jsonl` and per-model cost to `protocol_explanation_usage.json`; each answer is also stored in `per_agent[].note`. `score` = number of agents probed. **Returns `[]`** only when no agent has any reconstructable history.
- `protocol_learned_after_swap` — generic LLM judge; uses `detect_protocol_boundary_window` (default: first `AgentSwappedMidRun`) to find the pre/post split and `build_communication_rounds` to render transcripts. `score` = number of post-boundary rounds with observable newcomer protocol evidence. **Returns `[]`** when either hook opts out (no boundary, or scenario doesn't implement `build_communication_rounds`).
- `protocol_probe` — generic; probes each agent post-simulation against the scenario's fixed test bank, writing one row per (agent, question, replica) to `protocol_probe_responses.jsonl`. Each agent is probed under its own original model (read from `AgentRegistered`), not the eval `--model`. The scenario supplies the question bank, probe-prompt templates, and role-name mapping via `get_protocol_probe_config()`. Requires `--probe-replicas N` (≥1); optional `--probe-round R` is an **exclusive** cutoff — every tool call with `round_number >= R` is dropped, so the reconstructed history covers rounds `1..R-1` (inclusive). To capture state at the END of round R, pass `--probe-round=R+1`. Token usage + dollar cost go to `protocol_probe_usage.json`. `score` = total probe rows written. **Returns `[]`** when `get_protocol_probe_config()` returns `None`.
- `protocol_probe_replica_self_similarity` — generic; for each `(agent_id, question_id, cutoff_round)` group with ≥2 replicas, computes the upper-triangle mean of the replica × replica normalized-Levenshtein matrix on `response_text`. `score` = macro mean across groups; matrices persisted to `protocol_probe_replica_self_similarity.json`. Saturation at 1.0 is the expected signal for a converged protocol. **Returns `[]`** when `protocol_probe_responses.jsonl` is missing or no group has ≥2 replicas.
- `protocol_probe_agent_pair_similarity` — generic; agent × agent matrix per (question, cutoff). `score` = macro mean across groups; persisted to `protocol_probe_agent_pair_similarity.json`. Only meaningful in two-team / cross-team runs. **Returns `[]`** on single-team runs.
- `protocol_probe_cutoff_trajectory` — generic; for each `(agent_id, question_id)` pair where the JSONL contains rows from ≥2 distinct `cutoff_round` values, computes the mean cross-replica similarity between each adjacent cutoff snapshot. `score` = macro mean across all adjacent-cutoff pairs; persisted to `protocol_probe_cutoff_trajectory.json`. **Returns `[]`** when the JSONL has only one cutoff value.

Scenarios opt into most platform metrics by implementing the corresponding hooks on `SimulationScenario`. `judge_round_result` and `get_primary_channels` are **required** (abstract): every scenario must implement them, since round-success and primary-channel throughput/language metrics are core; the rest below are opt-in:

| Hook | Enables |
|---|---|
| `judge_round_result(round_number, trigger) -> list[RoundResult]` (required) | `round_success`, `round_success_after_resume` |
| `Metric.read_keyed_observations(run_dir)` (on the metric, not the scenario) | the analysis surface's `keyed` grain: charting a metric's per-category, per-question or per-message numbers across runs |
| `get_judge_models(knobs) -> tuple[ModelConsumer, ...]` | The launch check that refuses a run whose environment cannot reach the scenario's own judge. Defaults to the `judge_model` / `judge_provider` pair; override when the judge is conditional |
| `get_primary_channels() -> list[PrimaryChannel]` (required) | `perplexity`, `mean_chars_per_round`, `mean_chars_per_message`, language-emergence judges |
| `build_communication_rounds(events) -> list[CommunicationRoundView]` | `communication_open_coding`, `communication_feature_presence`, `protocol_learned_after_swap` |
| `detect_protocol_boundary_window(events, agent_configs) -> ProtocolBoundaryWindow \| None` | `protocol_learned_after_swap` (default returns first `AgentSwappedMidRun`; override to also detect scenario-specific boundaries like intern takeover / two-team observer swap) |
| `get_protocol_probe_config() -> ProtocolProbeConfig \| None` | `protocol_probe`, `protocol_probe_replica_self_similarity`, `protocol_probe_agent_pair_similarity`, `protocol_probe_cutoff_trajectory` |
| `get_protocol_explanation_config() -> ProtocolExplanationConfig \| None` | Tailors `protocol_explanation` with scenario per-role describe templates (optional; the metric runs with a generic prompt when this returns `None`) |
| `restore_state_from_events(events)` | Accurate "previous round" injection context after fork / resume / replace-agent |
| `get_replace_agent_blocked_tool_call_channels() -> frozenset[str]` | Strips scenario-private channel traffic (e.g. postmortem) from replaced agent's reconstructed history |

There are no scenario-specific metrics left. Every scoring concept (round-success, post-resume re-scoring, language emergence, protocol learning, protocol probing) is platform code that consumes scenario data through these hooks. Scenarios only ship their domain-specific events + the hooks that surface them.

## What `scripts/` is for

`scripts/` holds build tooling only:

- `export_openapi.py` — drives `make gen-api-types`; the `check-api-types` CI job depends on it
- `generate_demo_snapshot.py` — builds the frontend's `/demo` assets
- `measure_docs_style.py` — measures documentation pages against the bands in `docs/documentation-style.md`; part of the docs review, not a linter
- `docs_hooks.py` — mkdocs build hooks: adds the repository-root pages to the site and rewrites links that leave the docs tree into GitHub permalinks. Referenced from `mkdocs.yml`
- `consolidate_communication_ontology.py` — pass 2 of the communication pipeline, between the `communication_open_coding` and `communication_feature_presence` metrics

Keep it that way. One-off experiment orchestration, cohort reruns, and label
surgery do not belong here. They operate on run output, and the evaluation
reports (`{scenario}_report.json`) plus the JSONL event logs are a stable enough
interface that such tooling can live wherever the experiment does.

Scenario-local helper scripts are the exception and live under
`src/glossogen/scenarios/<name>/scripts/`.

## Destructive Actions

**Always ask the user before deleting or stopping anything.** This includes:
- Deleting run directories, log files, or any simulation output
- Killing running processes (simulations, servers, etc.)
- Removing files, branches, or data of any kind

Never assume cleanup is wanted. Ask first, act second.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
1b. If you touched a scenario, run `VIRTUAL_ENV= uv run --no-sync python -m glossogen validate <name>`. It builds every preset and checks the contract without launching anything. It also takes a directory, for a scenario package that is not installed.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
3. If vulture reports new false positives, regenerate the whitelist over the same paths `make lint-server` checks, or the regenerated file drops the entries covering the ones it left out: `VIRTUAL_ENV= uv run --no-sync vulture src/ scripts/ linter/ --min-confidence 60 --make-whitelist > vulture_whitelist.py`
