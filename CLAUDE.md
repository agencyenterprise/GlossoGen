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

- `src/` — application source code
- `src/schmidt/scenarios/<scenario_name>/` — one folder per scenario, containing:
  - `README.md` — scenario documentation
  - `scenario.py` — scenario class (channels, timing, tools, injections, turn logic, knobs schema)
  - `prompts/` — Jinja2 templates for agent system prompts and injection messages
  - `evaluation/` — scenario-specific evaluators (optional)
- `src/schmidt/runtime/` — autonomous mode runtime (MCP server + coordination):
  - `simulation_state.py` — shared state: channels, sessions, locks, callbacks, world context, token counters
  - `mcp_tools.py` — MCP tool definitions (read_notifications, read_channel, send_message, etc.)
  - `mcp_server.py` — starts FastMCP over Streamable HTTP
  - `game_clock.py` — round progression, injection delivery, termination detection
  - `agent_session.py` — per-agent notification queue, reaction delay, idle tracking
  - `scenario_mcp_tool.py` — ScenarioMcpTool for scenario-specific tool registration
  - `scenario_world.py` — ScenarioWorld ABC, WorldContext, MessageEvent, RoundAdvancedEvent
- `src/schmidt/runners/` — autonomous mode agent runners:
  - `agent_runner_base.py` — abstract base class for agent runners
  - `pydantic_ai_runner.py` — Pydantic AI agent runner via pydantic-ai framework
  - `communication_protocol.py` — shared prompts and constants for the agent communication protocol
- `src/schmidt/config_overrides.py` — Hydra-style dot-notation config override parser
- `src/schmidt/autonomous_supervisor.py` — autonomous mode orchestrator (supports resume via `RewindState`)
- `src/schmidt/message_rewind.py` — reconstructs simulation state at any message for fork/resume
- `src/schmidt/run_repository.py` — git-backed repository for run directories (init, commit, clone, checkout)
- `src/schmidt/message_history_builder.py` — reconstructs pydantic-ai ModelMessage history from JSONL events for fork/resume
- `src/schmidt/llm/` — LLM provider abstraction + Anthropic/OpenAI/HuggingFace implementations
- `src/schmidt/evaluation/` — generic evaluators and evaluation infrastructure
  - `evaluator_protocol.py` — `Evaluator` ABC and `EvaluatorFactory` type alias
  - `evaluator_registry.py` — registry mapping evaluator names to factory callables
  - `generic_evaluator_names.py` — canonical name list (avoids circular imports with `scenario_protocol`)
  - `round_transcript_builder.py` — builds per-round message transcripts from events (used by all generic evaluators)
  - `label_writer.py` — writes `eval:{evaluator}:{verdict}` labels to `labels.json` after evaluation
  - `language_strangeness_evaluator.py` — detects unusual grammar, structure, formatting (not codes/slang/neologisms)
  - `slang_emergence_evaluator.py` — detects informal register shifts and colloquial expressions
  - `neologism_evaluator.py` — detects genuinely invented words (not abbreviations or codes)
  - `shorthand_codes_evaluator.py` — detects abbreviation systems and symbol-to-meaning mappings
  - `round_ended_idle_evaluator.py` — flags rounds ending via the `all_agents_idle` trigger
  - `round_ended_timeout_evaluator.py` — flags rounds ending via the `round_timeout` trigger
  - `round_end_trigger_detection.py` — shared helpers for reading `RoundEnded` events
  - `prompts/` — Jinja2 templates for LLM judge prompts
- `src/schmidt/server/` — FastAPI web server exposing simulation data via REST and SSE streaming
  - `password_auth_middleware.py` — pure ASGI middleware for shared-password authentication
  - `runs/fork_router.py` — `POST /api/runs/{run_id}/fork` endpoint for creating forked runs
  - `mcp/browser.py` — MCP server mounted at `/mcp` for programmatic run browsing and launching (Claude Code, Cursor)
  - `mcp/oauth_provider.py` — OAuth 2.0 authorization server provider for MCP
  - `mcp/oauth_storage.py` — SQLite-backed storage for OAuth clients, codes, and tokens
  - `mcp/oauth_login_page.py` — login form for the MCP OAuth authorization flow
  - `run_launcher.py` — shared simulation launch helper used by REST and MCP run-start flows
- `linter/` — custom linting scripts
- `frontend/` — Next.js web application
  - `src/features/auth/` — authentication gate and login page
  - `src/features/mcp-config/` — MCP integration modal with connection instructions

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

- `list_scenarios` — lists available scenarios with knobs files, evaluators, and supported models/providers
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
├── .git/                          # Git history (one commit per meaningful event)
├── {scenario_name}.jsonl          # Event log (messages, reasoning, round transitions)
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines from Python logger, not in git)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate)
├── {scenario_name}_stdout.log     # (pipe stdout here, not in git)
└── fork_manifest.json             # (forked runs only) provenance: source_run_id, target_message_id
```

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

### Hydra-Style Config & Overrides

The `run` subcommand uses a unified config system inspired by Hydra. A base config file (`--config`) provides scenario knobs, and trailing `key=value` arguments override individual fields using dot-notation. The `agents.*` namespace is reserved for per-agent model/provider overrides.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --config <config-file.json> \
  [key=value overrides...] \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

Required flags: `--model`, `--provider` (`anthropic`, `openai`, `google-gla`, `ollama`), `--runs-dir`.
Optional flags: `--max-agent-turns` (default: 200), `--config <path>` (base config JSON file).

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

Internals: clones the source run's git repo at the commit produced by the source's `RoundAdvanced` event for `--round-start`. The cloned JSONL therefore contains every committed event up to and including that `round_advanced` (round N-1 fully ended in source — game phase, postmortem, both `round_ended` events) but no `injection_delivered` events for round N yet. On resume the game clock starts at round N and `_deliver_injections` fires the round-N injections fresh. The replaced agent's full event log is preserved on disk; its reconstructed pydantic-ai history is stripped of `text` / `thinking` parts and any tool calls targeting blocked channels (e.g. veyru's postmortem channels). The veyru world's per-team `outcomes` list is seeded from the source's `veyru_case_started` / `veyru_stabilization_judged` / `round_ended` events via `restore_state_from_events`, so the round-N injection's "PREVIOUS VEYRU RESULT" block reflects the source's actual round N-1 outcome. Cannot be used with `--round-start 1`. Non-replaced agents stay on their exact original models.

`--rounds-after-swap` defaults to `source_round_count - round_start` (the remaining rounds in the original run after the replacement boundary). The resumed simulation's `round_count` is set to `round_start + rounds_after_swap`.

**Per-channel history visibility (platform feature).** The replace-agent flow chooses, per channel the replaced agent is a member of, whether that channel's prior messages remain visible after resume.

- `--visible-history-channel CHANNEL` (repeatable): channels listed here keep their pre-resume history visible to the replaced agent. All other channels they belong to have `member_join_index` bumped to the current message count, so `read_channel` returns only post-resume messages there.
- When the flag is omitted, the CLI consults the source run's `replace_agent_default_channel_visibility: dict[str, bool]` knob (defined on `BaseKnobs`). Channels not listed in that map default to visible. Scenarios encode their per-channel defaults in the preset knob JSON files; no scenario code is required.

**Per-scenario knob overrides.** `--knobs <file.json>` is merged onto the source's `scenario_config` before validation. Veyru exposes `postmortem_disabled_at_start: bool` for this flow: setting it to `true` flips `world.disable_postmortem_globally()` at world construction, dropping the postmortem channel for the rest of the resumed simulation (no postmortem injections, no postmortem phase, sends to postmortem are rejected).

The replace-agent API endpoint is `POST /api/runs/{scenario}/{run_dir_name}/replace-agent`. Replace-agent runs appear in the run list with a "Replaced" badge.

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

After a simulation completes, score the log with LLM-as-judge evaluators. Evaluation uses `--provider` to select the LLM judge. The evaluate command reads the scenario configuration from the JSONL event log, so no scenario-specific flags (like `--knobs`) are needed.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate <scenario> \
  --run-dir ./runs/<scenario>/<timestamp> \
  --evaluators <comma-separated evaluator names> \
  --model <model> --provider <provider> \
  > ./runs/<scenario>/<timestamp>/eval_stdout.log 2>&1 &
```

Available evaluators per scenario:

Generic evaluators (available to all scenarios). Language-emergence evaluators are each scoped to a specific phenomenon — their prompts explicitly list what the other evaluators cover, so they do not overlap:

- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style (NOT codes, slang, or new words)
- `slang_emergence` — informal register shifts, colloquial expressions, casual nicknames (NOT codes or new words)
- `neologism` — genuinely invented words with new meanings (NOT abbreviations or code mappings)
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding (NOT new words or slang)
- `round_ended_idle` — flags rounds whose main phase ended because all agents went idle on `read_notifications` (deterministic, no LLM). Requires `round_ended` events in the log.
- `round_ended_timeout` — flags rounds whose main phase ended because the wall-clock duration limit was reached (deterministic, no LLM). Requires `round_ended` events in the log.

Scenario-specific evaluators:

- **veyru**: generic + the following veyru-specific evaluators:
  - `language_emergence` — novel compressed language in the fictional domain (LLM judge)
  - `round_success` — fraction of rounds the team stabilized the Veyru before collapse (deterministic, no LLM)
  - `round_success_after_resume` — same accounting as `round_success` but restricted to the rounds played after a replace-agent swap; also re-scores the source run over the same round window and reports the delta in evidence; reports N/A on non-resume runs (deterministic, no LLM)
  - `protocol_learned_after_swap` — whether two-team mode teams re-established a working protocol after an observer swap (LLM judge)

After evaluation, labels are automatically written to the run's `labels.json` in the format `eval:{evaluator}:{verdict}` where verdict is `identified`, `partial`, or `fail`. Previous `eval:` labels are replaced; user-added labels are preserved.

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
