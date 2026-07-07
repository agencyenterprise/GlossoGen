# GlossoGen

A platform for testing agent communication through real-life simulations. Agents decide when to speak; a game clock manages round progression and injects scenario events. All interactions are logged for post-hoc evaluation. A web UI displays simulation runs and evaluation results.

![Platform overview](images/platform_overview.webp)

## Setup

### Prerequisites

- **Python 3.12**
- **Node.js ≥ 22** (for the frontend)
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **make**, **git**
- **Postgres ≥ 14** — *optional for local dev.* Leave `DATABASE_URL` unset to run in zero-setup no-database local mode (the runs index is derived from the filesystem and OAuth state is held in memory). Postgres is required only for Clerk multi-tenant auth / production. On macOS: `brew install postgresql@16 && brew services start postgresql@16`. On Debian/Ubuntu: `apt-get install postgresql`.
- **System libraries for weasyprint** (PDF export). On macOS: `brew install pango cairo gdk-pixbuf libffi`. On Debian/Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0`.
- **Docker + Docker Compose** — *optional.* Only needed to run the local [Langfuse observability](#observability-langfuse) stack (`make langfuse-up`).

### Install dependencies

```bash
make install            # both backend and frontend
make install-server     # backend only (uv sync)
make install-frontend   # frontend only (npm ci)
```

### Local Postgres (optional)

By default the backend runs in **no-database local mode** — leave `DATABASE_URL` unset and skip this entire section. The runs index is derived from the `runs/` directory on disk and MCP OAuth tokens are held in memory (they reset on restart, which just means re-authenticating the MCP client).

Set up Postgres only if you want the Postgres-backed runs index locally, or to run Clerk multi-tenant auth. Create a role, a local database owned by that role, and point the backend at it via `DATABASE_URL`.

```bash
# 1. Create a Postgres role (one-time). On macOS/Homebrew a superuser role
#    named after your OS user already exists, so you can skip this and connect
#    without credentials. On Debian/Ubuntu (peer auth), create a role first:
sudo -u postgres createuser --createdb --pwprompt glossogen   # prompts for a password

# 2. Create the database owned by that role (one-time).
createdb -O glossogen glossogen_dev
# Homebrew default-role shortcut (role == your OS user, no password): createdb glossogen_dev

# 3. Apply the migrations (creates groups, runs, user_last_active_group,
#    schema_migrations, and the OAuth tables).
DATABASE_URL=postgresql://glossogen:<password>@localhost:5432/glossogen_dev \
  VIRTUAL_ENV= uv run --no-sync alembic upgrade head

# 4. Verify the schema.
psql -d glossogen_dev -c "\dt"
```

The `DATABASE_URL` format is `postgresql://<user>:<password>@<host>:<port>/<db>`. On a Homebrew install where the role matches your OS user and local connections use `trust`/`peer` auth, you can drop the credentials entirely: `postgresql://localhost:5432/glossogen_dev`.

The first time the backend boots it will also auto-create the synthetic `local` group used in single-tenant local mode. There's nothing else to do — leave `CLERK_SECRET_KEY` unset and every request runs as `local-user` inside the `local` group.

To reset the database, drop and recreate it: `dropdb glossogen_dev && createdb -O glossogen glossogen_dev && alembic upgrade head`.

### Configure environment

```bash
cp .env.example .env
```

See `.env.example` for all available variables (API keys, authentication, CORS). At minimum, set `ANTHROPIC_API_KEY`. Leave `DATABASE_URL` unset for no-database local mode, or set it to the Postgres database you created above (including the role's credentials if you set a password) to use the Postgres-backed runs index.

`.env.example` also pre-fills `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` for local [Langfuse observability](#observability-langfuse). Copying it as-is enables tracing once you run `make langfuse-up`; if the stack isn't running, simulations just log one warning and proceed untraced. Blank both keys to disable telemetry entirely.

## Running a Simulation

The CLI auto-generates a timestamped subdirectory under `--runs-dir`. Each round, agents communicate freely until all are idle or the round duration expires.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/veyru/knobs_default.json \
  > ./runs/veyru_stdout.log 2>&1 &
```

Flags:
- `--provider` — LLM provider: `anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted` (required). The `self-hosted` value targets any OpenAI-compatible chat-completions endpoint via `SELF_HOSTED_BASE_URLS` (a JSON map of model name → `/v1` URL) plus `SELF_HOSTED_API_KEY` — see [modal/README.md](modal/README.md) for reference Modal deployments (Llama 3.3 70B, Qwen3-32B).
- `--max-agent-turns` — Maximum agentic turns per agent (default: 200)
- `--resume` — Resume from an existing run directory after a crash

Check progress by reading the stdout log or the JSONL event log in the run directory.

### Resuming a Failed Simulation

If a simulation crashes or is killed, resume using the `--resume` flag pointing at the existing run directory.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --resume ./runs/<scenario>/<timestamp> \
  --config <original-config.json> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The simulation picks up from where it left off, preserving channel messages and scenario state. The `--resume` flag requires the same `--config` as the original run.

### Replacing an Agent (Round-Level Rewind)

Replay a finished run from the start of a chosen round with one specific agent restarted on a fresh history while every other agent keeps its full reconstructed history. Useful for asking "could a fresh agent follow the engineer from here on?" — a direct, empirical alternative to a judge.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
  --source-run-dir ./runs/veyru/<timestamp> \
  --round-start 5 \
  --replaced-agent-id field_observer \
  --model claude-sonnet-4-6 --provider anthropic \
  --runs-dir ./runs \
  [--rounds-after-swap N]
```

`--rounds-after-swap` defaults to `source_round_count - round_start` (the remaining rounds in the original run after the replacement boundary). The resumed simulation's `round_count` is set to `round_start + rounds_after_swap`.

Internals: clones the source run's git repo at the commit produced by the source's `RoundAdvanced` event for `--round-start`, so round N-1 is fully ended in the cloned JSONL but round N's injections have not yet been delivered. On resume the game clock starts at round N and delivers fresh round-N injections to all agents. The replaced agent's reconstructed pydantic-ai history has `text` / `thinking` parts stripped and any tool calls targeting blocked channels (e.g. veyru's postmortem channels) removed; its full event log is preserved on disk. The veyru world's per-team `outcomes` list is seeded from the source's events on resume so the round-N injection's "PREVIOUS VEYRU RESULT" block reflects the source's actual round N-1 outcome. The replaced agent's model/provider can differ from the original; non-replaced agents stay on their exact original models. Cannot be used with `--round-start 1`.

The CLI returns immediately after preparing the new run directory and spawning a detached simulation subprocess; check progress via `tail ./runs/veyru/<new_timestamp>/veyru_stdout.log` or the JSONL event log. For multi-run sweeps (e.g. several `--round-start` / `--rounds-after-swap` combinations), see the parallel orchestrator pattern in [CLAUDE.md](CLAUDE.md#parallel-replace-agent-orchestration).

**Per-channel history visibility for the replaced agent.** Pass `--visible-history-channel CHANNEL` (repeatable) to control which channels keep their prior message history visible to the replaced agent. When omitted, the CLI reads the `replace_agent_default_channel_visibility` knob from the source run's `scenario_config` (a `dict[str, bool]` defined on `BaseKnobs`; channels not in the map default to visible) and combines it with the agent's actual channel memberships. Channels marked invisible (or not in `--visible-history-channel`) have the replaced agent's `member_join_index` bumped to the current message count, so its `read_channel` calls only see post-resumption messages there.

**Per-scenario knob overrides on resume.** The `--knobs` flag accepts a JSON file whose entries are merged onto the source's `scenario_config` before validation. Veyru exposes `postmortem_disabled_at_start: bool` for this flow: setting it to `true` flips `world.disable_postmortem_globally()` at world construction, dropping the postmortem channel for the rest of the resumed simulation (no postmortem injections, no postmortem phase, sends to postmortem are rejected).

Derived runs appear in the run list with a "Replaced" badge linking to the source.

## Cross-Run Replacing an Agent (Round-Level Rewind, Different Source for the Imported Agent)

`glossogen cross-run-replace-agent` is a sibling of `replace-agent` that imports an agent from a *different* completed run (Sim B) into a target run (Sim A) at a chosen round boundary. Same scenario and same `agent_id` only. The imported agent retains its **full** pydantic-ai history (text + thinking + tool calls) from Sim B; non-replaced agents in Sim A continue with their full Sim A history. Useful for asking "how does an agent that learned its protocol with one team perform when dropped into another team that learned a different protocol?".

```bash
glossogen cross-run-replace-agent veyru \
  --source-a-run-dir ./runs/veyru/<sim_a_timestamp> \
  --source-b-run-dir ./runs/veyru/<sim_b_timestamp> \
  --replaced-agent-id field_observer \
  --round-start 15 \
  --runs-dir ./runs \
  [--source-b-round-end N] \
  [--model M --provider P] \
  [--knobs path/to/overrides.json] \
  [--rounds-after-swap K] \
  [--visible-history-channel CHANNEL ...]
```

Defaults: `--source-b-round-end` is `min(round_start - 1, B_max_round)` (largest temporally-aligned slice of B that doesn't exceed what B reached); `--model` / `--provider` default to whatever the imported agent ran under in Sim B (read from B's `AgentRegistered`). Both must be passed together to override.

Internals: clones Sim A at the round-start commit (same as replace-agent), copies Sim B's full JSONL into the new run dir as `imported_history_source.jsonl`, writes `cross_run_replace_manifest.json` with both source IDs + the imported model/provider, and launches the resumed simulation. On resume, the CLI detects `cross_run_replace_manifest.json` and feeds Sim B's events to a single agent's history reconstruction via an `ImportedHistory` redirect on `AgentHistoryFilter`; every other agent reads from Sim A's events. Channel-blocking on the imported history strips the scenario's default blocked channels (e.g. veyru's postmortem) plus any channel the imported agent had in Sim B but is missing in Sim A.

For veyru cross-team experiments, set `--knobs` with `{"postmortem_disabled_at_start": true}` to drop the postmortem channel after the swap. Without it, the two agents have a backchannel in postmortem that quickly re-aligns their protocols, washing out the cross-team-confusion signal. Cross-run runs appear in the run list with a violet "Cross-run" badge that links back to both Source A and Source B.

The same `round_success_after_resume` metric works for both replace-agent and cross-run flows; for cross-run runs the comparison is against Sim A over the same window.

## Resume at a Round (Post-Hoc, No Agent Replacement)

`glossogen resume-at-round` clones a finished run at the start of a chosen round and continues execution without restarting any agent. Every agent keeps its full reconstructed history; the resumed simulation differs from the source only through merged knob overrides. Useful for post-hoc multi-swap studies (inject new `scheduled_events`), toggling `postmortem_enabled` mid-experiment, extending `round_count` past where the source stopped, or just replaying a finished run with a different configuration.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen resume-at-round veyru \
  --source-run-dir ./runs/veyru/<source_timestamp> \
  --round-start 16 \
  --runs-dir ./runs \
  [--knobs path/to/overrides.json] \
  [--rounds-after-resume K]
```

`--rounds-after-resume` defaults to `source_round_count - round_start` (the remaining rounds in the original after the boundary). The resumed simulation's `round_count` is set to `round_start + rounds_after_resume`.

Internals: the flow reuses the `replace-agent` machinery with `replaced_agent_id=None`. Clones the source's git repo at the `RoundAdvanced(round_start)` commit, pins every agent to its source-active model via `model_overrides` (so resuming a multi-swap source picks up each agent's per-phase model), writes `replace_manifest.json` with `replaced_agent_id` / `replacement_model` / `replacement_provider` all `null`, and launches `glossogen run --resume`. The game clock's resume branch defers `deliver_round_injections` until after agent runners are launched and the boundary hook fires, so `scheduled_events` bucketed at `round_start` execute against a fully-wired runtime and the resulting round-start injection lands in the post-swap session.

`--knobs` accepts a JSON file shallow-merged onto the source's `scenario_config`. Use it to flip `postmortem_enabled`, append new `scheduled_events` for post-hoc multi-swap studies, extend `round_count` beyond what the source ran, or override `model_overrides`. When the scenario's knobs schema gained a required field after the source was created, pass that field via `--knobs` so validation passes (example: veyru's `easy_round_numbers` was added later — older runs need `--knobs '{"easy_round_numbers": [1, 2, 3, 6, 13]}'`).

Inherited `scheduled_events` semantics: events at `at_round < round_start` are silently skipped (the resumed clock never visits those rounds). Events at `at_round == round_start` fire on resume — by design — because the cloned JSONL is captured before the source dispatched that boundary's scheduler events. Boundaries that already fired in the source (or in a crashed-and-resumed run) are pre-seeded into the scheduler's `_fired_rounds` set so they are not re-dispatched.

Runs created this way appear with a green "↺ Resumed @ round N" badge linking back to the source. Multi-swap runs (whether direct via `scheduled_events` or inherited via resume) render one floating action button per swap so users can scroll directly to any boundary.

## In-Run Agent Swaps via `scheduled_events`

The in-run scheduler swaps agents at scheduled round boundaries inside a single live simulation. Multiple swaps fire across the same run on one continuous timeline; a run with three swaps produces four phases (A → B → C → D) on the same timeline.

Configure via the `scheduled_events` knob in the scenario config. Two event types:

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

`channel_visibility` is a per-channel discriminated union: `{"kind":"full"}` keeps all predecessor history visible; `{"kind":"none"}` hides the channel entirely; `{"kind":"from_round","round_floor":R}` windows the channel to round `R` onward. Channels not listed default to `Full`. Globally disabled channels (e.g. veyru's postmortem after `set_postmortem`) are forced to `none` by the runtime regardless of the swap config.

Each swap emits an `AgentSwappedMidRun` event into the JSONL, writes a `resume_context_<agent_id>_round_<R>.json` file capturing the swapped-in agent's seed history, and invokes `ScenarioWorld.on_agent_swapped_mid_run` so the scenario can suppress prior-round injection content for the swapped-in agent's first turn. The frontend renders one tab per `(agent_id, generation)` and a dashed indigo divider in the chat pane between adjacent rounds that straddle a swap. The `round_success_after_resume` metric emits one Measurement per swap (named `round_success_after_resume_round_<R>_<agent_id>`) with the previous phase as the baseline. The Streamlit Multi-swap tab visualises per-phase round-success with Δ pp annotations between phases.

## Observability (Langfuse)

Simulation agents are instrumented with [pydantic-ai](https://ai.pydantic.dev/)'s OpenTelemetry support, exporting every LLM call (prompts, completions, tool calls, token usage, latency, cost) to a **local, self-hosted [Langfuse](https://langfuse.com/)** — never a cloud endpoint.

```bash
make langfuse-up      # start the local stack (web, worker, postgres, clickhouse, redis, minio)
make langfuse-down    # stop it
make langfuse-logs    # tail langfuse-web
```

- UI at **http://localhost:3001** (3001 because the frontend dev server owns 3000). First boot takes ~2-3 min while migrations run. Log in with `local@glossogen.dev` / `local-dev-password`.
- The `glossogen` org/project and the API keys (`pk-lf-local-dev` / `sk-lf-local-dev`) are seeded headlessly on first boot via `LANGFUSE_INIT_*` in [docker-compose.langfuse.yml](docker-compose.langfuse.yml). Those keys are pre-filled in `.env.example`, so `glossogen run` traces to this instance out of the box. Langfuse's internal Postgres is mapped to host port 5433 to avoid clashing with a local 5432 Postgres.
- Each run is one Langfuse **session** keyed by `run_id`; every agent's cycles trace under it, tagged with `agent_id` / `role_name` / `model` / `provider` / `scenario`. Each generation also carries `round_number` in its metadata, so observations are filterable by simulation round.
- Telemetry is enabled only when both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, and only in the `glossogen run` path — `glossogen evaluate`'s probe/judge LLM calls are not traced. If the stack is down or keys are unset, the run logs one warning and proceeds untraced; telemetry never blocks a simulation. Docker Desktop needs adequate resources for the full stack (Langfuse suggests ~4 cores / 16 GiB).

## Run Output Directory Structure

All simulation outputs use a standard directory layout under `runs/`:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl              # Event log
├── {scenario_name}_debug.jsonl        # Debug log (JSON lines, visible in FE Logs tab)
├── {scenario_name}_report.json        # Evaluation report (written by evaluate)
├── fork_manifest.json                 # (forked runs only) provenance tracking
├── replace_manifest.json              # (replace-agent runs only) provenance tracking
├── cross_run_replace_manifest.json    # (cross-run replace-agent runs only) source A/B + imported model
├── imported_history_source.jsonl      # (cross-run replace-agent runs only) verbatim copy of Sim B's JSONL
├── resume_context_{agent_id}.json     # per-agent reconstructed pydantic-ai message history at resume time
├── resume_context_{agent_id}_round_{R}.json  # (in-run scheduled swap) one file per AgentSwappedMidRun event
├── protocol_probe_responses.jsonl     # (veyru only) one row per (agent, question, replica) when protocol_probe is run
├── protocol_probe_replica_self_similarity.json  # (veyru only) within-run replica × replica similarity matrices
├── protocol_probe_agent_pair_similarity.json    # (veyru only) within-run agent × agent similarity matrices (two-team)
├── protocol_probe_cutoff_trajectory.json        # (veyru only) per (agent, question) adjacent-cutoff series
└── multi_swap_cache.json              # streamlit Multi-swap tab cache (per-phase round_success)
```

## Running Evaluation

After a simulation completes, point `--run-dir` at the specific run directory. Evaluation uses `--provider` to select the LLM judge.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate veyru \
  --run-dir ./runs/veyru/1742234567 \
  --metrics language_strangeness,shorthand_codes \
  --model claude-sonnet-4-6 --provider anthropic
```

Generic metrics (available to every scenario, opt-in via the per-scenario hooks listed below). Both deterministic and LLM-driven metrics return `Measurement` entries with `score`, `score_unit`, `summary`, structured `per_round`, and optional `per_agent` breakdowns:

Communication-style LLM judges (each scoped to one phenomenon so they don't overlap):
- `language_repetition` — per-message redundant re-encoding on the primary channel (repeated tokens, digit+word dual-encoding, abbreviation+expansion). For each round, the round's pristine `#link` messages are judged as an enumerated list and the judge returns one redundancy factor per message (≥1.0); `rounds × 3` calls, averaged per message, written to a `language_repetition_messages.jsonl` sidecar. The run score is the mean per-message factor
- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style
- `slang_emergence` — informal register shifts, colloquial expressions, casual nicknames
- `neologism` — genuinely invented words with new meanings
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding

Deterministic metrics (no LLM):
- `round_ended_idle` / `round_ended_timeout` — count rounds whose main phase ended via the `all_agents_idle` or `round_timeout` trigger
- `content_filter_refusal` — counts LLM content-filter refusals with per-agent breakdown
- `perplexity` — mean per-token surprisal (in nats) of primary-channel messages under a fixed `gpt2` language model
- `mean_chars_per_round` — mean total characters per round on the primary channel; the headline channel-utilization number that maps directly to Veyru's `time_budget_seconds`
- `mean_chars_per_message` — mean characters per primary-channel message; normalizes MCR by message count so rounds with more back-and-forth no longer inflate the score

Round-success and post-swap metrics (powered by `judge_round_result` + manifests):
- `round_success` — fraction of rounds judged a success by `judge_round_result`; one Measurement per `team_id` for multi-team scenarios
- `round_success_after_resume` — same accounting restricted to the post-swap window of replace-agent / cross-run / in-run-swap runs, with a baseline comparison in `summary`

Protocol metrics (powered by `build_communication_rounds`, `detect_protocol_boundary_window`, `get_protocol_probe_config`):
- `protocol_learned_after_swap` — LLM judge: did the newcomer adopt the pre-existing protocol after a personnel change?
- `protocol_probe` — probes each agent under its original model on a fixed scenario question bank; writes `protocol_probe_responses.jsonl`; requires `--probe-replicas N`, optional `--probe-round R`
- `protocol_probe_replica_self_similarity` / `protocol_probe_agent_pair_similarity` / `protocol_probe_cutoff_trajectory` — Levenshtein-based similarity over the probe responses; each writes its own matrix artifact for the streamlit "Probe similarity" tab
- `communication_open_coding` / `communication_feature_presence` — the open-coding → ontology → relabel pipeline (see below)

Scenarios opt in by implementing the corresponding hook on `SimulationScenario`; a scenario without the hook returns `[]` for that metric and the measurement is simply absent from the report. Both Veyru and Salon currently implement every hook except `get_protocol_probe_config` (Salon does not yet ship a probe bank).

Output is a JSON report under the `measurements` field; metrics no longer write `eval:*` labels to `labels.json`. Filter on `score` or on the `per_round` / `per_agent` lists directly.

### Auditing LLM-judge calls

LLM-judge metrics emit their full system prompt, user prompt, and structured output via stdlib `logger.debug`. Set `LOG_LEVEL=DEBUG` in the environment and pipe stderr to a file to capture the exact text the judge saw and returned. The capture is the source of truth for "did the metric get all the data it needed and nothing else" — review it whenever a metric's output looks surprising.

```bash
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate veyru \
  --run-dir ./runs/veyru/1742234567 \
  --metrics communication_open_coding \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2> /tmp/veyru_eval_debug.log
```

The debug log records contain the verbatim Jinja-rendered prompt blocks (per-round transcripts, ground-truth blocks) plus the judge's raw structured output as JSON. The `LOG_LEVEL` env var is honoured by `glossogen evaluate` and by `scripts/consolidate_communication_ontology.py` (see below). Without it the harness defaults to `INFO`. Both are dotenv-friendly — set them in `.env` for a persistent default or inline as shown above.

If the judge's structured output truncates (you'll see a `Field required ... input_value={}` validation warning followed by a metric failure), bump the per-call output-token cap by setting `LLM_MAX_TOKENS=32768` (or higher) in `.env` or inline. The default of `16384` covers the verbose communication-feature outputs but pathological runs with many labels × many evidence citations can still exceed it.

### Communication-feature analysis (open coding → ontology → relabel)

A two-phase LLM-judge pipeline that surfaces and scores emergent communication-pattern features on the primary channel without committing to a pre-specified vocabulary. Scenario-agnostic: any scenario that implements `SimulationScenario.build_communication_rounds(events)` participates. Three steps:

```bash
# 1. Open-coding pass: per run, one LLM call. Writes
#    runs/<scenario>/<id>/communication_open_coding.json with free-form labels +
#    multi-round evidence citations.
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate <scenario> \
  --run-dir ./runs/<scenario>/<id> \
  --metrics communication_open_coding \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2>> /tmp/communication_eval_debug.log

# 2. Consolidation: one LLM call across N runs of one scenario. Produces a
#    versioned taxonomy under runs/<scenario>/_ontology/.
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python scripts/consolidate_communication_ontology.py \
  --scenario-name <scenario> \
  --run-id <scenario>/<id1> --run-id <scenario>/<id2> --run-id <scenario>/<id3> \
  --runs-dir ./runs \
  --version <version> \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2>> /tmp/communication_consolidate_debug.log

# 3. Relabel pass: per run, one LLM call against the ontology. Writes
#    runs/<scenario>/<id>/communication_feature_presence.json with a 0-1
#    confidence per ontology category.
LOG_LEVEL=DEBUG VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate <scenario> \
  --run-dir ./runs/<scenario>/<id> \
  --metrics communication_feature_presence \
  --ontology-path runs/<scenario>/_ontology/<version>.json \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  2>> /tmp/communication_eval_debug.log
```

Always run with `LOG_LEVEL=DEBUG` and a stderr redirect during development so the prompt and the structured judge output land in an auditable file. Both passes use the same per-round view (primary-channel messages + the scenario-rendered per-agent ground truth) so the open-coding labels and feature-presence confidences are commensurable.

Consolidated ontology JSONs live under `runs/<scenario_name>/_ontology/` so they ship with any export of the runs tree. The entire `runs/` directory is gitignored — the ontology JSONs are regenerable from the open-coding sidecars; pass them around alongside the runs they were derived from rather than committing them.

## Results Viewer (Streamlit)

A Streamlit app at [analysis/results_viewer/](analysis/results_viewer/) overlays per-round metric hits across multiple evaluated runs — useful for comparing models or knob configurations. Tabs include Timeline, Baseline, Verbosity, Resume, Cross-swap, Multi-swap, OSS vs Frontier, and Probe similarity (Levenshtein-based comparisons across the per-run probe artifacts, with a multi-select run picker driving every sub-view).

```bash
uv sync --group analysis    # one-time, installs streamlit + plotly
make results-viewer         # opens the viewer in a browser
```

It reads from `GLOSSOGEN_RUNS_DIR` (defaults to `./runs`) and lists all runs that have a `{scenario}_report.json`.

## Web UI

A FastAPI backend + Next.js frontend for browsing simulation runs. The frontend streams events in real time via SSE for in-progress runs.

### Authentication

The backend uses **Clerk** for multi-tenant authentication. Each Clerk organization corresponds to a study group; every run is owned by exactly one group and never shared across groups except via the export/import flow.

* **Local mode (default for dev clones):** leave `CLERK_SECRET_KEY` unset on the backend and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` unset on the frontend. The backend's identity middleware short-circuits every request to a synthetic `local` group / `local-user`; the frontend renders without a sign-in flow. With `DATABASE_URL` also unset, the backend runs with no database at all — the runs index comes from the filesystem and OAuth state is in memory. (Setting `DATABASE_URL` keeps local mode but stores the `local` group + `runs` index in Postgres.)
* **Clerk mode (prod / hosted):** set Clerk env vars on both sides plus `CLERK_WEBHOOK_SECRET` so the backend can keep its local `groups` table in sync with Clerk org create/update/delete events. The frontend mounts `<ClerkProvider>` and Clerk's middleware redirects unauthenticated traffic to `/sign-in`. API requests carry the Clerk session token as the Bearer header; the backend reads the active group from the URL slug (`/api/g/{slug}/...`) and validates membership against the JWT.

The active group is identified by the URL slug — `/g/team-a/runs/...` on the frontend hits `/api/g/team-a/runs/...` on the backend. The identity middleware accepts the request only if the user's Clerk session has `team-a` as the active org.

#### Multi-org users — Clerk `organizationSyncOptions`

The frontend `middleware.ts` wires Clerk's `organizationSyncOptions.organizationPatterns` to `["/g/:slug", "/g/:slug/(.*)"]`. Clerk's middleware reads the slug from the URL and activates that org on the session for the current request *before* the page renders or the API client mints a token. A user who belongs to multiple orgs can therefore navigate to any of them by URL without first clicking the org switcher.

If the user is not a member of the URL's org, Clerk leaves the previously active org in place; the backend then sees `claims.org_slug != url_slug` and returns 403.

**Tab caveat.** Clerk's session cookie is a singleton per browser, so only one tab's active org is reflected in the cookie at a time. Each tab still activates its own org server-side on navigation (so initial page loads and Server-Component fetches are correct), and the API client uses `getToken()` per request (not the cookie), so foreground tab requests get a token aligned to that tab's URL. Background fetches (cron, service workers) that don't pass through the focused tab can race — there are none in glossogen today.

The MCP endpoint at `/mcp` uses OAuth 2.0 with PKCE (see MCP Integration below). MCP tokens are bound to a specific group at consent time — in local mode the synthetic `local` group, in Clerk mode the user's active org picked on the consent page — so every tool call is automatically scoped.

### Starting the Servers

The backend and frontend run as separate processes — start each in its own terminal:

```bash
make dev            # terminal 1: FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # terminal 2: Next.js dev server on port 3000
```

Open <http://localhost:3000> once both are running.

The frontend displays a list of all simulation runs with scenario name, timestamp, message count, status (including in-progress runs), evaluation status, and lineage badges (fork, replace-agent, cross-run, resume-at-round). Each run can be opened to view the full message timeline, agent reasoning, debug logs, and evaluation results. Simulations are launched from the CLI (see "Running a Simulation" above) or via the MCP `start_run` tool.

### Live Token Streaming

Every `glossogen run` starts an embedded streaming server on an ephemeral port and writes a `stream.json` discovery file to the run directory. When `glossogen serve` detects a live simulation (via `stream.json`), it proxies the simulation's SSE stream — including token-by-token text deltas from the LLM streaming API — to connected frontends. The frontend shows text appearing character-by-character as agents generate responses. When the simulation ends, `stream.json` is deleted and the server falls back to JSONL tailing.

### API Type Safety

All frontend API calls use a typed client generated from the backend's OpenAPI schema. Raw `fetch()` is forbidden (enforced by ESLint). To regenerate types after changing backend endpoints:

```bash
make gen-api-types
```

### MCP Integration

The backend exposes an MCP (Model Context Protocol) server at `/mcp` for programmatic access to simulation data from LLM clients like Claude Code or Cursor. The MCP endpoint uses OAuth 2.0 with PKCE and dynamic client registration — clients handle authentication automatically.

**Requires `OAUTH_ISSUER_URL`** to be set to the public backend URL (e.g. `http://localhost:8000`). The MCP endpoint is disabled if this variable is unset.

Click the **MCP** button on the runs page for connection instructions, or configure manually:

```bash
claude mcp add-json glossogen-runs '{"type":"http","url":"http://localhost:8000/mcp"}'
```

No auth headers needed — the client discovers OAuth metadata and handles registration, authorization, and token refresh automatically. In local mode the consent step auto-approves to the synthetic `local` group; in Clerk mode the backend parks the authorization request and redirects the browser to the frontend at `/mcp-consent?request_id=...`, where Clerk forces sign-in and the user picks which organization to authorize. The frontend POSTs back to `/mcp/consent/approve` with a fresh Clerk JWT; the backend resolves the active org to a group, mints the authorization code bound to that `group_id`, and redirects the browser to the OAuth client's callback. Every subsequent MCP tool call is automatically scoped to the chosen group.

Available tools:
- `list_scenarios`
- `list_runs` (paginated, filterable)
- `get_run_metadata` (agents, configuration, evaluation summary, lineage provenance)
- `list_derived_runs` (replace-agent / resume-at-round / cross-run children with round boundaries and scores)
- `get_run` (messages, reasoning, tool use)
- `get_knobs_schema` (JSON Schema for scenario knobs + available preset files)
- `get_knobs_preset` (load a preset knobs file)
- `start_run` (launch a simulation with model/provider/knobs)
- `export_run_artifacts` (download URL for a zip of the run's artifacts)
- `export_agent_thread` (one agent's reconstructed thread as a drop-in Anthropic/OpenAI request body, with an optional round cutoff)

Typical MCP run-start workflow:
1. `get_knobs_schema` to inspect available fields and preset names.
2. `get_knobs_preset` to load a baseline config.
3. `start_run` with the selected model/provider and final knobs payload.

### Pushing local runs to a remote glossogen server

The same OAuth flow that issues MCP tokens also gives the CLI a way to push local run bundles to a deployed (Clerk-protected) backend. The CLI calls the remote's existing `/api/g/{slug}/runs/import` REST endpoint — there's no separate prod-upload server-side feature.

```bash
# 1. One-time: sign in to the deployed backend. Opens your browser to the
#    Clerk-gated consent page; pick your org, approve, the CLI's loopback
#    server collects the code and writes ~/.glossogen/credentials.json (0600).
glossogen login --url https://schmidtsciencesapi.up.railway.app

# 2. Diff local runs against prod and upload anything missing. Filters by
#    label (AND) and by report-present (so crashed runs are skipped). The
#    remote import endpoint is idempotent on run_id, so re-running is safe.
glossogen push-to-prod --label baseline --runs-dir ./runs
```

Useful flags:
- `--scenario <name>` (repeatable) restricts to specific scenarios.
- `--label <label>` (repeatable, AND) requires the run's `labels.json` to contain every listed label.
- `--include-incomplete` allows pushing runs that don't have a `<scenario>_report.json` yet.
- `--dry-run` prints the diff without sending bytes.
- `--concurrency N` (default 1, capped at 4) parallelizes uploads. Keep this small — each upload holds the bundle bytes in memory, and the export side iterates the run directory.

For runs that **already exist on prod** but whose local labels or evaluation report have been edited (re-evaluated, manually retagged, etc.), use the companion command:

```bash
# For every local-evaluated run that's already on prod: PUT the local
# labels (when they differ from the remote's) and PUT the local
# evaluation report (unconditionally — local is the source of truth).
# Use this when you only need to push metadata edits without
# re-uploading bundles.
glossogen sync-metadata-to-prod --runs-dir ./runs
```

Useful flags:
- `--scenario <name>` (repeatable) restricts to specific scenarios.
- `--dry-run` prints which runs would be touched (and whether they have label drift) without sending PUTs.
- `--concurrency N` (default 4, capped at 8) parallelizes the PUTs. Higher than `push-to-prod` because the bodies are just the label list / report JSON, not a tarball.

The middleware accepts the MCP OAuth Bearer for both `/mcp/*` tool calls and `/api/g/{slug}/...` REST calls, so the same token works for browsing in Claude Code, pushing bundles, and syncing labels from the CLI.

## Scenarios

### Veyru

Two agents (Field Observer, Stabilization Engineer) stabilize failing Veyru entities — fictional box-shaped entities with internal wave-patterns — across a series of budget-constrained rounds. Every character sent on the comm link costs one simulated second against a fixed per-round time budget; a Veyru collapses when total communication time exceeds that budget. Selected early/mid rounds (1, 2, 3, 6, 13) are forced to a single priority-≤2 motif so pressure ramps up gradually over the run. The position of reference star SAGWE392 remaps the symptom→treatment mapping each round and varies physical parameters (hold duration, starting face, pressure level), forcing per-round communication even if agents develop shorthand. See the [scenario README](src/glossogen/scenarios/veyru/README.md).

![Veyru scenario overview](images/veyru_overview.webp)

### Warehouse Robot Recovery

Three agents (Floor Associate, Robotics Engineer, Fleet Safety Coordinator) coordinate over a shared radio channel to recover stopped warehouse robots. Per-character communication budget; recovery procedures rotate per round with random wait times, intensities, and surfaces drawn from rotating parameter pools. See the [scenario README](src/glossogen/scenarios/warehouse_robot_recovery/README.md).

### Satellite Contact Window

Three agents (Telemetry Operator, Subsystem Engineer, Flight Director) submit ordered command sequences during a limited satellite contact window. Per-character budget on the comm link; the operator submits the sequence in a single judged call against the engineer's resolver and the flight director's authorization envelope. See the [scenario README](src/glossogen/scenarios/satellite_contact_window/README.md).

### Container Yard Stacking

Three agents (Yard Operator, Logistics Planner, Crane Operator) place one incoming container per round into its correct stack slot. Per-round changing yard map prevents postmortem memorization: the planner alone sees the active crane stations and stack layout, the yard operator alone sees the incoming container's manifest, the crane operator executes one physical move per `crane_move` call. See the [scenario README](src/glossogen/scenarios/container_yard_stacking/README.md).

### Adding a New Scenario

See [docs/creating-a-scenario.md](docs/creating-a-scenario.md) for the full step-by-step guide — package layout, every optional extension surface (run-detail API hook, frontend plug-in, per-scenario scripts), the canonical smoke-test recipe, and a pre-flight checklist.

## Project Structure

```
src/glossogen/
  cli.py                       # CLI: run, evaluate, serve, replace-agent
  autonomous_supervisor.py     # Round progression, event injection, resume
  channel_router.py            # Message storage + membership validation
  message_rewind.py            # State reconstruction at any message (fork/resume)
  message_history_builder.py   # Builds per-agent transcript history for fork/resume context
  replace_agent.py             # Round-boundary agent replacement (shared by API + CLI)
  run_jsonl_rewriter.py        # Shared JSONL rewriter for fork + replace-agent flows
  event_logger.py              # JSONL event writer
  event_bus.py                 # In-process pub/sub for SSE streaming
  simulation_server.py         # Embedded SSE server per simulation
  telemetry_settings.py        # Langfuse env config (LANGFUSE_* keys → enabled flag)
  telemetry_bootstrap.py       # Langfuse OTEL bootstrap + pydantic-ai instrumentation (run path only)
  telemetry_round_processor.py # Span processor stamping round_number onto generation spans

  runtime/                     # MCP server + coordination
    simulation_state.py        # Shared state: channels, sessions, locks, current round, injection delivery
    mcp_tools.py               # MCP tool definitions (read_notifications, read_channel, send_message)
    mcp_server.py              # FastMCP over Streamable HTTP
    game_clock.py              # Round progression and termination (delegates injection delivery to runtime)
    agent_session.py           # Per-agent notification queue, reaction delay, idle tracking

  runners/                     # Agent runner implementations
    pydantic_ai_runner.py      # Pydantic AI agent runner
    communication_protocol.py  # Shared prompts for agent communication

  models/                      # Pydantic data models
    event_base.py              # EventBase + TokenUsage (imported by scenario events)
    event.py                   # Core platform events + scenario-event auto-discovery
  llm/                         # LLM provider abstraction (used by evaluation)
  evaluation/                  # Post-hoc Metric / Measurement infrastructure
  scenario_registry.py         # SCENARIO_REGISTRY (separate from scenarios/__init__.py
                               #   to keep event discovery cycle-free)
  scenarios/                   # One folder per scenario (class + events + prompts + README)

modal/                         # Self-hosted LLM endpoint deployable to Modal (vLLM + Llama 3.3)
  serve_llama.py               # Modal app exposing OpenAI-compatible chat-completions API
  tool_chat_template_llama3.1_json.jinja  # vLLM tool-calling chat template
  smoke_test_llama.py          # End-to-end smoke test for the deployed endpoint
  README.md                    # Deploy + integration instructions

  server/                      # FastAPI web server (glossogen serve)
    identity/middleware.py     # Clerk-aware identity middleware: parses /g/{slug}, validates JWT
    identity/clerk_verifier.py # Networkless Clerk JWT verification (v2 nested o claim + v1 flat)
    identity/webhook_router.py # Svix-verified POST /api/clerk/webhook (groups sync)
    runs/listing.py            # Postgres-backed list_runs_for_group
    runs/lookup.py             # resolve_run_or_404 + register_new_run (group-scoped)
    run_launcher.py            # Shared run-launch utilities for REST and MCP start endpoints
    mcp/                       # MCP server at /mcp with OAuth
      browser.py               # FastMCP tools for run browsing and launching
      oauth_provider.py        # OAuth 2.0 authorization server provider
      oauth_storage.py         # Postgres-backed OAuth client/token storage (group-scoped tokens)
      asgi_context.py          # ASGI wrapper that primes RunContext from the token's group_id

  db/                          # Postgres data layer (psycopg3 async + alembic migrations)
    queries.py                 # Typed query helpers returning Pydantic rows
    pool.py                    # Async connection pool
    migrations/versions/       # Raw-SQL alembic revisions (groups + runs + oauth tables)

frontend/                      # Next.js web application
  src/proxy.ts                 # clerkMiddleware with organizationSyncOptions for /g/:slug
  src/app/g/[groupSlug]/       # All authenticated routes live under here
  src/app/sign-in/, sign-up/   # Clerk catch-all sign-in / sign-up flows
  src/app/select-org/          # OrganizationList for signed-in users with no active org
  src/features/auth/           # GroupProvider, GroupTopBar (org switcher + user button)
  src/features/mcp-config/     # MCP integration modal with connection instructions
```

See [Architecture.md](Architecture.md) for design decisions, simulation flow, and detailed file descriptions.

## Deployment

The application deploys to Railway as two services from a single repository. Each service has a `Dockerfile` and a `railway.toml` config-as-code file.

- **Backend** (`Dockerfile`, `railway.toml`): Python 3.12, FastAPI server with a persistent volume at `/data/runs` for simulation data.
- **Frontend** (`frontend/Dockerfile`, `frontend/railway.toml`): Node 22, Next.js standalone build.

Railway environment variables for the backend:

- `DATABASE_URL` — provision a Postgres database on Railway and attach its connection string. The backend won't boot without it.
- `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_JWT_KEY`, `CLERK_WEBHOOK_SECRET` — required for Clerk-gated multi-tenant auth. Leave all unset to run in single-tenant local mode.
- `CLERK_AUTHORIZED_PARTIES` — comma-separated frontend origins allowed to mint tokens (e.g. `https://frontend.up.railway.app`).
- `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`, etc.) — provider keys for running simulations.
- `ALLOWED_ORIGINS` — comma-separated frontend URLs for CORS.
- `OAUTH_ISSUER_URL` — public backend URL to enable MCP OAuth.
- `ENABLE_EVALUATIONS` — set to `false` to disable the REST evaluate endpoint (the frontend "Run Eval" button): the endpoint returns 403 and the frontend hides the button. Defaults to enabled. Does not affect the CLI `glossogen evaluate` command.

The frontend requires `NEXT_PUBLIC_API_URL` as a build arg pointing to the backend URL, plus `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` for Clerk-mode operation.

The backend container runs `alembic upgrade head` on every start so the schema is always at the latest revision before the server begins accepting requests.

## Linting

```bash
make lint              # runs both server and frontend linters
make lint-server       # server only (black, isort, ruff, pyright, vulture, custom linters)
make lint-frontend     # frontend only (prettier, eslint, stylelint, tsc)
make check-frontend    # frontend CI mode (prettier --check, no auto-fix)
```

### Vulture Dead Code Detection

Vulture runs at 60% confidence. False positives (Pydantic fields, FastAPI handlers, enum values, abstract methods) are suppressed via `vulture_whitelist.py`. To regenerate the whitelist after code changes:

```bash
VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 60 --make-whitelist 2>/dev/null | tee vulture_whitelist.py
```

Review the generated whitelist before committing — every entry should be a genuine false positive, not actual dead code.
