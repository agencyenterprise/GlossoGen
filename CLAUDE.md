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
- `src/schmidt/scenario_protocol.py` — `SimulationScenario` ABC that every scenario implements
- `src/schmidt/simulation_state_protocol.py` — `SimulationStateProtocol` for stateful scenarios with mutable world state
- `src/schmidt/simulation_hub.py` — orchestrator that runs the turn loop, handles round transitions, and registers built-in tools
- `src/schmidt/agent_runner.py` — per-agent coroutine lifecycle (LLM calls, tool execution, reasoning capture)
- `src/schmidt/channel_generation.py` — `generate_dm_channels()` utility for auto-generating pairwise DM channels
- `src/schmidt/tools/` — tool system (registry, executor, built-in tools)
  - `builtin_send_message.py` / `builtin_pass_turn.py` — core tools every agent gets
  - `builtin_notebook.py` — private per-agent notebook (`write_notebook`, `read_notebook`)
  - `builtin_shared_documents.py` — shared document workspace (`list_documents`, `read_document`, `write_document`)
  - `stateful_tool.py` — `StatefulToolExecutor` helper for scenario tools that mutate world state
- `src/schmidt/scenarios/<scenario_name>/` — one folder per scenario, containing:
  - `README.md` — scenario documentation (agents, channels, tools, round injections, turn logic, evaluation focus)
  - `scenario.py` — scenario class definition (channels, turn logic, tools, injections)
  - `prompts/` — Jinja2 templates for all agent system prompts and injection messages
  - `evaluation/` — scenario-specific evaluators (optional)
- `src/schmidt/evaluation/` — generic evaluators and evaluation infrastructure
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
├── {scenario_name}.jsonl          # Event log
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines from Python logger, read by FE)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate)
└── {scenario_name}_stdout.log     # (pipe stdout here)
```

## Running Simulations

Always run simulations as a background process, piping all output to a log file. This lets both the user and Claude monitor progress. The CLI auto-generates a timestamped subdirectory under `--runs-dir`.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> --model <model> --runs-dir ./runs \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

The `incident_response` scenario requires a `--max-turns-per-round` flag:

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run incident_response \
    --model <model> --runs-dir ./runs \
    --max-turns-per-round 10 \
  > ./runs/incident_response_stdout.log 2>&1 &
```

The `car_recall` scenario registers its own `--knobs` flag pointing to a JSON file with scenario configuration (includes `max_turns_per_round`). Two presets are provided in `src/schmidt/scenarios/car_recall/`:

- `knobs_baseline.json` — 5 agents, 5 rounds, 10 turns per round, all knobs set to low
- `knobs_high_pressure.json` — 5 agents, 3 rounds, 10 turns per round, high time/goal/regulator pressure

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run car_recall \
    --model <model> --runs-dir ./runs \
    --knobs src/schmidt/scenarios/car_recall/knobs_baseline.json \
  > ./runs/car_recall_stdout.log 2>&1 &
```

The `product_launch` scenario also uses `--knobs`. Two presets are provided in `src/schmidt/scenarios/product_launch/`:

- `knobs_baseline.json` — 6 agents, 8 features, 12 rounds, 10 turns per round, 15% budget deficit, medium events
- `knobs_high_pressure.json` — 6 agents, 10 features, 8 rounds, 10 turns per round, 25% budget deficit, high event intensity

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run product_launch \
    --model <model> --runs-dir ./runs \
    --knobs src/schmidt/scenarios/product_launch/knobs_baseline.json \
  > ./runs/product_launch_stdout.log 2>&1 &
```

Check progress by reading the stdout log file or the JSONL event log.

### Resuming Failed Simulations

If a simulation errors midway through, resume from the last checkpoint using the `--resume` flag pointing at the existing run directory. The simulation will pick up from the exact turn where it left off, preserving all channel messages, notebook entries, and shared document contents.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> \
    --model <model> --runs-dir ./runs \
    --resume ./runs/<scenario>/<timestamp> \
    <scenario-specific flags like --knobs or --max-turns-per-round> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The `--resume` flag requires the same scenario-specific flags as the original run (e.g. `--knobs` for car_recall/product_launch, `--max-turns-per-round` for incident_response). The `--runs-dir` flag is still required but ignored when resuming.

### IMPORTANT: Monitoring Long-Running Processes

When running simulations, evaluations, or any long-running background process, **always** follow this pattern:

1. Launch the process in the background (with `run_in_background` or `&`)
2. Immediately after launch, `sleep 30` then check the log file for progress (grep for turn count, last line, or completion marker)
3. Report a brief status update to the user (e.g. "Turn 8/14, Round 2")
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

Generic evaluators (available to all scenarios): `secret_leak`, `instruction_adherence`, `cooperation`, `communication_pattern`, `report_accuracy`

- **incident_response**: generic evaluators
- **car_recall**: generic evaluators + `fact_surfacing`, `report_divergence`, `decision_correctness`
- **product_launch**: generic evaluators + `launch_outcome`, `emergent_behavior`

## Destructive Actions

**Always ask the user before deleting or stopping anything.** This includes:
- Deleting run directories, log files, or any simulation output
- Killing running processes (simulations, servers, etc.)
- Removing files, branches, or data of any kind

Never assume cleanup is wanted. Ask first, act second.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
