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
  - `scenario.py` — scenario class (channels, timing, tools, injections, turn logic)
  - `prompts/` — Jinja2 templates for agent system prompts and injection messages
  - `evaluation/` — scenario-specific evaluators (optional)
- `src/schmidt/runtime/` — autonomous mode runtime (MCP server + coordination):
  - `simulation_state.py` — shared state: channels, sessions, locks, callbacks
  - `mcp_tools.py` — MCP tool definitions (check_messages, read_channel, send_message, etc.)
  - `mcp_server.py` — starts FastMCP over Streamable HTTP
  - `game_clock.py` — round progression, injection delivery, termination detection
  - `agent_session.py` — per-agent notification queue, reaction delay, idle tracking
  - `scenario_mcp_tool.py` — ScenarioMcpTool for scenario-specific tool registration
- `src/schmidt/runners/` — autonomous mode agent runners:
  - `agent_runner_base.py` — abstract base class for agent runners
  - `claude_code_runner.py` — Claude Code agent runner via Agent SDK
- `src/schmidt/autonomous_supervisor.py` — autonomous mode orchestrator
- `src/schmidt/simulation_hub.py` — orchestrated mode turn-based orchestrator
- `src/schmidt/agent_runner.py` — orchestrated mode per-agent turn execution
- `src/schmidt/llm/` — LLM provider abstraction + Anthropic/OpenAI/HuggingFace implementations
- `src/schmidt/tools/` — orchestrated mode tool registry, executor, stores (notebook, document), built-in tools
- `src/schmidt/evaluation/` — generic evaluators and evaluation infrastructure
- `src/schmidt/server/` — FastAPI web server exposing simulation data via REST and SSE streaming
- `linter/` — custom linting scripts
- `frontend/` — Next.js web application

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

## Development

```bash
make dev            # start FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # start Next.js dev server on port 3000
```

## Run Output Directory Structure

All simulation outputs use a standard directory layout:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl          # Event log (messages, reasoning, round transitions)
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines from Python logger, read by FE)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate)
└── {scenario_name}_stdout.log     # (pipe stdout here)
```

## Running Simulations

Two execution modes are available, selected via the `--mode` flag:

- **`autonomous`** — Agents run as independent Claude Code processes connected via MCP. A game clock manages round progression. No centralized turn control.
- **`orchestrated`** — A central hub assigns turns sequentially via direct LLM API calls. Supports multiple providers and checkpoint/resume.

Always run simulations as a background process, piping all output to a log file.

### Autonomous Mode

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
    --mode autonomous --model <model> --runs-dir ./runs \
    <scenario-specific flags> \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

Autonomous-mode flags: `--mcp-port` (default: 8001), `--max-agent-turns` (default: 200).

The `incident_response` scenario requires `--max-round-duration`:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --mode autonomous --model claude-sonnet-4-20250514 --runs-dir ./runs \
    --max-round-duration 120 \
  > ./runs/incident_response_stdout.log 2>&1 &
```

### Orchestrated Mode

Requires `--provider` to select the LLM backend.

The `--provider` flag selects which LLM backend to use. Set the corresponding API key in `.env`:
- `anthropic` — requires `ANTHROPIC_API_KEY`
- `openai` — requires `OPENAI_API_KEY`. Optionally use `--reasoning-effort` (low/medium/high) for reasoning models.
- `huggingface` — requires `HF_TOKEN`. Optionally use `--inference-provider` to route through a third-party backend.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --mode orchestrated --model claude-sonnet-4-20250514 --provider anthropic --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &
```

The `car_recall` scenario uses a `--knobs` flag:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run car_recall \
    --mode orchestrated --model <model> --provider <provider> --runs-dir ./runs \
    --knobs src/schmidt/scenarios/car_recall/knobs_baseline.json \
  > ./runs/car_recall_stdout.log 2>&1 &
```

The `product_launch` scenario also uses `--knobs`:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run product_launch \
    --mode orchestrated --model <model> --provider <provider> --runs-dir ./runs \
    --knobs src/schmidt/scenarios/product_launch/knobs_baseline.json \
  > ./runs/product_launch_stdout.log 2>&1 &
```

Check progress by reading the stdout log file or the JSONL event log.

### IMPORTANT: Monitoring Long-Running Processes

When running simulations, evaluations, or any long-running background process, **always** follow this pattern:

1. Launch the process in the background (with `run_in_background` or `&`)
2. Immediately after launch, `sleep 30` then check the log file for progress
3. Report a brief status update to the user
4. Repeat: `sleep 30`, check, report — until the process completes
5. Never use `while` loops or polling constructs — use sequential sleep/check/report cycles

## Running Evaluations

After a simulation completes, score the log with LLM-as-judge evaluators. Evaluation uses `--provider` to select the LLM judge.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate <scenario> \
    --run-dir ./runs/<scenario>/<timestamp> \
    --evaluators <comma-separated evaluator names> \
    --model <model> --provider <provider> \
  > ./runs/<scenario>/<timestamp>/eval_stdout.log 2>&1 &
```

Available evaluators per scenario:

Generic evaluators (available to all): `secret_leak`, `instruction_adherence`, `cooperation`, `communication_pattern`

- **incident_response**: generic evaluators only
- **car_recall**: generic + `fact_surfacing`, `report_divergence`, `decision_correctness`
- **product_launch**: generic + `launch_outcome`, `emergent_behavior`, `information_integrity`, `coordination_efficiency`, `conflict_resolution`, `report_accuracy`
- **persuasion_debate**: generic + `persuasion_accuracy`, `persuasion_dynamics`

## Destructive Actions

**Always ask the user before deleting or stopping anything.** This includes:
- Deleting run directories, log files, or any simulation output
- Killing running processes (simulations, servers, etc.)
- Removing files, branches, or data of any kind

Never assume cleanup is wanted. Ask first, act second.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
