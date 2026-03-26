# schmidt-poc

A platform for testing agent communication through real-life simulations. LLM-based agents collaboratively solve scenarios while a central system manages communication channels, injects scenario events, and logs all interactions for post-hoc evaluation. A web UI displays simulation runs and evaluation results.

Two execution modes are supported:

- **Autonomous mode** — Each agent runs as an independent Claude Code process connected via MCP. Agents decide when to speak; a game clock manages round progression. No centralized turn control.
- **Orchestrated mode** — A central hub assigns turns sequentially via direct LLM API calls. Supports multiple LLM providers (Anthropic, OpenAI, HuggingFace) and checkpoint/resume.

## Setup

```bash
make install
```

This installs both the Python server dependencies (`uv sync`) and the frontend dependencies (`npm ci`).

Create a `.env` file in the project root with API keys for your chosen provider(s):

```bash
# Required for autonomous mode (always uses Claude Code)
ANTHROPIC_API_KEY=sk-ant-...

# Required for orchestrated mode with --provider openai
OPENAI_API_KEY=sk-...

# Required for orchestrated mode with --provider huggingface
HF_TOKEN=hf_...
```

## Running a Simulation

The `--mode` flag selects the execution mode. The CLI auto-generates a timestamped subdirectory under `--runs-dir`.

### Autonomous Mode

Agents run as independent Claude Code processes connected via MCP. Each round, agents communicate freely until all are idle or the round duration expires.

```bash
# Incident Response (autonomous)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --mode autonomous --model claude-sonnet-4-20250514 --runs-dir ./runs \
    --max-round-duration 120 \
  > ./runs/incident_response_stdout.log 2>&1 &

# Car Recall (autonomous)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run car_recall \
    --mode autonomous --model claude-sonnet-4-20250514 --runs-dir ./runs \
    --knobs src/schmidt/scenarios/car_recall/knobs_baseline.json \
  > ./runs/car_recall_stdout.log 2>&1 &
```

Autonomous-mode flags:
- `--mcp-port` — Port for the MCP server (default: 8001)
- `--max-agent-turns` — Maximum agentic turns per agent (default: 200)

### Orchestrated Mode

A central hub assigns turns using direct LLM API calls. Requires `--provider` to select the LLM backend.

```bash
# Incident Response (orchestrated, Anthropic)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --mode orchestrated --model claude-sonnet-4-20250514 --provider anthropic --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &

# Car Recall (orchestrated, OpenAI)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run car_recall \
    --mode orchestrated --model gpt-4o --provider openai --runs-dir ./runs \
    --knobs src/schmidt/scenarios/car_recall/knobs_baseline.json \
  > ./runs/car_recall_stdout.log 2>&1 &

# Product Launch (orchestrated, HuggingFace via Together)
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run product_launch \
    --mode orchestrated --model meta-llama/Llama-3.1-70B-Instruct \
    --provider huggingface --inference-provider together --runs-dir ./runs \
    --knobs src/schmidt/scenarios/product_launch/knobs_baseline.json \
  > ./runs/product_launch_stdout.log 2>&1 &
```

Orchestrated-mode flags:
- `--provider` — LLM provider (required): `anthropic`, `openai`, `huggingface`
- `--inference-provider` — HuggingFace inference backend (e.g. `together`, `fireworks-ai`, `cerebras`)
- `--reasoning-effort` — OpenAI reasoning models: `low`, `medium`, `high`
- `--resume` — Resume from an existing run directory after a crash

Check progress by reading the stdout log or the JSONL event log in the run directory.

### Resuming a Failed Simulation

If a simulation crashes or is killed, resume from the last checkpoint (orchestrated mode only):

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
    --mode orchestrated --model <model> --provider <provider> --runs-dir ./runs \
    --resume ./runs/<scenario>/<timestamp> \
    <scenario-specific flags> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The simulation picks up from the exact turn where it left off, preserving channel messages, notebook entries, and shared document contents. The `--resume` flag requires the same scenario-specific flags as the original run (e.g. `--knobs` for product_launch, `--max-turns-per-round` for incident_response).

## Run Output Directory Structure

All simulation outputs use a standard directory layout under `runs/`:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl          # Event log
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines, visible in FE Logs tab)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate)
```

## Running Evaluation

After a simulation completes, point `--run-dir` at the specific run directory. Evaluation uses `--provider` to select the LLM judge.

```bash
set -a && source .env && set +a && \
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

### Starting the Servers

```bash
make dev            # FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # Next.js dev server on port 3000
```

The frontend displays a list of all simulation runs with scenario name, timestamp, message count, status (including in-progress runs), and evaluation status. Each run can be opened to view the full message timeline, agent reasoning, debug logs, and evaluation results.

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
  cli.py                       # CLI: run (autonomous/orchestrated), evaluate, serve
  autonomous_supervisor.py     # Autonomous mode: round progression, event injection
  simulation_hub.py            # Orchestrated mode: turn-based orchestrator
  agent_runner.py              # Orchestrated mode: per-agent turn execution
  channel_router.py            # Message storage + membership validation
  checkpoint_loader.py         # Resume state reconstruction from JSONL event log
  event_logger.py              # JSONL event writer
  event_bus.py                 # In-process pub/sub for SSE streaming
  simulation_server.py         # Embedded SSE server per simulation

  runtime/                     # Autonomous mode: MCP server + coordination
    simulation_state.py        # Shared state: channels, sessions, locks
    mcp_tools.py               # MCP tool definitions (check_messages, read_channel, send_message)
    mcp_server.py              # FastMCP over Streamable HTTP
    game_clock.py              # Round progression, injection delivery, termination
    agent_session.py           # Per-agent notification queue, reaction delay, idle tracking

  runners/                     # Autonomous mode: agent runner implementations
    claude_code_runner.py      # Claude Code via Agent SDK

  models/                      # Pydantic data models
  llm/                         # LLM provider abstraction + Anthropic/OpenAI/HuggingFace
  tools/                       # Tool registry, executor, stores (notebook, document), built-in tools
  evaluation/                  # Post-hoc LLM-as-judge evaluators
  scenarios/                   # One folder per scenario (class + Jinja2 prompts + README)

  server/                      # FastAPI web server (schmidt serve)

frontend/                      # Next.js web application
```

See [Architecture.md](Architecture.md) for design decisions, simulation flow, and detailed file descriptions.

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
