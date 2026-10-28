# glossogen

## Setup

```bash
make install           # installs both server (uv sync) and frontend (npm ci)
make install-server    # server only
make install-frontend  # frontend only
```

## Linting

```bash
make lint              # runs both server and frontend linters
make lint-server       # server only (black, isort, ruff, pyright, vulture, custom linters)
make lint-frontend     # frontend only (prettier --write, eslint, stylelint, tsc)
make check-frontend    # frontend CI mode (prettier --check, no auto-fix)
```

## Where things are

[Architecture.md](Architecture.md) describes the runtime, the scenario contract, run storage, the derivation flows and the web server. Each module's docstring describes what it holds.

- `src/glossogen/scenarios/<name>/` — one folder per scenario. Adding one: [docs/creating-a-scenario.md](docs/creating-a-scenario.md)
- `src/glossogen/scenario_protocol.py` / `scenario_base.py` — the scenario contract. `scenario_registry.py` lists built-in scenarios; `scenario_loader.py` is the only way a scenario name is resolved
- `src/glossogen/runtime/` — shared simulation state, the channel router, the game clock, communication tools, `read_notifications` waits
- `src/glossogen/runners/` — pydantic-ai agent runners and per-provider model construction
- `src/glossogen/run_config/` — building a run's config before launch: resolving `--config`/`--knobs` presets and `key=value` overrides into it, and validating it
- `src/glossogen/run_derivation/` — replace-agent, cross-run replace-agent and fork-at-round
- `src/glossogen/run_replay/` — rebuilding agent histories and simulation state from a run's event log, for `--resume`, forks, swaps and exports
- `src/glossogen/evaluation/` — the `Metric` contract (`metric_core/`), reports, generic metrics. Adding one: [docs/creating-a-metric.md](docs/creating-a-metric.md)
- `src/glossogen/run_export/` / `run_analysis/` / `dashboards/` — multi-run CSV export, grouped analysis, saved dashboards. No FastAPI imports. See [docs/exporting-runs.md](docs/exporting-runs.md), [docs/analysis.md](docs/analysis.md)
- `src/glossogen/server/` — FastAPI app: identity middleware, routers, the MCP server
- `src/glossogen/db/` — Postgres layer (raw SQL, psycopg3 async, alembic migrations)
- `src/glossogen/cli/` — one module per subcommand, each with `add_<command>_parser` beside `handle_<command>`
- `frontend/` — Next.js app; `src/features/` per surface, scenario plug-ins in `src/features/runs/`
- `modal/` — self-hosted vLLM endpoints; see `modal/README.md`

### Invariants spread across modules

- **Missing is not zero.** A metric with no measurement renders `""` in a CSV and `None` in analysis, never `0`. A present measurement renders its score, `0.0` included. A metric that does not apply returns `[]`, not a zero-score `Measurement`.
- Build a run directory's scenario-named file paths through `run_file_paths.py`, never with an f-string.
- Read `labels.json` only through `run_labels_file.py`.
- Resolve a scenario name only through `scenario_loader.py`.
- Metrics and the helpers they import type against `ScenarioBase`, not `SimulationScenario`.
- No platform module names a scenario's metrics or extension; a scenario declares them through `scenario_metrics()` / `run_detail_extension()`. A metric meaningful for one scenario lives in that scenario's `evaluation/`.
- Prompts (agent system prompts, injections) are Jinja2 templates in the scenario's `prompts/`. Never hardcode prompt text in Python.
- `run_export/` and `run_analysis/` name no scenario and no metric; columns come from each run's recorded config and report.

## Running simulations and evaluations

How to configure, resume, swap, fork and evaluate: [docs/running-simulations.md](docs/running-simulations.md), [docs/agent-swaps.md](docs/agent-swaps.md), [docs/evaluation.md](docs/evaluation.md). Launching a sweep of many runs: [docs/running-simulations.md#running-many-simulations](docs/running-simulations.md#running-many-simulations).

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --config <preset-name> [key=value overrides...] \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

- **Canonical seed: `seed=42`**, unchanged across replications, unless the user asks otherwise.
- **Canonical judge: `claude-haiku-4-5-20251001`** on `anthropic` in every knobs file, unless the user asks otherwise.
- **A run is finished only when its JSONL has `simulation_ended`.** Never gate evaluation on a `round_advanced` count: round N's advance fires when it starts, so the evaluation misses round N.
- **Labels:** `labels.json` is a JSON list and the PUT replaces it. Parse it with `json`, never substring-match it; read, modify and write back rather than overwrite; scope a bulk edit by run identity, not by current labels; dry-run and confirm when unsure.

### Watching runs you launched

Runs cost money. While any run you launched is live:

- **No foreground `sleep`.** Launch in the background and arm a background heartbeat (a loop that echoes every 30–60s). Do the real check yourself on each tick. Never gate a wake-up on one grep condition you have not verified against real output: if it never matches, you never wake.
- Check every 1–2 minutes, and never set a wake-up longer than about 10 minutes. On each check: tail the launcher log for `WARN`, `ERROR`, `Traceback` or an empty `new_run_id=`; count live sims per model with `pgrep -f "Python -m glossogen run <scenario> --model <model>"` (capital `Python`, so the check's own shell does not match); confirm `round_advanced` is still climbing; audit each new run's labels, source and model against the plan, since duplicate launches are the costliest mistake.
- Cap concurrent sims at 15 per model, with one launch queue per provider so a full queue on one never idles the other.
- When overriding a knob, also override the knobs its validators check against it. A rejected config exits before claiming a run directory, so a launcher polling for one loses the spec silently.

## Further reading

| Topic | Where |
|---|---|
| Environment variables | `.env.example`, [docs/installation.md](docs/installation.md#configure-environment) |
| Local Langfuse tracing | [docs/observability.md](docs/observability.md) |
| Authentication, identity providers | [Architecture.md](Architecture.md#multi-tenancy--authentication), [docs/deployment.md](docs/deployment.md#authentication), [docs/creating-an-identity-provider.md](docs/creating-an-identity-provider.md) |
| MCP server and OAuth | [docs/mcp-integration.md](docs/mcp-integration.md), [Architecture.md](Architecture.md#mcp-runs-browser) |
| Scenario hooks the metrics read | [docs/creating-a-scenario.md](docs/creating-a-scenario.md), [docs/creating-a-metric.md](docs/creating-a-metric.md#scenario-hooks) |
| Run directory layout | [Architecture.md](Architecture.md#run-storage) |
| Labels and the label glossary | [docs/web-ui.md](docs/web-ui.md#run-labels) |
| Deployment | [docs/deployment.md](docs/deployment.md) |

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

### Tests and time

**No test may depend on wall-clock time.** No `sleep`, no waiting for a duration
to elapse, no assertion that rests on a timeout firing on its own. A test that
races real time passes on a quiet machine and fails under load, and the failure
reads as a bug in the code under test rather than in the test.

Monkeypatching a duration to a small number is not a fix. It narrows the race
without removing it, and the smaller the number the tighter the race gets
against scheduling jitter.

Where the platform uses time as a proxy for a question, the test answers the
question directly instead. The game clock waits `MIN_ROUND_DURATION_SECONDS`
after the last message to guess whether the agents have finished; a test with
scripted agents knows when they have finished, because it wrote the scripts. If
the production path has no injection point for that, add one rather than tune
the wait.

A test that has to exercise a timeout drives the clock rather than waiting for
one: advancing time is an explicit statement in the test.

This was measured, not assumed. With that floor patched to 50ms,
`container_yard_stacking` dropped a message roughly one full-suite run in six
under `-n auto`, which changed what its world announced and broke a recorded
baseline. Nothing about the scenario or the platform was wrong; the test was
racing.

### Tests and files the repo ships

**No test may write to a file the repo ships**, even if it restores it afterwards.
Test processes share one filesystem: under `-n auto` the restore protects the test
that made the edit and nothing else, so any test reading that file inside the
window sees the edit and reports the thing it read as broken.

Break a copy instead. Copy the package to `tmp_path`, edit the copy, and point the
code under test at it: `monkeypatch.setattr(scenario_cls,
"scenario_package_files", classmethod(...))`. Copy the whole package rather than
the one file, because the other checks read from that directory too.

This was measured, not assumed. `test_an_events_module_importing_the_event_union_is_reported`
prepended an import to `prisoners_dilemma/events.py` and restored it in a
`finally`. Roughly one full-suite run in eighteen, `validate prisoners_dilemma`
read the file mid-window and failed with `events.py imports from
glossogen.models.event at line 1`. Nothing was wrong with prisoners_dilemma; two
tests were racing on one file.

### Writing

This applies to every word committed here: docstrings, comments, markdown, commit
messages, PR descriptions.

Write like an engineer explaining something to the next engineer. The habits below
read as machine-written and are not wanted:

- **Em-dashes mid-sentence.** "The log is what everyone reads — so a thing that
  wasn't logged didn't happen." Use a comma, a colon, or two sentences. A dash
  introducing a definition in a list is fine and common here:
  `` - `src/` — application source code ``.
- **Announcing importance instead of stating fact.** "These are the tests that
  matter", "this is the whole point", "deliberately loud". Say what the thing
  does and let the reader judge.
- **Restating the heading** in the first sentence under it. Add information.
- **Inflated words**: leverage, harness, seamless, robust, powerful, unlock,
  streamline, empower, at scale, cutting-edge. Use the plain one.
- **"Not just X, it's Y"** and **rule-of-three lists** when three isn't the real
  count. State the point; say the true number.
- **Every sentence the same medium length.** Vary it. Some should be short.

Read it back before committing. If you would not say it out loud to a colleague,
rewrite it.

### Docstrings

- **Every module needs a module-level docstring** describing what it defines.
- **Every public class and important function needs a docstring.**
- **Be factual only.** Describe what the code does, not assumptions about why. Never use subjective language.
- **Be concise.** One to three sentences for most docstrings.
- **Never state a count of things that can change.** "Six scenarios build a judge",
  "the four probe metrics", "28 questions per agent". Every one of these becomes a
  lie the next time someone adds a scenario, a metric, or a question, and nothing
  fails when it does. Name the property instead: "scenarios that judge their own
  rounds", "the probe metrics", "the whole question bank". Counts that describe a
  fixed design ("three agents share one channel") are fine, because changing them
  means redesigning the thing being described.

## Frontend

Stack: Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4, TanStack React Query, openapi-fetch.

The installed Next.js is newer than most models' training data, and its APIs, conventions and file layout have changed. Before writing Next.js code, read the guide for what you are touching in `frontend/node_modules/next/dist/docs/`, which matches the installed version, and heed its deprecation notices. `next dev` would otherwise write this advice into an untracked `frontend/AGENTS.md`; `agentRules: false` in `next.config.ts` turns that off.

### API Client & Type Safety

All API calls must use the generated typed client from `@/shared/lib/api-client`. Raw `fetch()` is forbidden, enforced by ESLint.

To regenerate types after changing backend endpoints:

```bash
make gen-api-types
```

CI fails if `frontend/src/types/api.gen.ts` drifts from the backend schema.

## What `scripts/` is for

`scripts/` holds build tooling only:

- `export_openapi.py` — drives `make gen-api-types`; the `check-api-types` CI job depends on it
- `generate_demo_snapshot.py` — builds the frontend's `/demo` assets
- `measure_docs_style.py` — measures documentation pages against the bands in `docs/documentation-style.md`; part of the docs review, not a linter
- `docs_hooks.py` — mkdocs build hooks: adds the repository-root pages to the site and rewrites links that leave the docs tree into GitHub permalinks. Referenced from `mkdocs.yml`
- `consolidate_communication_ontology.py` — pass 2 of the communication pipeline, between the `communication_open_coding` and `communication_feature_presence` metrics
- `check_wheel_contents.py` — checks that a built wheel contains the expected package files; run by `make check-package`

Keep it that way. One-off experiment orchestration, cohort reruns, and label
surgery do not belong here. They operate on run output, and the evaluation
reports (`{scenario}_report.json`) plus the JSONL event logs are a stable enough
interface that such tooling can live wherever the experiment does.

Scenario-local helper scripts are the exception and live under
`src/glossogen/scenarios/<name>/scripts/`.

## Destructive Actions

**Always ask the user before deleting or stopping anything.** This includes:
- Deleting run directories, log files, or any simulation output
- Killing running processes (simulations, servers, etc.)
- Removing files, branches, or data of any kind

Never assume cleanup is wanted. Ask first, act second.

## Pre-Commit Checklist

1. Run `make lint` and fix all errors.
1b. If you touched a scenario, run `VIRTUAL_ENV= uv run --no-sync python -m glossogen validate <name>`. It builds every preset and checks the contract without launching anything. It also takes a directory, for a scenario package that is not installed.
2. Check for dead code: unused model fields, orphaned functions, stale imports. Remove them.
3. If vulture reports new false positives, regenerate the whitelist over the same paths `make lint-server` checks, or the regenerated file drops the entries covering the ones it left out: `VIRTUAL_ENV= uv run --no-sync vulture src/ scripts/ linter/ --min-confidence 60 --make-whitelist > vulture_whitelist.py`
