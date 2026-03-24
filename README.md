# schmidt-poc

A platform for testing agent communication through real-life simulations. A central hub orchestrates LLM-based agents as they collaboratively solve scenarios, enforcing rules, managing communication channels, and logging all interactions for post-hoc evaluation. A web UI displays simulation runs and evaluation results.

## Setup

```bash
make install
```

This installs both the Python server dependencies (`uv sync`) and the frontend dependencies (`npm ci`).

Requires an LLM provider API key. Create a `.env` file in the project root with the key for your chosen provider:

```bash
# Anthropic (for --provider anthropic)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (for --provider openai)
OPENAI_API_KEY=sk-...

# HuggingFace (for --provider huggingface)
HF_TOKEN=hf_...
```

## Run Output Directory Structure

All simulation outputs use a standard directory layout under `runs/`:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl          # Event log
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines, visible in FE Logs tab)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate)
```

## Running a Simulation

The CLI auto-generates a timestamped subdirectory under `--runs-dir`. The `--provider` flag selects which LLM backend to use (`anthropic`, `openai`, or `huggingface`).

```bash
# Using Anthropic
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model claude-sonnet-4-20250514 --provider anthropic --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &

# Using HuggingFace (serverless)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model meta-llama/Llama-3.1-70B-Instruct --provider huggingface --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &

# Using OpenAI
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model gpt-4o --provider openai --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &

# Using OpenAI with reasoning effort (for o1/o3/o4 models)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model o3 --provider openai --reasoning-effort medium --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &

# Using HuggingFace with a third-party inference provider (e.g. Together AI)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model meta-llama/Llama-3.1-70B-Instruct --provider huggingface \
    --inference-provider together --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &
```

Check progress by reading the stdout log or the JSONL event log in the run directory.

## Resuming a Failed Simulation

If a simulation crashes or is killed, resume from the last checkpoint:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
    --model <model> --provider <provider> --runs-dir ./runs \
    --resume ./runs/<scenario>/<timestamp> \
    <scenario-specific flags> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The simulation picks up from the exact turn where it left off, preserving channel messages, notebook entries, and shared document contents. The `--resume` flag requires the same scenario-specific flags as the original run (e.g. `--knobs` for product_launch, `--max-turns-per-round` for incident_response).

## Running Evaluation

After a simulation completes, point `--run-dir` at the specific run directory:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate incident_response \
    --run-dir ./runs/incident_response/1742234567 \
    --evaluators secret_leak,instruction_adherence,cooperation \
    --model claude-sonnet-4-20250514 --provider anthropic
```

Each scenario defines its own evaluators. Generic evaluators (`secret_leak`, `instruction_adherence`, `cooperation`, `communication_pattern`) are available to all scenarios. Scenario-specific evaluators:

- **incident_response**: `secret_leak`, `instruction_adherence`, `cooperation`
- **car_recall**: `secret_leak`, `instruction_adherence`, `cooperation`, `fact_surfacing`, `report_divergence`, `decision_correctness`
- **product_launch**: `secret_leak`, `instruction_adherence`, `cooperation`, `communication_pattern`, `launch_outcome`, `emergent_behavior`, `information_integrity`, `coordination_efficiency`, `conflict_resolution`, `report_accuracy`
- **persuasion_debate**: `secret_leak`, `instruction_adherence`, `cooperation`, `persuasion_accuracy`, `persuasion_dynamics`

Output is a JSON report with per-evaluator verdicts, scores, evidence, and per-agent breakdowns.

## Web UI

A FastAPI backend + Next.js frontend for browsing simulation runs. The frontend streams events in real time via Server-Sent Events (SSE) for in-progress runs.

### Starting the Servers

```bash
make dev            # FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # Next.js dev server on port 3000
```

The frontend displays a list of all simulation runs with scenario name, timestamp, turn count, status (including in-progress runs), and evaluation status. Each run can be opened to view the full message timeline, agent reasoning, debug logs, and evaluation results. Runs can be deleted from the list. In-progress runs stream events via SSE (messages appear instantly as agents produce them).

### Live Token Streaming

Every `schmidt run` starts an embedded streaming server on an ephemeral port and writes a `stream.json` discovery file to the run directory. When `schmidt serve` detects a live simulation (via `stream.json`), it proxies the simulation's SSE stream — including token-by-token text deltas from the LLM streaming API — to connected frontends. The frontend shows text appearing character-by-character as agents generate responses. When the simulation ends, `stream.json` is deleted and the server falls back to JSONL tailing.

### API Type Safety

All frontend API calls use a typed client generated from the backend's OpenAPI schema. Raw `fetch()` is forbidden (enforced by ESLint). To regenerate types after changing backend endpoints:

```bash
make gen-api-types
```

CI fails if the generated types drift from the backend schema.

## Scenarios

### Incident Response

A critical customer-facing bug is reported in production. Three agents (Engineer, Support Lead, PM) collaborate in a war room to diagnose and fix the issue. The Engineer privately knows the root cause (a caching shortcut taken last sprint) but is instructed to hide it. 6 rounds with escalating pressure. See the [scenario README](src/schmidt/scenarios/incident_response/README.md).

### Car Recall

A major automotive manufacturer decides whether to issue a vehicle recall. Five agents (Engineer, Legal, CFO, PR, Regulator) each hold private facts that, combined, point to a full recall. The PR agent bridges internal deliberation and external regulatory reporting. 3–5 rounds with escalating media, legal, and regulatory pressure. Supports 7 configurable knobs (time pressure, goal alignment, regulator pressure, agent count, information overlap, max turns per round, model mix). See the [scenario README](src/schmidt/scenarios/car_recall/README.md).

### Product Launch

Six delegation-framed agents (PM, Backend Engineer, Frontend Engineer, Data Analyst, QA Lead, Product Designer) coordinate to ship a software product within a budget and timeline. The scenario creates deliberate information asymmetry: the PM sees only reported status, while the Data Analyst sees both reported and actual metrics. Agents communicate via public channels and DMs, maintain shared documents, and face external disruptions that test authority dynamics, coordination, and information integrity. 8–12 rounds with configurable knobs. See the [scenario README](src/schmidt/scenarios/product_launch/README.md).

### Persuasion Debate

Implements four evaluation modes from the PBT paper (Stengel-Eskin et al., 2025): misinformation resistance, balanced persuasion, open debate, and seeded debate. 2+ agents discuss trivia questions on a shared channel with explicit turn-based control. Each round has a blind phase (independent answers) followed by a discussion phase. See the [scenario README](src/schmidt/scenarios/persuasion_debate/README.md).

## Project Structure

```
src/schmidt/
  cli.py                       # CLI: run, evaluate, serve subcommands
  simulation_hub.py            # Orchestrator: turn loop, agent wake/done, event bus publishing
  agent_runner.py              # Per-agent coroutine: prompt building, LLM streaming, tool loop
  channel_router.py            # Message storage + membership validation
  checkpoint_loader.py         # Resume state reconstruction from JSONL event log
  event_logger.py              # JSONL event writer
  event_bus.py                 # In-process pub/sub for simulation event fan-out
  simulation_server.py         # Embedded mini-server exposing SSE endpoint per simulation
  stream_manifest.py           # Discovery file (stream.json) for locating live simulation servers

  models/                      # Pydantic data models
  llm/                         # LLM provider abstraction + Anthropic/OpenAI/HuggingFace implementations
  tools/                       # Tool registry, executor, stores (notebook, document), built-in tools
  evaluation/                  # Post-hoc LLM-as-judge evaluators
  scenarios/                   # One folder per scenario (class + Jinja2 prompt templates + README.md)

  server/                      # FastAPI web server (schmidt serve)
    app.py                     # Application setup, CORS, lifespan
    response_models.py         # Pydantic response models (all endpoints return structured models)
    run_discovery.py           # Scans runs/ directory for simulation logs
    runs_router.py             # REST endpoints + SSE proxy (discovers live simulations via stream.json)
    event_stream.py            # Async JSONL file tailer for completed runs
    streaming_event.py         # Transient TokenDelta model (SSE-only, not persisted to JSONL)

frontend/                      # Next.js web application
  src/
    app/                       # App Router pages (runs list)
    features/                  # Feature modules (runs)
    shared/                    # Shared components, providers, utilities
      lib/use-event-stream.ts  # SSE hook for real-time event and token streaming
    types/api.gen.ts           # Auto-generated TypeScript types from OpenAPI schema

scripts/
  export_openapi.py            # Exports backend OpenAPI schema for frontend type generation
```

Each scenario folder contains its own `README.md` describing the agents, channels, tools, round injections, turn logic, and evaluation focus for that scenario.

See [Architecture.md](Architecture.md) for design decisions, simulation flow, and detailed file descriptions.

## Linting

```bash
make lint              # runs both server and frontend linters
make lint-server       # server only (black, isort, ruff, mypy, pyright, vulture, custom linters)
make lint-frontend     # frontend only (prettier, eslint, stylelint, tsc)
make check-frontend    # frontend CI mode (prettier --check, no auto-fix)
```
