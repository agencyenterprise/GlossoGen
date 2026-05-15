# schmidt-poc

## Setup

```bash
make install           # installs both server (uv sync) and frontend (npm ci)
make install-server    # server only
make install-frontend  # frontend only
```

## Linting

```bash
make lint              # runs both server and frontend linters
make lint-server       # server only (black, isort, ruff, mypy, pyright, vulture, custom linters)
make lint-frontend     # frontend only (prettier --write, eslint, stylelint, tsc)
make check-frontend    # frontend CI mode (prettier --check, no auto-fix)
```

## Project Structure

- For a step-by-step guide on adding a new scenario, see [docs/creating-a-scenario.md](docs/creating-a-scenario.md).
- `src/` — application source code
- `src/schmidt/scenarios/<scenario_name>/` — one folder per scenario, containing:
  - `README.md` — scenario documentation
  - `scenario.py` — scenario class (channels, timing, tools, injections, turn logic, knobs schema)
  - `prompts/` — Jinja2 templates for agent system prompts and injection messages
  - `evaluation/` — scenario-specific metrics (optional)
  - `events.py` — scenario-specific `EventBase` subclasses (auto-discovered)
  - `run_detail_extension.py` — optional hook for surfacing scenario-specific data on the run-detail API
  - `scripts/` — one-off scripts that import directly from this scenario (smoke runners, probe-bank generators, etc.). Cross-scenario tools live in the repo-root `scripts/` instead.
- `src/schmidt/runtime/` — autonomous mode runtime (MCP server + coordination):
  - `simulation_state.py` — shared state: channels, sessions, locks, callbacks, world context, token counters, current round, injection delivery (`deliver_round_injections`, `deliver_postmortem_injections`, `has_postmortem_for_round`)
  - `mcp_tools.py` — MCP tool definitions (read_notifications, read_channel, send_message, etc.)
  - `mcp_server.py` — starts FastMCP over Streamable HTTP
  - `game_clock.py` — round progression and termination detection (delegates injection delivery to `SimulationRuntime`)
  - `agent_session.py` — per-agent notification queue, reaction delay, idle tracking
  - `scenario_mcp_tool.py` — ScenarioMcpTool for scenario-specific tool registration
  - `scenario_world.py` — ScenarioWorld ABC, WorldContext, MessageEvent, RoundAdvancedEvent
- `src/schmidt/runners/` — autonomous mode agent runners:
  - `agent_runner_base.py` — abstract base class for agent runners
  - `pydantic_ai_runner.py` — Pydantic AI agent runner via pydantic-ai framework
  - `pydantic_ai_model_factory.py` — per-provider mapping from `(model, provider)` to a pydantic-ai `model=` argument and default `ModelSettings`; shared by the runner and the platform's post-simulation `protocol_probe` helper
  - `communication_protocol.py` — shared prompts and constants for the agent communication protocol
- `src/schmidt/config_overrides.py` — Hydra-style dot-notation config override parser
- `src/schmidt/scenario_registry.py` — maps scenario name strings to `SimulationScenario` classes; lives outside `schmidt.scenarios` package init so importing event-related modules doesn't trigger eager loading of every scenario
- `src/schmidt/autonomous_supervisor.py` — autonomous mode orchestrator (supports resume via `RewindState`)
- `src/schmidt/message_rewind.py` — reconstructs simulation state at any message for fork/resume
- `src/schmidt/run_repository.py` — git-backed repository for run directories (init, commit, clone, checkout)
- `src/schmidt/message_history_builder.py` — reconstructs pydantic-ai ModelMessage history from JSONL events for fork/resume
- `src/schmidt/llm/` — LLM provider abstraction + Anthropic/OpenAI/HuggingFace implementations
- `src/schmidt/evaluation/` — generic metrics and evaluation infrastructure
  - `metric_core/` — the Metric contract + I/O types
    - `metric_protocol.py` — `Metric` ABC; `compute(events, agent_configs, scenario, llm_provider, run_dir, options)` is the only entry point. Most metrics ignore `options`; metrics that need per-invocation flags (e.g. `protocol_probe`) read them off the passed `MetricRunOptions`.
    - `metric_run_options.py` — `MetricRunOptions` Pydantic model carrying per-invocation flags (`probe_round`, `probe_replicas`); built by the CLI from argparse and threaded into `scenario.run_evaluation(...)`.
    - `metric_registry.py` — `dict[str, type[Metric]]` mapping metric names to their classes; `cls()` builds an instance and `cls.compute(..., options=options)` runs it.
    - `measurement.py` — `Measurement`, `RoundObservation`, `AgentObservation`, and judge-side `RoundNote` Pydantic models
    - `generic_metric_names.py` — canonical name list (avoids circular imports with `scenario_protocol`)
  - `reports/` — on-disk report shape
    - `evaluation_report.py` — `EvaluationReport` schema, plus `load_report` / `write_report` / `merge_evaluation_costs` helpers
    - `evaluation_cost.py` — `EvaluationTokenUsage`, `EvaluationCost`, and `compute_evaluation_cost`
  - `metrics/` — concrete Metric implementations
    - `language_strangeness_metric.py` — detects unusual grammar, structure, formatting (not codes/slang/neologisms)
    - `slang_emergence_metric.py` — detects informal register shifts and colloquial expressions
    - `neologism_metric.py` — detects genuinely invented words (not abbreviations or codes)
    - `shorthand_codes_metric.py` — detects abbreviation systems and symbol-to-meaning mappings
    - `content_filter_refusal_metric.py` — counts ``ContentFilterError`` refusals across the run, with per-round + per-agent breakdowns
    - `perplexity_metric.py` — mean per-token surprisal of primary-channel messages under `gpt2`
    - `mcr_metric.py` — mean total characters per round on the primary channel
    - `mcm_metric.py` — mean characters per message on the primary channel
    - `round_success_metric.py` — generic; reads `RoundResultRecorded` events written by the game clock from `SimulationScenario.judge_round_result`. Single-team scenarios emit one Measurement (`metric_name="round_success"`); multi-team scenarios emit one per `team_id` (`round_success_team_a`, etc.). Returns `[]` if the scenario doesn't override the hook.
    - `round_success_after_resume_metric.py` — generic; re-scores `round_success` over the post-resume window. Reads `replace_manifest.json` / `cross_run_replace_manifest.json` and every `AgentSwappedMidRun` event; the per-window scoring delegates to the same `RoundResultRecorded` events as `round_success`. Returns `[]` on non-resume runs.
    - `protocol_learned_after_swap_metric.py` — generic LLM-judge; calls the scenario's `detect_protocol_boundary_window` to find the pre/post split and `build_communication_rounds` to render transcripts. Returns `[]` when either hook opts out.
    - `protocol_probe/` — generic protocol-probe metric family (4 metrics). Reads `SimulationScenario.get_protocol_probe_config()` for the per-scenario question bank and probe-prompt templates; returns `[]` when the hook returns `None`.
      - `protocol_probe_metric.py` — runs the probe LLM calls and writes `protocol_probe_responses.jsonl`
      - `protocol_probe_replica_self_similarity_metric.py` — within-(agent, question, cutoff) replica self-similarity
      - `protocol_probe_agent_pair_similarity_metric.py` — agent × agent matrix per (question, cutoff); skips on single-team runs
      - `protocol_probe_cutoff_trajectory_metric.py` — adjacent-cutoff drift per (agent, question)
      - `probe_agent.py`, `similarity_core.py`, `response_models.py` — shared helpers
    - `round_ended/` — round-end trigger metrics
      - `round_ended_idle_metric.py` — flags rounds ending via the `all_agents_idle` trigger
      - `round_ended_timeout_metric.py` — flags rounds ending via the `round_timeout` trigger
      - `trigger_detection.py` — shared helpers for reading `RoundEnded` events
  - `metric_core/` (additions):
    - `round_result_index.py` — `per_round_joint_success(events)` builds round→bool from `RoundResultRecorded` events (multi-team joint = all teams succeeded)
    - `protocol_boundary.py` — `ProtocolBoundaryWindow` NamedTuple returned by `detect_protocol_boundary_window`
    - `protocol_probe_config.py` — `ProtocolProbeConfig` NamedTuple returned by `get_protocol_probe_config`
    - `resume_anchors.py` — manifest + `AgentSwappedMidRun` reading helpers shared by `round_success_after_resume`
  - `log_reader.py` — JSONL event loading + scenario/agent config extraction (cross-cutting; used by CLI, server, runtime, and metrics)
  - `round_transcript_builder.py` — builds per-round message transcripts from events (used by all generic LLM-judge metrics)
  - `prompts/` — Jinja2 templates for LLM judge prompts + the `prompt_renderer.py` loader
- `src/schmidt/server/` — FastAPI web server exposing simulation data via REST and SSE streaming
  - `password_auth_middleware.py` — pure ASGI middleware for shared-password authentication
  - `runs/fork_router.py` — `POST /api/runs/{run_id}/fork` endpoint for creating forked runs
  - `runs/scenario_extension.py` — `ScenarioRunDetailExtension` ABC + auto-discovery of every scenario's optional `run_detail_extension.py`; powers the discriminated-union `scenario_extras` field on `RunDetailResponse`
  - `runs/run_detail_types.py` — leaf DTOs (`AgentDetail`, `ChannelMessage`) shared by `models.py` and scenario-side extensions so extensions can import them without re-entering `models.py` during its discovery-time import
  - `mcp/browser.py` — MCP server mounted at `/mcp` for programmatic run browsing and launching (Claude Code, Cursor)
  - `mcp/oauth_provider.py` — OAuth 2.0 authorization server provider for MCP
  - `mcp/oauth_storage.py` — SQLite-backed storage for OAuth clients, codes, and tokens
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
  - `src/features/runs/scenario-plugin.ts` — `ScenarioPlugin` interface (knobs form, round-detail panel, replace-agent defaults, tool-metadata renderer) — form state is `unknown` at the boundary so the registry can hold every plug-in under a single type
  - `src/features/runs/scenario-registry.ts` — eager-imports each scenario's optional `<scenario>/plugin.tsx`; `getScenarioPlugin(name)` resolves an unknown name to the default no-op plug-in

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

### Docstrings

- **Every module needs a module-level docstring** describing what it defines.
- **Every public class and important function needs a docstring.**
- **Be factual only.** Describe what the code does, not assumptions about why. Never use subjective language.
- **Be concise.** One to three sentences for most docstrings.

## Frontend

Stack: Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4, TanStack React Query, openapi-fetch.

### API Client & Type Safety

All API calls must use the generated typed client from `@/shared/lib/api-client`. Raw `fetch()` is forbidden — enforced by ESLint.

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
| `APP_PASSWORD` | Optional | Shared password for web UI auth (disabled if unset) |
| `ALLOWED_ORIGINS` | Optional | Comma-separated CORS origins (defaults to `http://localhost:3000`) |
| `SCHMIDT_RUNS_DIR` | Optional | Directory for simulation run data (defaults to `./runs`) |
| `OAUTH_ISSUER_URL` | Yes (for MCP) | Public backend URL for MCP OAuth (MCP is disabled if unset) |
| `PROD_API_URL` | Optional | Target prod server URL for the "Upload to prod" button (button hidden when unset) |
| `PROD_PASSWORD` | Optional | Bearer password for `PROD_API_URL` (required alongside `PROD_API_URL`) |
| `SELF_HOSTED_BASE_URLS` | Required for `--provider self-hosted` | JSON object mapping model name → OpenAI-compatible `/v1` base URL. Example: `{"meta-llama/Llama-3.3-70B-Instruct":"https://....modal.run/v1","Qwen/Qwen3-32B":"https://....modal.run/v1"}` |
| `SELF_HOSTED_API_KEY` | Required for `--provider self-hosted` | Bearer token shared across all entries in `SELF_HOSTED_BASE_URLS` (matches each server's `--api-key`) |
| `LOG_LEVEL` | Optional | Stdlib logging level for `schmidt` CLI commands and analysis scripts (`DEBUG`/`INFO`/`WARNING`/`ERROR`). Set to `DEBUG` to capture verbatim LLM-judge system prompt, user prompt, and structured-output JSON in stderr. Defaults to `INFO`. |
| `LLM_MAX_TOKENS` | Optional | Per-call output-token cap applied uniformly to the Claude (`max_tokens`), OpenAI (`max_output_tokens`), and HuggingFace (`max_tokens`) providers. Defaults to `16384`; bump higher if structured-output JSON truncates. |

Frontend environment variables go in `frontend/.env.local` (see `frontend/.env.local.example`):

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |

## Development

```bash
make dev            # start FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # start Next.js dev server on port 3000
```

## Authentication

The application supports two authentication modes: shared-password (for the REST API and optionally MCP) and OAuth 2.0 (for MCP clients).

### Shared-Password Authentication

Controlled by the `APP_PASSWORD` environment variable.

- **Enabled**: Set `APP_PASSWORD` to a password string. All API endpoints except `GET /api/health` require authentication.
- **Disabled**: Leave `APP_PASSWORD` unset. All endpoints are open (default for local development).

The backend middleware (`password_auth_middleware.py`) accepts credentials via:
- `Authorization: Bearer <password>` header (used by the typed API client)
- `?token=<password>` query parameter (used by SSE EventSource connections, which cannot set custom headers)

The frontend `AuthGate` component probes `POST /api/auth/verify` on mount. If auth is required, it shows a login page. The password is stored in `localStorage` and attached to all API requests via openapi-fetch middleware.

### MCP OAuth 2.0 Authentication

The MCP server at `/mcp` uses OAuth 2.0 with PKCE and dynamic client registration. It is controlled by the `OAUTH_ISSUER_URL` environment variable.

- **Enabled**: Set `OAUTH_ISSUER_URL` to the public base URL of the backend (e.g. `https://backend.up.railway.app`). The MCP server is mounted and protected by OAuth. The `/mcp` path is excluded from the shared-password middleware.
- **Disabled**: Leave `OAUTH_ISSUER_URL` unset. The MCP server is not mounted and the `/mcp` endpoint is unavailable.

OAuth configuration:
- Clients auto-register via `POST /mcp/register` (dynamic client registration, RFC 7591)
- Authorization uses the code flow with PKCE (RFC 7636) via `GET /mcp/authorize`
- When `APP_PASSWORD` is set, authorization redirects to a login form at `/mcp/oauth/login` for password verification
- When `APP_PASSWORD` is unset, authorization auto-approves (open access)
- Token exchange at `POST /mcp/token` issues access tokens (1 hour) and refresh tokens (30 days)
- OAuth metadata is discoverable at `GET /mcp/.well-known/oauth-authorization-server`
- Token state is stored in SQLite at `$SCHMIDT_RUNS_DIR/oauth.db`

Implementation files:
- `src/schmidt/server/mcp/oauth_provider.py` — `OAuthAuthorizationServerProvider` implementation
- `src/schmidt/server/mcp/oauth_storage.py` — SQLite-backed storage for clients, codes, and tokens
- `src/schmidt/server/mcp/oauth_login_page.py` — login form for the authorization flow

## MCP Integration

The backend exposes an MCP (Model Context Protocol) server at `/mcp` for programmatic access to simulation data from LLM clients like Claude Code or Cursor. The MCP server is mounted inside the existing FastAPI app and uses OAuth 2.0 for authentication. Requires `OAUTH_ISSUER_URL` to be set.

### Available Tools

- `list_scenarios` — lists available scenarios with knobs files, metrics, and supported models/providers
- `list_runs` — paginated run listing with filtering by scenario, model, fork status, and run status
- `get_run_metadata` — lightweight metadata for a single run: agents, channels, configuration, evaluation summary
- `get_run` — full run content with messages; opt-in sections for reasoning, tool use, debug logs, and system prompts; filtering by agent or channel
- `get_knobs_schema` — returns a scenario's knobs JSON Schema and available knobs preset files
- `get_knobs_preset` — loads a knobs preset JSON payload by scenario and preset name
- `start_run` — launches a simulation subprocess with scenario, model, provider, and optional knobs

### Connecting

From the web UI, click the **MCP** button on the runs page to see connection instructions. Clients discover OAuth automatically via the well-known metadata endpoint — no auth headers needed in the config.

**Claude Code:**

```bash
claude mcp add-json schmidt-runs '{"type":"http","url":"<API_URL>/mcp"}'
```

**Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "schmidt-runs": {
      "url": "<API_URL>/mcp"
    }
  }
}
```

Replace `<API_URL>` with the backend URL (e.g. `http://localhost:8000` for local development). The client handles OAuth registration, authorization, and token refresh automatically. If `APP_PASSWORD` is set, the user is prompted with a login form during the authorization flow.

## Deployment

The application deploys to Railway as two services from a single repository.

### Docker

- `Dockerfile` (repo root) — Backend: Python 3.12, uv, weasyprint system dependencies, git
- `frontend/Dockerfile` — Frontend: Node 22, three-stage build with Next.js standalone output

### Railway Configuration

Each service has a `railway.toml` config-as-code file:
- `railway.toml` (repo root) — Backend service: Dockerfile builder, `/api/health` healthcheck
- `frontend/railway.toml` — Frontend service: Dockerfile builder

### Railway Dashboard Setup

**Backend service**: root directory `/`, volume mounted at `/data/runs`.

Environment variables:
- `APP_PASSWORD` — shared password for authentication
- `ANTHROPIC_API_KEY` — required for simulations
- `ALLOWED_ORIGINS` — comma-separated frontend URLs for CORS (e.g. `https://frontend.up.railway.app`)
- `OAUTH_ISSUER_URL` — public backend URL to enable MCP OAuth (e.g. `https://backend.up.railway.app`)
- `OPENAI_API_KEY`, `HF_TOKEN` — optional provider keys

**Frontend service**: root directory `frontend`.

Build args:
- `NEXT_PUBLIC_API_URL` — backend service URL (e.g. `https://backend.up.railway.app`)

**Deploy order**: Backend first (get URL) → set as frontend `NEXT_PUBLIC_API_URL` build arg → deploy frontend → update backend `ALLOWED_ORIGINS` with frontend URL.

## Run Output Directory Structure

All simulation outputs use a standard directory layout. Each run directory is a git repository — meaningful events (messages, tool results, round advances) trigger commits that capture the JSONL and any workspace files.

```
runs/{scenario_name}/{unix_timestamp}/
├── .git/                              # Git history (one commit per meaningful event)
├── {scenario_name}.jsonl              # Event log (messages, reasoning, round transitions)
├── {scenario_name}_debug.jsonl        # Debug log (JSON lines from Python logger, not in git)
├── {scenario_name}_report.json        # Evaluation report (written by evaluate)
├── {scenario_name}_stdout.log         # (pipe stdout here, not in git)
├── labels.json                        # JSON array of label strings (e.g. ["baseline_oss"])
├── note.md                            # Optional free-text note for the run
├── fork_manifest.json                 # (forked runs only) provenance: source_run_id, target_message_id
├── replace_manifest.json              # (replace-agent runs only) provenance + post-swap channel visibility
├── cross_run_replace_manifest.json    # (cross-run replace-agent runs only) source_a/source_b/imported_model + post-swap channel visibility
├── imported_history_source.jsonl      # (cross-run replace-agent runs only) verbatim copy of Sim B's JSONL used to mount the imported agent's history
├── replace_config.json                # (replace-agent or cross-run runs only) merged scenario_config + model_overrides written by the orchestrator
├── resume_context_{agent_id}.json     # (resume / fork / replace-agent / cross-run runs) per-agent reconstructed pydantic-ai message history dumped at resume time for inspection
├── resume_context_{agent_id}_round_{R}.json  # (in-run scheduled swap) one file per AgentSwappedMidRun event capturing the swapped-in agent's seed history
├── protocol_probe_responses.jsonl     # (scenarios that implement get_protocol_probe_config) one row per (agent, question, replica)
├── protocol_probe_usage.json          # (same) per-model token usage + cost for that probe batch
├── protocol_probe_replica_self_similarity.json  # (same) within-run replica × replica matrices per (agent, question, cutoff)
├── protocol_probe_agent_pair_similarity.json    # (same) within-run agent × agent matrices per (question, cutoff); two-team runs
├── protocol_probe_cutoff_trajectory.json        # (same) per (agent, question) adjacent-cutoff series; multi-cutoff JSONLs
├── communication_open_coding.json               # (when communication_open_coding metric is run) free-form open-coding labels for this run
├── communication_feature_presence.json          # (when communication_feature_presence metric is run) per-category confidence vector against a consolidated ontology
└── multi_swap_cache.json              # streamlit Multi-swap tab cache (per-phase round_success); regenerated whenever the JSONL's size or mtime changes
```

### Run Labels

Labels are short tags attached to a run for filtering and grouping in the UI and in evaluation queries. They live in `labels.json` inside the run dir as a JSON array of strings.

Three ways to apply them:

1. **Frontend "Create simulation" page**: enter labels at form time. Frontend POSTs the run, polls until it appears, then calls `PUT /api/runs/{scenario}/{run_dir_name}/labels` with `{"labels": [...]}` — see [new-simulation-form.tsx](frontend/src/features/runs/new-simulation-form.tsx).
2. **Backend API**: same endpoint — `PUT /api/runs/{scenario}/{run_dir_name}/labels` with body `UpdateLabelsRequest{labels: list[str]}` — see [router.py:409](src/schmidt/server/runs/router.py#L409). The PUT replaces all labels (it does not append), so include any existing labels you want to keep.
3. **Direct file write** (orchestrator scripts): write `labels.json` directly to the run dir as soon as the dir exists. Faster than the API and avoids needing the backend to be running. Example:
   ```bash
   echo '["baseline_oss"]' > "runs/veyru/<timestamp>/labels.json"
   ```

**Important**: do not PUT labels after evaluations have run. Evaluations merge into `labels.json` (preserving prior labels), but a PUT replaces. Apply your labels *before* `schmidt evaluate` if you also want eval-derived labels to coexist.

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

The pattern matched runs labeled `["baseline", "budget=2000", "eval:content_filter_refusal:0", "eval:round_success:pass", ...]` and overwrote all of those eval-derived labels. They are NOT recoverable from git (labels.json is not tracked in the per-run git repos) and have to be regenerated via `schmidt evaluate`.

**Rules when bulk-modifying labels.json:**

1. **Always parse as JSON, never substring-match the file contents.** Use Python (`json.load`) and compare list membership precisely (`labels == ['baseline_oss', 'budget=2000']` not `'baseline_oss' in content`).
2. **Scope by run identity, not by label content.** If you're modifying runs you just created in this session, list those run dirs by mtime or by tracking the run IDs at launch. Don't infer them from current label state.
3. **Never overwrite — append.** If you must modify labels, read existing JSON, append/remove specific entries, write back. Only blow away the whole list if you're certain the run has no eval-derived labels (i.e. you just created it and `schmidt evaluate` has not run on it).
4. **If unsure, dry-run first.** Print which runs you'd modify and their current labels; ask the user to confirm before writing.

### Git-Backed Run History

Each run directory is initialized as a git repository at simulation start. The `EventLogger` commits after writing committable events (messages, tool results, rounds, injections). Non-committable events like `LLMResponseReceived` are written to JSONL but only appear in git as part of the next meaningful commit's diff.

All event types are committed except `llm_response_received` and `agent_connected` (high-volume, no forkable state). New event types are committed by default — no platform code changes needed.

Commit messages follow a structured format for searchability:
```
{event_type}: {summary}

event_id: {uuid}
timestamp: {iso8601}
```

Use `git log --oneline` in a run directory to see the simulation timeline.

## Running Simulations

Agents connect to a shared MCP server via the Pydantic AI framework. A game clock manages round progression. Always run simulations as a background process, piping all output to a log file.

**Canonical seed: `seed=42`.** Always use `seed=42` when launching comparison runs so results are comparable against the baseline. Do not vary the seed across replications — the seed fixes the case set, so running multiple times with the same seed measures LLM stochasticity on an identical workload. Only change the seed if the user explicitly asks for it.

**Canonical judge: `claude-haiku-4-5-20251001`.** Set `judge_model: "claude-haiku-4-5-20251001"` and `judge_provider: "anthropic"` in every scenario knobs file. Keeping the judge fixed across runs holds judge-side noise constant so cross-run comparisons measure agent behavior, not judge variance. Only change the judge if the user explicitly asks for it.

### Hydra-Style Config & Overrides

The `run` subcommand uses a unified config system inspired by Hydra. A base config file (`--config`) provides scenario knobs, and trailing `key=value` arguments override individual fields using dot-notation. The `agents.*` namespace is reserved for per-agent model/provider overrides.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --config <config-file.json> \
  [key=value overrides...] \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

Required flags: `--model`, `--provider` (`anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted`), `--runs-dir`.
Optional flags: `--max-agent-turns` (default: 200), `--config <path>` (base config JSON file).

The `self-hosted` provider points pydantic-ai at any OpenAI-compatible chat-completions endpoint. `SELF_HOSTED_BASE_URLS` is a JSON map from model name → `/v1` URL, so multiple self-hosted models can coexist; `SELF_HOSTED_API_KEY` is the bearer token shared across them. Reference deployments are in `modal/` (Llama 3.3 70B + Qwen3-32B, both vLLM with tool calling) — see `modal/README.md` for deploy steps. Once deployed and the env vars are set:

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json \
  > ./runs/veyru_stdout.log 2>&1 &
```

The pricing entry in `src/schmidt/token_pricing.py` is keyed by the literal model name (case-sensitive prefix match after dots→dashes); add a new entry there if you serve a different model.

Examples:

```bash
# Veyru with base config
VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json \
  > ./runs/veyru_stdout.log 2>&1 &

# Veyru with per-agent model overrides
VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json \
  agents.stabilization_engineer.model=gpt-5.4 agents.stabilization_engineer.provider=openai \
  > ./runs/veyru_stdout.log 2>&1 &

# Override knobs inline on top of a base config
VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json \
  max_round_duration_seconds=120 round_count=20 \
  > ./runs/veyru_stdout.log 2>&1 &
```

Override values are auto-parsed as JSON: `rounds=5` becomes int, `enabled=true` becomes bool, `name=alice` stays string.

Check progress by reading the stdout log file or the JSONL event log.

#### Knob co-dependencies: watch for cross-field validators

Scenarios' knob Pydantic models can have cross-field validators that reject otherwise-valid-looking inline overrides. Toggling one knob without its sibling fails preflight validation, the schmidt run subprocess exits before claiming a run directory, and any orchestrator that simply launches and polls for a new dir will silently lose the spec.

Known cases:

- **veyru**: `postmortem_after_swap=true` requires `postmortem_enabled=true`. When sweeping with `postmortem_enabled=false`, also pass `postmortem_after_swap=false` (the default knobs JSON has it set to true).

Defensive launcher pattern: when overriding a knob, also override every knob the scenario's `model_validator` checks against it. If you're unsure, run one foreground launch first to surface validation errors before queueing a sweep — those errors land in the launch's stdout/stderr log, not in the orchestrator log.

### Live Streaming

Every `schmidt run` starts an embedded streaming server on an ephemeral port and writes a `stream.json` manifest to the run directory. The `schmidt serve` process discovers this file and proxies the simulation's SSE stream to connected frontends. When the simulation ends, `stream.json` is deleted and the server falls back to JSONL tailing for the completed run.

### Resuming Failed Simulations

If a simulation errors midway through, resume from the last checkpoint using the `--resume` flag pointing at the existing run directory.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --resume ./runs/<scenario>/<timestamp> \
  --config <original-config.json> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The `--resume` flag requires the same `--config` as the original run. The `--runs-dir` flag is still required but ignored when resuming.

### Forking Runs (Message-Level Rewind)

The web UI supports forking a completed simulation from any message. In the run detail view, hover over a message to reveal an edit button. Edit the message text, then click the play button to fork. A new simulation starts with the channel history up to that message (with the edit applied), and agents continue from there.

Forking uses the git-backed run history:
1. Find the git commit corresponding to the target message
2. Clone the source run's git repository to a new run directory
3. Check out the target commit — the JSONL and all workspace files are at the correct state
4. Apply message text edits to the JSONL and assign a new run ID
5. Write `fork_manifest.json` for provenance, commit the edits
6. Launch `schmidt run --resume <new_dir>` as a background subprocess
7. Reconstruct a conversation transcript from the event log and inject it as each agent's system prompt context

Agents receive the conversation history (channel messages, scenario injections, round transitions) as context. They do not receive their prior reasoning — only externally visible state — so they re-derive their thinking naturally in response to the edited message.

The fork API endpoint is `POST /api/runs/{run_id}/fork`. Forked runs appear in the run list with a "Fork" badge and show a lineage link in the run detail header.

### Replacing an Agent (Round-Level Rewind)

Replay a finished run from the start of a chosen round with one specific agent restarted on a fresh history while every other agent keeps its full reconstructed history. Useful for asking "could a fresh agent follow the engineer from here on?" — a direct, empirical alternative to a judge.

```bash
schmidt replace-agent veyru \
  --source-run-dir ./runs/veyru/<timestamp> \
  --round-start 5 \
  --replaced-agent-id field_observer \
  --model claude-sonnet-4-6 --provider anthropic \
  --runs-dir ./runs \
  [--rounds-after-swap N] \
  [--visible-history-channel CHANNEL ...] \
  [--knobs path/to/overrides.json]
```

Internals: clones the source run's git repo at the commit produced by the source's `RoundAdvanced` event for `--round-start`. The cloned JSONL therefore contains every committed event up to and including that `round_advanced` (round N-1 fully ended in source — game phase, postmortem, both `round_ended` events) but no `injection_delivered` events for round N yet. On resume the game clock starts at round N and calls `runtime.deliver_round_injections(N)` to fire the round-N injections fresh. The replaced agent's full event log is preserved on disk; its reconstructed pydantic-ai history is stripped of `text` / `thinking` parts and any tool calls targeting blocked channels (e.g. veyru's postmortem channels). The veyru world's per-team `outcomes` list is seeded from the source's `veyru_case_started` / `veyru_stabilization_judged` / `round_ended` events via `restore_state_from_events`, so the round-N injection's "PREVIOUS VEYRU RESULT" block reflects the source's actual round N-1 outcome. Cannot be used with `--round-start 1`. Non-replaced agents stay on their exact original models.

`--rounds-after-swap` defaults to `source_round_count - round_start` (the remaining rounds in the original run after the replacement boundary). The resumed simulation's `round_count` is set to `round_start + rounds_after_swap`.

**Per-channel history visibility (platform feature).** The replace-agent flow chooses, per channel the replaced agent is a member of, whether that channel's prior messages remain visible after resume.

- `--visible-history-channel CHANNEL` (repeatable): channels listed here keep their pre-resume history visible to the replaced agent. All other channels they belong to have `member_join_index` bumped to the current message count, so `read_channel` returns only post-resume messages there.
- When the flag is omitted, the CLI consults the source run's `replace_agent_default_channel_visibility: dict[str, bool]` knob (defined on `BaseKnobs`). Channels not listed in that map default to visible. Scenarios encode their per-channel defaults in the preset knob JSON files; no scenario code is required.

**Per-scenario knob overrides.** `--knobs <file.json>` is merged onto the source's `scenario_config` before validation. Veyru exposes `postmortem_disabled_at_start: bool` for this flow: setting it to `true` flips `world.disable_postmortem_globally()` at world construction, dropping the postmortem channel for the rest of the resumed simulation (no postmortem injections, no postmortem phase, sends to postmortem are rejected).

The replace-agent API endpoint is `POST /api/runs/{scenario}/{run_dir_name}/replace-agent`. Replace-agent runs appear in the run list with a "Replaced" badge.

### Cross-Run Replacing an Agent (Round-Level Rewind, Different Source for the Imported Agent)

Cross-run replace-agent is a sibling of replace-agent that imports an agent from a *different* completed run (Sim B) into a target run (Sim A) at a chosen round boundary. Same scenario and same `agent_id` only. The imported agent retains its **full pydantic-ai history** (text + thinking + tool calls) from Sim B; non-replaced agents in Sim A continue with their full Sim A history.

```bash
schmidt cross-run-replace-agent veyru \
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

**Default for `--source-b-round-end`** is `min(round_start - 1, B_max_round)` — temporally aligned with Sim A's swap point but clamped to the last round Sim B actually played, so the imported agent always gets the largest possible slice of B's history without exceeding what B reached. Example: `round_start=20` against a Sim B that only ran 15 rounds → `source_b_round_end=15`.

**Default for `--model`/`--provider`** is to read Sim B's `AgentRegistered` for the imported agent (so the imported agent runs under the same model it used in Sim B). Override with `--model M --provider P` to test cross-team behaviour with a different model. Both must be provided together.

**Imported agent history reconstruction.** The cross-run flow extends `AgentHistoryFilter` with an `imported: ImportedHistory | None` slot (events + target_timestamp + cutoff_round). When set, that agent's history is rebuilt from Sim B's `imported_history_source.jsonl` (a verbatim copy of Sim B's JSONL placed inside the new run dir) and the agent's system prompt is taken from Sim B's `AgentRegistered`. All other agents continue to use Sim A's events. Channel-blocking on the reconstructed history covers the scenario's default blocked channels (e.g. veyru's postmortem) plus any channel the imported agent had in Sim B but is missing in Sim A.

**Postmortem on cross-run runs.** The FE modal sets `postmortem_disabled_at_start: true` for veyru by default (so opus and gpt-5.4 don't have a backchannel to re-align protocols after the swap). The CLI does **not** auto-set this — pass `--knobs /tmp/cross_team_knobs.json` with `{"postmortem_disabled_at_start": true}` for the same effect. Forgetting this contaminates cross-team experiments.

**Manifest + provenance.** Persisted as `cross_run_replace_manifest.json` (parallel to `replace_manifest.json`). Carries both `source_a_run_id` (target timeline) and `source_b_run_id` (where the imported agent came from), plus `imported_model`/`imported_provider`, `round_start`, `source_b_round_end`, `rounds_after_swap`, `replaced_agent_id`, `channels_with_visible_history`, `blocked_tool_call_channels`. The discovery layer surfaces this on `RunSummary` / `RunDetailResponse` as `cross_run_replace_agent_source`. Cross-run runs appear in the run list with a violet "Cross-run" badge that links back to both sources.

**API endpoint** is `POST /api/runs/{scenario}/{run_dir_name}/cross-run-replace-agent`. The path's `{scenario}/{run_dir_name}` identifies Sim A; the body's `source_b_run_id` identifies Sim B. The `GET /api/runs` listing accepts `?scenario=&contains_agent_id=&status=` filters used by the FE modal's Sim B picker.

**Verifying the imported history.** Each resumed run writes `resume_context_{agent_id}.json` to the new run dir capturing the exact reconstructed pydantic-ai messages handed to that agent on its first turn. For cross-run runs, `resume_context_<replaced_agent_id>.json`'s tail should match Sim B's last few `field_observer` (or whichever role) messages verbatim — that confirms the cross-run history is being mounted from Sim B and not contaminated by Sim A.

**Label convention.** Cross-run runs are labelled `cross_team` plus a range tag like `15-25` (rounds played post-swap). The streamlit results viewer's "Cross-swap" tab filters on `cross_team` and plots `round_success_after_resume` per `(imported_model, round_start)` bucket against both Source A and Source B accuracy on the same rounds. Apply labels by writing `labels.json` directly *before* `schmidt evaluate` runs (the eval-derived labels merge into that file).

**`round_success_after_resume` works for both flows.** The metric reads either `replace_manifest.json` or `cross_run_replace_manifest.json` and projects to a common `_ResumeAnchor` (`round_start`, `rounds_after_swap`, `source_run_id`, `source_run_dir`). For cross-run runs, the comparison is against Sim A (`source_a_*`) — i.e. "did the imported agent perform better/worse than what the original agent achieved over the same window?".

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

**Streamlit Multi-swap tab**: per-phase round-success bar chart with Δ pp annotations between phases.

### Per-Agent Model Overrides

Each agent uses the default `--model` and `--provider` unless overridden. Per-agent overrides live in `model_overrides` inside scenario knobs/config. The CLI also supports `agents.*` dot-notation overrides, which are normalized into `model_overrides`.

**CLI usage:** Pass dot-notation overrides:

```bash
schmidt run veyru --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default.json \
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

**Web UI:** The "Create simulation" page shows an "Agent Model Overrides" section after selecting a scenario. Each agent can be individually overridden to a different model/provider. The fork dialog also supports per-agent overrides.

**Backend flow:** `POST /api/runs/start` and `POST /api/runs/{run_id}/fork` accept only knobs/config payloads; there is no top-level `model_overrides` field. Preflight validation reads `model_overrides` from knobs/config, validates provider names, and validates agent IDs against scenario roles before launch.

**Agent discovery:** `POST /api/scenarios/{scenario_name}/agents` accepts `{knobs}` and returns the agent IDs and role names for the given configuration. Used by the frontend to populate the override UI. Each scenario implements `get_agent_roles(knobs)` as a classmethod.

### IMPORTANT: Monitoring Long-Running Processes

When running simulations, evaluations, or any long-running background process, **always** follow this pattern:

1. Launch the process in the background (with `run_in_background` or `&`)
2. Immediately after launch, `sleep 30` then check the log file for progress
3. Report a brief status update to the user
4. Repeat: `sleep 30`, check, report — until the process completes
5. Never use `while` loops or polling constructs — use sequential sleep/check/report cycles

### Launching Replace-Agent Runs in the Background

`schmidt replace-agent` is a one-shot CLI that prepares the new run directory and spawns the simulation as a detached subprocess (`subprocess.Popen` with `start_new_session=True`). The CLI returns immediately with `new_run_id=...` and `new_run_dir=...`; the simulation runs independently and writes its own `<scenario>_stdout.log` inside the new run directory.

Single replace-agent run, monitor pattern:

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt replace-agent veyru \
  --source-run-dir ./runs/veyru/<source_timestamp> \
  --round-start 15 \
  --replaced-agent-id field_observer \
  --model gpt-5.4 --provider openai \
  --runs-dir ./runs \
  --knobs /tmp/replace_knobs.json
# CLI prints new_run_id=veyru/<new_timestamp>; that subprocess is now running detached.
# Monitor: sleep 30 → tail ./runs/veyru/<new_timestamp>/veyru_stdout.log → repeat.
```

### Parallel Replace-Agent Orchestration

To run several replace-agent variants while keeping at most N simulations live, use a small bash orchestrator. Each `schmidt replace-agent` call returns in ~25s after spawning its detached `python -m schmidt run veyru ... --resume` subprocess; the orchestrator polls active simulations via `pgrep` against the `Python -m schmidt run ... --resume` cmdline, sleeps when full, and launches the next spec when a slot frees up.

Save as `/tmp/replace_orchestrator.sh` (or anywhere outside the repo so it doesn't get committed):

```bash
#!/bin/bash
cd /Users/nsander/workspace/schmidt-poc

SOURCE=runs/veyru/<source_timestamp>
KNOBS=/tmp/replace_knobs.json   # e.g. {"postmortem_disabled_at_start": true}
RUNS_DIR=runs
MAX_PARALLEL=3
LOG=/tmp/replace_orchestrator.log

# Each spec is "round_start rounds_after_swap".
queue=(
  "15 10"
  "20 5"
  "10 15"
)

count_running() {
  # Match the python simulation processes only — capital "Python" comes from
  # the homebrew python.framework binary path, so bash/pgrep subshells that
  # mention the pattern as a literal string do not match.
  pgrep -f "Python -m schmidt run veyru .* --resume" 2>/dev/null | wc -l | tr -d ' '
}

echo "=== Started at $(date) ===" >> "$LOG"
for spec in "${queue[@]}"; do
  read -r round_start rounds_after_swap <<< "$spec"
  while [ "$(count_running)" -ge "$MAX_PARALLEL" ]; do
    sleep 30
  done
  echo "$(date): launching round_start=$round_start rounds_after_swap=$rounds_after_swap" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m schmidt replace-agent veyru \
    --source-run-dir "$SOURCE" \
    --round-start "$round_start" \
    --rounds-after-swap "$rounds_after_swap" \
    --replaced-agent-id field_observer \
    --model gpt-5.4 --provider openai \
    --runs-dir "$RUNS_DIR" \
    --knobs "$KNOBS" >> "$LOG" 2>&1
  sleep 2  # let claim_run_dir get a unique unix-second slot
done
echo "$(date): all launches complete" >> "$LOG"
```

Launch the orchestrator detached so it survives the session:

```bash
nohup bash /tmp/replace_orchestrator.sh > /tmp/replace_orchestrator.stdout 2>&1 &
disown
```

Monitoring pattern (every ~30s):

```bash
tail -20 /tmp/replace_orchestrator.log
pgrep -af "Python -m schmidt run veyru .* --resume"
```

`pgrep` pitfalls:
- The pattern **must** anchor on `Python` (capital) so bash/zsh subshells that contain the string verbatim don't false-match. The same applies to any wrapper command (e.g. a `Bash` tool call running `pgrep` on a string that quotes the pattern — that command's argv contains the pattern, and a loose pattern like `schmidt run veyru` will count it).
- Same caveat for the orchestrator's `count_running` function — keep it in a function (not inlined into a wrapping command) and use the tight pattern.

The orchestrator has no automatic recovery: if it dies, simulations keep running but no further launches happen. To resume, recompute the remaining queue (subtract already-launched specs from your full plan) and relaunch with the trimmed `queue=(...)`.

## Running Evaluations

After a simulation completes, score the log with one or more **metrics** — both deterministic ones and LLM-as-judge ones live behind the same `Metric` abstraction, returning a `Measurement` (`score`, `score_unit`, `summary`, `per_round`, `per_agent`). Evaluation uses `--provider` to select the LLM judge for the LLM-driven metrics; deterministic metrics ignore it. The evaluate command reads the scenario configuration from the JSONL event log, so no scenario-specific flags (like `--knobs`) are needed.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate <scenario> \
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

**Not-applicable metrics return `[]`.** When a metric detects it cannot apply to the current run (e.g. `protocol_probe_agent_pair_similarity` on a single-team run, `round_success_after_resume` on a non-resume run, `perplexity`/`mcr`/`mcm` on a scenario with no primary channel, the LLM-judge metrics on runs with no link messages, `protocol_learned_after_swap` on runs without a swap boundary, `communication_*` on runs with no link data), it returns an empty list and logs an INFO-level skip line. No zero-score sentinel Measurement is written. Existing entries from prior invocations are preserved via `merge_measurements` until the next invocation that produces a real Measurement for that metric_name replaces them — to forcibly drop stale not-applicable entries from a report, delete the report file before re-evaluating.

Metrics that DO emit a zero-score Measurement keep doing so when the count is a legitimate observation: `round_ended_idle`, `round_ended_timeout`, and `content_filter_refusal` all use `score = 0` to mean "this run had zero rounds/refusals with the trigger."

**`evaluation_cost` accumulates across invocations.** Each call to `schmidt evaluate` adds its provider usage onto the existing report's `evaluation_cost.usage` (via `merge_evaluation_costs` in [evaluation_report.py](src/schmidt/evaluation/reports/evaluation_report.py)) when the `(model, provider_name)` pair matches. Mismatched model/provider resets the cumulative cost to the new invocation's value (a mid-stream judge swap invalidates the running total). The `estimated_cost_usd` is recomputed each write from the summed usage. Implication: a re-run with no real LLM calls (e.g. a metric that errors before generating, or a not-applicable invocation) no longer clobbers prior cost data to zero.

Metrics no longer write `eval:` labels into `labels.json` — filter on `score` or on the `per_round` list directly.

Available metrics per scenario:

Generic metrics (available to all scenarios):

- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style (NOT codes, slang, or new words). LLM judge; `score` = number of rounds with detected anomalies.
- `slang_emergence` — informal register shifts, existing-word repurposing (NOT codes or new words). LLM judge; `score` = number of rounds with detected slang.
- `neologism` — genuinely invented words with new meanings (NOT abbreviations or code mappings). LLM judge; `score` = number of rounds with detected neologisms.
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding (NOT new words or slang). LLM judge; `score` = number of rounds with detected codes.
- `perplexity` — mean per-token surprisal of primary-channel messages under `gpt2`, reported per round (deterministic, no LLM judge). `score` = overall mean nats; `per_round` carries per-round mean+std+message count. Skips scenarios with no primary channel.
- `mean_chars_per_round` — total characters of all primary-channel messages in a round, averaged across rounds (deterministic, no LLM judge). `score` = mean chars/round; `per_round` carries per-round total + message count. Skips scenarios with no primary channel. The headline throughput number — in Veyru this maps directly to `time_budget_seconds` (one char = one second).
- `mean_chars_per_message` — characters per primary-channel message, averaged across all messages (deterministic, no LLM judge). `score` = overall mean chars/message; `per_round` carries per-round mean+std+message count. Skips scenarios with no primary channel. Normalizes MCR by message count: rounds that need more back-and-forth no longer inflate the score, so MCM isolates per-message verbosity from message density.
- `round_ended_idle` — flags rounds whose main phase ended because all agents went idle on `read_notifications` (deterministic, no LLM). `score` = count of idle-ended rounds. Requires `round_ended` events in the log.
- `round_ended_timeout` — flags rounds whose main phase ended because the wall-clock duration limit was reached (deterministic, no LLM). `score` = count of timeout-ended rounds. Requires `round_ended` events in the log.
- `content_filter_refusal` — counts `ContentFilterError` refusals across the run (deterministic, no LLM). `score` = total refusal count; `per_round` lists rounds with at least one refusal; `per_agent` lists per-agent counts.
- `communication_open_coding` — pass 1 of the open-coding → ontology → relabel pipeline. One LLM call per run feeds the judge every primary-channel message plus the scenario-rendered per-round ground truth (via `SimulationScenario.build_communication_rounds`), and asks for free-form short labels naming communication-pattern features (multi-label per run, no pre-specified vocabulary). Writes `communication_open_coding.json` to the run dir with each label's evidence round and quote. `score` = number of free-form labels. Followed by `scripts/consolidate_communication_ontology.py` (one LLM call across N runs of one scenario, writes a versioned ontology under `runs/<scenario_name>/_ontology/<version>.json`) and then `communication_feature_presence` for relabel. **Returns `[]` (no Measurement)** when the scenario does not implement the `build_communication_rounds` hook.
- `communication_feature_presence` — pass 3 of the same pipeline. Accepts `--ontology-path PATH` to pin a specific ontology JSON; when omitted the metric auto-resolves the most recently modified ontology JSON under `runs/<scenario>/_ontology/`. One LLM call per run re-reads the same per-round transcript view against the ontology's categories and emits a 0–1 confidence per category. Writes `communication_feature_presence.json` (full feature-presence vector + ontology provenance). `score` = number of categories scoring ≥0.5. Passes 1 and 3 read the same `CommunicationRoundView` rows so confidences are commensurable with the open-coding labels. **Returns `[]` (no Measurement)** when the scenario does not implement the `build_communication_rounds` hook.
- `round_success` — generic; reads `RoundResultRecorded` events. Single-team scenarios emit one Measurement (`metric_name="round_success"`); multi-team scenarios emit one per `team_id` (`round_success_team_a`, etc.). **Returns `[]`** when the scenario doesn't override `judge_round_result`.
- `round_success_after_resume` — generic; same accounting as `round_success` over the post-resume window. Reads `replace_manifest.json` / `cross_run_replace_manifest.json` and every `AgentSwappedMidRun` event; the comparison in `summary` is against the source run's same-window `round_success`. **Returns `[]`** on non-resume runs.
- `protocol_learned_after_swap` — generic LLM judge; uses `detect_protocol_boundary_window` (default: first `AgentSwappedMidRun`) to find the pre/post split and `build_communication_rounds` to render transcripts. `score` = number of post-boundary rounds with observable newcomer protocol evidence. **Returns `[]`** when either hook opts out (no boundary, or scenario doesn't implement `build_communication_rounds`).
- `protocol_probe` — generic; probes each agent post-simulation against the scenario's fixed test bank, writing one row per (agent, question, replica) to `protocol_probe_responses.jsonl`. Each agent is probed under its own original model (read from `AgentRegistered`), not the eval `--model`. The scenario supplies the question bank, probe-prompt templates, and role-name mapping via `get_protocol_probe_config()`. Requires `--probe-replicas N` (≥1); optional `--probe-round R` is an **exclusive** cutoff — every tool call with `round_number >= R` is dropped, so the reconstructed history covers rounds `1..R-1` (inclusive). To capture state at the END of round R, pass `--probe-round=R+1`. Token usage + dollar cost go to `protocol_probe_usage.json`. `score` = total probe rows written. **Returns `[]`** when `get_protocol_probe_config()` returns `None`.
- `protocol_probe_replica_self_similarity` — generic; for each `(agent_id, question_id, cutoff_round)` group with ≥2 replicas, computes the upper-triangle mean of the replica × replica normalized-Levenshtein matrix on `response_text`. `score` = macro mean across groups; matrices persisted to `protocol_probe_replica_self_similarity.json`. Saturation at 1.0 is the expected signal for a converged protocol. **Returns `[]`** when `protocol_probe_responses.jsonl` is missing or no group has ≥2 replicas.
- `protocol_probe_agent_pair_similarity` — generic; agent × agent matrix per (question, cutoff). `score` = macro mean across groups; persisted to `protocol_probe_agent_pair_similarity.json`. Only meaningful in two-team / cross-team runs. **Returns `[]`** on single-team runs.
- `protocol_probe_cutoff_trajectory` — generic; for each `(agent_id, question_id)` pair where the JSONL contains rows from ≥2 distinct `cutoff_round` values, computes the mean cross-replica similarity between each adjacent cutoff snapshot. `score` = macro mean across all adjacent-cutoff pairs; persisted to `protocol_probe_cutoff_trajectory.json`. **Returns `[]`** when the JSONL has only one cutoff value.

Scenarios opt into the platform metrics by implementing the corresponding hooks on `SimulationScenario`:

| Hook | Enables |
|---|---|
| `judge_round_result(round_number, trigger) -> list[RoundResult]` | `round_success`, `round_success_after_resume` |
| `build_communication_rounds(events) -> list[CommunicationRoundView]` | `communication_open_coding`, `communication_feature_presence`, `protocol_learned_after_swap` |
| `detect_protocol_boundary_window(events, agent_configs) -> ProtocolBoundaryWindow \| None` | `protocol_learned_after_swap` (default returns first `AgentSwappedMidRun`; override to also detect scenario-specific boundaries like intern takeover / two-team observer swap) |
| `get_protocol_probe_config() -> ProtocolProbeConfig \| None` | `protocol_probe`, `protocol_probe_replica_self_similarity`, `protocol_probe_agent_pair_similarity`, `protocol_probe_cutoff_trajectory` |
| `restore_state_from_events(events)` | Accurate "previous round" injection context after fork / resume / replace-agent |
| `get_replace_agent_blocked_tool_call_channels() -> frozenset[str]` | Strips scenario-private channel traffic (e.g. postmortem) from replaced agent's reconstructed history |

There are no scenario-specific metrics left — every scoring concept (round-success, post-resume re-scoring, language emergence, protocol learning, protocol probing) is platform code that consumes scenario data through these hooks. Scenarios only ship their domain-specific events + the hooks that surface them.

## Destructive Actions

**Always ask the user before deleting or stopping anything.** This includes:
- Deleting run directories, log files, or any simulation output
- Killing running processes (simulations, servers, etc.)
- Removing files, branches, or data of any kind

Never assume cleanup is wanted. Ask first, act second.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
3. If vulture reports new false positives, regenerate the whitelist: `VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 60 --make-whitelist > vulture_whitelist.py`
