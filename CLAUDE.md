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
  - `README.md` — scenario documentation (agents, channels, tools, round injections, agent coordination, evaluation focus)
  - `scenario.py` — scenario class definition (channels, timing config, tools, injections)
  - `prompts/` — Jinja2 templates for all agent system prompts and injection messages
- `src/schmidt/runtime/` — simulation runtime (MCP server + coordination):
  - `simulation_state.py` — shared state: channels, sessions, locks, callbacks
  - `mcp_tools.py` — MCP tool definitions (check_messages, read_channel, send_message, etc.)
  - `mcp_server.py` — starts FastMCP over Streamable HTTP as an asyncio task
  - `game_clock.py` — round progression, injection delivery, termination detection
  - `agent_session.py` — per-agent notification queue, reaction delay, idle tracking
  - `activity_notification.py` — notification types (NewMessages, NewInfo, Done)
  - `scenario_mcp_tool.py` — ScenarioMcpTool NamedTuple for scenario-specific tool registration
- `src/schmidt/runners/` — agent runner implementations:
  - `agent_runner_base.py` — abstract base class defining the interface for agent runners
  - `claude_code_runner.py` — runner that executes agents via Claude Code with MCP tools; captures agent reasoning text (`TextBlock`) and emits `LLMResponseReceived` events to the event log
- `src/schmidt/template_renderer.py` — shared Jinja2 `TemplateRenderer` used by scenarios and evaluators
- `src/schmidt/autonomous_supervisor.py` — monitors agent activity and triggers round advancement
- `src/schmidt/server/` — FastAPI web server exposing simulation data via REST
- `linter/` — custom linting scripts
- `frontend/` — Next.js web application
  - `frontend/src/app/` — Next.js App Router pages
  - `frontend/src/features/` — feature-based modules (runs, etc.)
  - `frontend/src/shared/` — shared components, hooks, providers, and utilities
  - `frontend/src/types/api.gen.ts` — auto-generated TypeScript types from the backend OpenAPI schema

### Prompt Templates

All prompts (agent system prompts, round injections) use Jinja2 templates stored in `prompts/` inside each scenario folder. Never hardcode prompt text in Python code.

## Code Design Principles

### API & Schema Design

- **Strict API schemas.** Never return raw dicts. Always define a Pydantic response model. Use enums for status-like fields.
- **Non-optional when always set.** If a field is always populated, declare it as required, not `Optional`.
- **Web server responses must be structured Pydantic models.** Every FastAPI endpoint must declare a `response_model` and return an instance of that model. Never return plain dicts, strings, or untyped JSON. Use enums instead of bare strings for any field with a fixed set of values (status codes, categories, verdicts, etc.).

### File & Module Organization

- **No generic file names.** Never name a file `services.py`, `utils.py`, `helpers.py`, or `common.py`. The file name must describe its content.
- **Same for classes and functions.** `BaseHelper`, `CommonUtils`, `MiscOperations` are red flags. Name things after what they do.

### Python Style

- **Always use named arguments** when calling functions.
- **Never return dicts from functions.** When returning multiple values, use a `NamedTuple` or Pydantic model.
- **No default parameter values.** All callers must pass all arguments explicitly. Refactor callers instead of adding defaults.
- **Prefer async.** When both sync and async options exist (database, HTTP, file I/O), use the async variant.
- **No `TYPE_CHECKING` or `from __future__ import annotations`.** Use direct imports. If there's a circular import, fix the cycle by restructuring.
- **No string type annotations.** Never use quotes around type hints (e.g., `"asyncio.Queue[X]"`). All types must be referenced directly.
- **No inline ternary expressions.** Use `if`/`else` blocks instead of `x if condition else y`.
- **Remove dead code aggressively.** Unused fields, stale imports, commented-out code — delete them.
- **Always use `logger.exception` in except blocks.** Every `except` clause that handles an error must call `logger.exception(...)` so the full stacktrace is visible in logs. Never silently swallow exceptions or use `logger.error` without the traceback.

### LLM Output Parsing

- **Always use output schemas to enforce structured LLM responses.** Never parse free text from LLM responses. Define a Pydantic model for the desired output shape, pass it to `generate_structured()`, and use the validated instance directly. Each caller defines its own output model tailored to its specific semantics.

### Docstrings

- **Every module needs a module-level docstring** describing what it defines (classes, protocols, functions).
- **Every public class and important function needs a docstring.**
- **Be factual only.** Describe what the code does, not assumptions about why. Never use subjective language like "makes things easier", "improves performance", "for convenience", "simplifies". State behavior, not benefits.
- **Be concise.** One to three sentences for most docstrings. Avoid restating type hints or parameter names that are already self-documenting.

## Frontend

Stack: Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4, TanStack React Query, openapi-fetch.

### API Client & Type Safety

All API calls must use the generated typed client from `@/shared/lib/api-client`. Raw `fetch()` is forbidden — this is enforced by an ESLint rule. The typed client provides compile-time validation of request paths, parameters, and response types.

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

### Agent Reasoning in the Event Log

The JSONL event log contains `llm_response_received` events with agent reasoning text — the text the agent produces between tool calls. The `ClaudeCodeRunner` captures `TextBlock` content from `AssistantMessage` responses and emits these as events. The frontend displays reasoning entries inline in the chat timeline with reduced opacity and a "reasoning" label.

## Running Simulations

Always run simulations as a background process, piping all output to a log file. This lets both the user and Claude monitor progress. The CLI auto-generates a timestamped subdirectory under `--runs-dir`.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> --model <model> --runs-dir ./runs \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

The `incident_response` scenario requires a `--max-round-duration` flag:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model <model> --runs-dir ./runs \
    --max-round-duration 300 \
  > ./runs/incident_response_stdout.log 2>&1 &
```

The `car_recall` scenario requires a `--knobs` flag pointing to a JSON file with scenario configuration. Two presets are provided in `src/schmidt/scenarios/car_recall/`:

- `knobs_baseline.json` — 5 agents, 5 rounds, all knobs set to low
- `knobs_high_pressure.json` — 5 agents, 3 rounds, high time/goal/regulator pressure

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run car_recall \
    --model <model> --runs-dir ./runs \
    --knobs src/schmidt/scenarios/car_recall/knobs_baseline.json \
  > ./runs/car_recall_stdout.log 2>&1 &
```

Check progress by reading the stdout log file or the JSONL event log.

### IMPORTANT: Monitoring Long-Running Processes

When running simulations, evaluations, or any long-running background process, **always** follow this pattern:

1. Launch the process in the background (with `run_in_background` or `&`)
2. Immediately after launch, `sleep 30` then check the log file for progress (grep for round number, last line, or completion marker)
3. Report a brief status update to the user (e.g. "Round 3/6, agents active")
4. Repeat: `sleep 30`, check, report — until the process completes
5. Never use `while` loops or polling constructs — use sequential sleep/check/report cycles so the user sees updates between checks

## Running Evaluations

After a simulation completes, score the log with LLM-as-judge evaluators. Point `--run-dir` at the specific run directory. Run as a background process like simulations.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate <scenario> \
    --run-dir ./runs/<scenario>/<timestamp> \
    --evaluators <comma-separated evaluator names> \
    --model <model> \
  > ./runs/<scenario>/<timestamp>/eval_stdout.log 2>&1 &
```

Available evaluators per scenario:

- **incident_response**: `secret_leak`, `instruction_adherence`, `cooperation`
- **car_recall**: `secret_leak`, `instruction_adherence`, `cooperation`, `fact_surfacing`, `report_divergence`, `decision_correctness`

## Destructive Actions

**Always ask the user before deleting or stopping anything.** This includes:
- Deleting run directories, log files, or any simulation output
- Killing running processes (simulations, servers, etc.)
- Removing files, branches, or data of any kind

Never assume cleanup is wanted. Ask first, act second.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
