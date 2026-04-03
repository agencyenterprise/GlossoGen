# schmidt-poc

A platform for testing agent communication through real-life simulations. LLM-based agents run as independent Claude Code processes connected via MCP. Agents decide when to speak; a game clock manages round progression and injects scenario events. All interactions are logged for post-hoc evaluation. A web UI displays simulation runs and evaluation results.

## Setup

```bash
make install
```

This installs both the Python server dependencies (`uv sync`) and the frontend dependencies (`npm ci`).

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

See `.env.example` for all available variables (API keys, authentication, CORS). At minimum, set `ANTHROPIC_API_KEY`.

## Running a Simulation

The CLI auto-generates a timestamped subdirectory under `--runs-dir`. Each round, agents communicate freely until all are idle or the round duration expires.

```bash
# Incident Response
VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
  --model claude-sonnet-4-20250514 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/incident_response/knobs_baseline.json \
  > ./runs/incident_response_stdout.log 2>&1 &

# Car Recall
VIRTUAL_ENV= uv run --no-sync python -m schmidt run car_recall \
  --model claude-sonnet-4-20250514 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/car_recall/knobs_baseline.json \
  > ./runs/car_recall_stdout.log 2>&1 &

# Product Launch
VIRTUAL_ENV= uv run --no-sync python -m schmidt run product_launch \
  --model claude-sonnet-4-20250514 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/product_launch/knobs_baseline.json \
  > ./runs/product_launch_stdout.log 2>&1 &
```

Flags:
- `--provider` — LLM provider: `anthropic`, `openai`, `google-gla`, `ollama` (required)
- `--mcp-port` — Port for the MCP server (default: 8001)
- `--max-agent-turns` — Maximum agentic turns per agent (default: 200)
- `--resume` — Resume from an existing run directory after a crash

Check progress by reading the stdout log or the JSONL event log in the run directory.

### Resuming a Failed Simulation

If a simulation crashes or is killed, resume using the `--resume` flag pointing at the existing run directory.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --resume ./runs/<scenario>/<timestamp> \
  --config <original-config.json> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The simulation picks up from where it left off, preserving channel messages and scenario state. The `--resume` flag requires the same `--config` as the original run.

### Forking Runs (Message-Level Rewind)

The web UI supports forking a completed simulation from any message. In the run detail view, hover over a message to reveal an edit button. Edit the message text, then click the play button to create a fork — a new simulation that starts with channel history up to that message (with the edit applied). Agents continue from there with full context of the prior conversation.

Forked runs appear in the run list with a "Fork" badge and link back to the source run. The fork API is also available programmatically via `POST /api/runs/{run_id}/fork`.

## Run Output Directory Structure

All simulation outputs use a standard directory layout under `runs/`:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl          # Event log
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines, visible in FE Logs tab)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate)
└── fork_manifest.json             # (forked runs only) provenance tracking
```

## Running Evaluation

After a simulation completes, point `--run-dir` at the specific run directory. Evaluation uses `--provider` to select the LLM judge.

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate incident_response \
  --run-dir ./runs/incident_response/1742234567 \
  --evaluators secret_leak,instruction_adherence,cooperation \
  --model claude-sonnet-4-20250514 --provider anthropic
```

Generic evaluators (available to all scenarios): `secret_leak`, `instruction_adherence`, `cooperation`, `communication_pattern`

Scenario-specific evaluators:

- **incident_response**: generic evaluators only
- **car_recall**: `fact_surfacing`, `report_divergence`, `decision_correctness`
- **product_launch**: `launch_outcome`, `emergent_behavior`, `information_integrity`, `coordination_efficiency`, `conflict_resolution`, `report_accuracy`
- **persuasion_debate**: `persuasion_accuracy`, `persuasion_dynamics`

Output is a JSON report with per-evaluator verdicts, scores, evidence, and per-agent breakdowns.

## Web UI

A FastAPI backend + Next.js frontend for browsing simulation runs. The frontend streams events in real time via SSE for in-progress runs.

### Authentication

Set `APP_PASSWORD` in `.env` to require a shared password for the web UI. All API endpoints except the health check are protected. If `APP_PASSWORD` is unset, authentication is disabled (default for local development).

### Starting the Servers

```bash
make dev            # FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # Next.js dev server on port 3000
```

The frontend displays a list of all simulation runs with scenario name, timestamp, message count, status (including in-progress runs), evaluation status, and fork badges. Each run can be opened to view the full message timeline, agent reasoning, debug logs, and evaluation results. Completed runs support message-level editing and forking — hover over any message to edit it and launch a new simulation from that point.

### Live Token Streaming

Every `schmidt run` starts an embedded streaming server on an ephemeral port and writes a `stream.json` discovery file to the run directory. When `schmidt serve` detects a live simulation (via `stream.json`), it proxies the simulation's SSE stream — including token-by-token text deltas from the LLM streaming API — to connected frontends. The frontend shows text appearing character-by-character as agents generate responses. When the simulation ends, `stream.json` is deleted and the server falls back to JSONL tailing.

### API Type Safety

All frontend API calls use a typed client generated from the backend's OpenAPI schema. Raw `fetch()` is forbidden (enforced by ESLint). To regenerate types after changing backend endpoints:

```bash
make gen-api-types
```

## Scenarios

### Incident Response

Three agents (Engineer, Support Lead, PM) collaborate in a war room to diagnose and fix a production bug. The Engineer privately knows the root cause but is instructed to hide it. 6 rounds with escalating pressure. See the [scenario README](src/schmidt/scenarios/incident_response/README.md).

### Car Recall

Five agents (Engineer, Legal, CFO, PR, Regulator) decide whether to issue a vehicle recall. Each holds private facts that, combined, point to a full recall. 3–5 rounds with escalating pressure. Configurable knobs for time pressure, goal alignment, and more. See the [scenario README](src/schmidt/scenarios/car_recall/README.md).

### Product Launch

Six delegation-framed agents (PM, Backend Engineer, Frontend Engineer, Data Analyst, QA Lead, Product Designer) coordinate to ship a software product within a budget and timeline. Deliberate information asymmetry between agents. 8–12 rounds with configurable knobs. See the [scenario README](src/schmidt/scenarios/product_launch/README.md).

### Persuasion Debate

2+ agents discuss trivia questions with four evaluation modes from the PBT paper (Stengel-Eskin et al., 2025). Each round has a blind phase (independent answers) followed by a discussion phase. See the [scenario README](src/schmidt/scenarios/persuasion_debate/README.md).

## Project Structure

```
src/schmidt/
  cli.py                       # CLI: run, evaluate, serve
  autonomous_supervisor.py     # Round progression, event injection, resume
  channel_router.py            # Message storage + membership validation
  message_rewind.py            # State reconstruction at any message (fork/resume)
  message_history_builder.py   # Builds per-agent transcript history for fork/resume context
  event_logger.py              # JSONL event writer
  event_bus.py                 # In-process pub/sub for SSE streaming
  simulation_server.py         # Embedded SSE server per simulation

  runtime/                     # MCP server + coordination
    simulation_state.py        # Shared state: channels, sessions, locks
    mcp_tools.py               # MCP tool definitions (check_messages, read_channel, send_message)
    mcp_server.py              # FastMCP over Streamable HTTP
    game_clock.py              # Round progression, injection delivery, termination
    agent_session.py           # Per-agent notification queue, reaction delay, idle tracking

  runners/                     # Agent runner implementations
    pydantic_ai_runner.py      # Pydantic AI agent runner
    communication_protocol.py  # Shared prompts for agent communication

  models/                      # Pydantic data models
  llm/                         # LLM provider abstraction (used by evaluation)
  evaluation/                  # Post-hoc LLM-as-judge evaluators
  scenarios/                   # One folder per scenario (class + Jinja2 prompts + README)

  server/                      # FastAPI web server (schmidt serve)
    password_auth_middleware.py # Shared-password ASGI middleware
    fork_router.py             # POST /api/runs/{run_id}/fork endpoint

frontend/                      # Next.js web application
  src/features/auth/           # Login page and auth gate
```

See [Architecture.md](Architecture.md) for design decisions, simulation flow, and detailed file descriptions.

## Deployment

The application deploys to Railway as two services from a single repository. Each service has a `Dockerfile` and a `railway.toml` config-as-code file.

- **Backend** (`Dockerfile`, `railway.toml`): Python 3.12, FastAPI server with a persistent volume at `/data/runs` for simulation data.
- **Frontend** (`frontend/Dockerfile`, `frontend/railway.toml`): Node 22, Next.js standalone build.

Railway environment variables for the backend: `APP_PASSWORD`, `ANTHROPIC_API_KEY`, `ALLOWED_ORIGINS` (set to the frontend URL). The frontend requires `NEXT_PUBLIC_API_URL` as a build arg pointing to the backend URL.

## Linting

```bash
make lint              # runs both server and frontend linters
make lint-server       # server only (black, isort, ruff, mypy, pyright, vulture, custom linters)
make lint-frontend     # frontend only (prettier, eslint, stylelint, tsc)
make check-frontend    # frontend CI mode (prettier --check, no auto-fix)
```

### Vulture Dead Code Detection

Vulture runs at 60% confidence. False positives (Pydantic fields, FastAPI handlers, enum values, abstract methods) are suppressed via `vulture_whitelist.py`. To regenerate the whitelist after code changes:

```bash
VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 60 --make-whitelist 2>/dev/null | tee vulture_whitelist.py
```

Review the generated whitelist before committing — every entry should be a genuine false positive, not actual dead code.
