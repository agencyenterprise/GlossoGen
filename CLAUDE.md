# schmidt-poc

## Setup

```bash
make install
```

## Linting

```bash
make lint
```

## Project Structure

- `src/` — application source code
- `src/schmidt/scenarios/<scenario_name>/` — one folder per scenario, containing:
  - `README.md` — scenario documentation (agents, channels, tools, round injections, turn logic, evaluation focus)
  - `scenario.py` — scenario class definition (channels, turn logic, tools, injections)
  - `prompts/` — Jinja2 templates for all agent system prompts and injection messages
- `linter/` — custom linting scripts

### Prompt Templates

All prompts (agent system prompts, round injections) use Jinja2 templates stored in `prompts/` inside each scenario folder. Never hardcode prompt text in Python code.

## Code Design Principles

### API & Schema Design

- **Strict API schemas.** Never return raw dicts. Always define a Pydantic response model. Use enums for status-like fields.
- **Non-optional when always set.** If a field is always populated, declare it as required, not `Optional`.

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
- **Remove dead code aggressively.** Unused fields, stale imports, commented-out code — delete them.
- **Always use `logger.exception` in except blocks.** Every `except` clause that handles an error must call `logger.exception(...)` so the full stacktrace is visible in logs. Never silently swallow exceptions or use `logger.error` without the traceback.

### Docstrings

- **Every module needs a module-level docstring** describing what it defines (classes, protocols, functions).
- **Every public class and important function needs a docstring.**
- **Be factual only.** Describe what the code does, not assumptions about why. Never use subjective language like "makes things easier", "improves performance", "for convenience", "simplifies". State behavior, not benefits.
- **Be concise.** One to three sentences for most docstrings. Avoid restating type hints or parameter names that are already self-documenting.

## Running Simulations

Always run simulations as a background process, piping all output to a log file. This lets both the user and Claude monitor progress.

```bash
set -a && source .env && set +a && \
  VIRTUAL_ENV= uv run --no-sync python -m schmidt run <scenario> --model <model> --log-dir ./logs \
  > ./logs/<scenario>_stdout.log 2>&1 &
```

Check progress by reading the stdout log file or the JSONL event log.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
