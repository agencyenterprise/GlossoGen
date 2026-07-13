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

## Project Structure

- For a step-by-step guide on adding a new scenario, see [docs/creating-a-scenario.md](docs/creating-a-scenario.md).
- `src/` — application source code
- `src/glossogen/scenarios/<scenario_name>/` — one folder per scenario, containing:
  - `README.md` — scenario documentation
  - `scenario.py` — scenario class (channels, timing, tools, injections, turn logic, knobs schema)
  - `prompts/` — Jinja2 templates for agent system prompts and injection messages
  - `evaluation/` — scenario-specific metrics (optional)
  - `events.py` — scenario-specific `EventBase` subclasses (auto-discovered)
  - `run_detail_extension.py` — optional hook for surfacing scenario-specific data on the run-detail API
  - `scripts/` — one-off scripts that import directly from this scenario (smoke runners, probe-bank generators, etc.). Cross-scenario tools live in the repo-root `scripts/` instead.
- `src/glossogen/runtime/` — autonomous mode runtime (MCP server + coordination):
  - `simulation_state.py` — shared state: channels, sessions, locks, callbacks, world context, token counters, current round, injection delivery (`deliver_round_injections`, `deliver_postmortem_injections`, `has_postmortem_for_round`)
  - `mcp_tools.py` — MCP tool definitions (read_notifications, read_channel, send_message, etc.)
  - `mcp_server.py` — starts FastMCP over Streamable HTTP
  - `game_clock.py` — round progression and termination detection (delegates injection delivery to `SimulationRuntime`)
  - `agent_session.py` — per-agent notification queue, reaction delay, idle tracking
  - `scenario_mcp_tool.py` — ScenarioMcpTool for scenario-specific tool registration
  - `scenario_world.py` — ScenarioWorld ABC, WorldContext, MessageEvent, RoundAdvancedEvent
- `src/glossogen/runners/` — autonomous mode agent runners:
  - `agent_runner_base.py` — abstract base class for agent runners
  - `pydantic_ai_runner.py` — Pydantic AI agent runner via pydantic-ai framework
  - `pydantic_ai_model_factory.py` — per-provider mapping from `(model, provider)` to a pydantic-ai `model=` argument and default `ModelSettings`; shared by the runner and the platform's post-simulation `protocol_probe` helper
  - `communication_protocol.py` — shared prompts and constants for the agent communication protocol
- `src/glossogen/config_overrides.py` — Hydra-style dot-notation config override parser
- `src/glossogen/scenario_registry.py` — maps scenario name strings to `SimulationScenario` classes; lives outside `glossogen.scenarios` package init so importing event-related modules doesn't trigger eager loading of every scenario
- `src/glossogen/autonomous_supervisor.py` — autonomous mode orchestrator (supports resume via `RewindState`)
- `src/glossogen/message_rewind.py` — reconstructs simulation state at any message for fork/resume
- `src/glossogen/run_archive.py` — run directory helpers: `claim_run_dir`, `find_event_offset`/`find_message_offset` (linear JSONL scans), `copy_run_at_event` (copy + JSONL truncate), `strip_legacy_git_dir` (one-shot cleanup of pre-rewrite runs)
- `src/glossogen/message_history_builder.py` — reconstructs pydantic-ai ModelMessage history from JSONL events for fork/resume
- `src/glossogen/llm/` — LLM provider abstraction + Anthropic/OpenAI/HuggingFace implementations
- `src/glossogen/evaluation/` — generic metrics and evaluation infrastructure
  - `metric_core/` — the Metric contract + I/O types
    - `metric_protocol.py` — `Metric` ABC; `compute(events, agent_configs, scenario, llm_provider, run_dir, options)` is the only entry point. Most metrics ignore `options`; metrics that need per-invocation flags (e.g. `protocol_probe`) read them off the passed `MetricRunOptions`.
    - `metric_run_options.py` — `MetricRunOptions` Pydantic model carrying per-invocation flags (`probe_round`, `probe_replicas`); built by the CLI from argparse and threaded into `run_scenario_evaluation(...)`.
    - `metric_registry.py` — `dict[str, type[Metric]]` mapping metric names to their classes; `cls()` builds an instance and `cls.compute(..., options=options)` runs it.
    - `measurement.py` — `Measurement`, `RoundObservation`, `AgentObservation`, and judge-side `RoundNote` Pydantic models
    - `generic_metric_names.py` — canonical name list (avoids circular imports with `scenario_protocol`)
  - `reports/` — on-disk report shape
    - `evaluation_report.py` — `EvaluationReport` schema, plus `load_report` / `write_report` / `merge_evaluation_costs` helpers
    - `evaluation_cost.py` — `EvaluationTokenUsage`, `EvaluationCost`, and `compute_evaluation_cost`
  - `metrics/` — concrete Metric implementations
    - `language_repetition_metric.py` — LLM judge, **per message**: for each round it feeds that round's `#link` messages (pristine) as an enumerated list and the judge returns one redundancy factor per message (≥1.0; captures repeated tokens, digit+word dual-encoding, abbreviation+expansion). Judged `rounds × 3` calls (3 replicas/round, averaged per message). Per-message factors → `language_repetition_messages.jsonl` sidecar (keyed by `message_id`); the `Measurement` carries the per-round mean factor and run-level mean
    - `language_strangeness_metric.py` — detects unusual grammar, structure, formatting (not codes/slang/neologisms)
    - `slang_emergence_metric.py` — detects informal register shifts and colloquial expressions
    - `neologism_metric.py` — detects genuinely invented words (not abbreviations or codes)
    - `shorthand_codes_metric.py` — detects abbreviation systems and symbol-to-meaning mappings
    - `content_filter_refusal_metric.py` — counts ``ContentFilterError`` refusals across the run, with per-round + per-agent breakdowns
    - `perplexity_metric.py` — mean per-token surprisal of primary-channel messages under `gpt2`
    - `mcr_metric.py` — mean total characters per round on the primary channel
    - `mcm_metric.py` — mean characters per message on the primary channel
    - `round_success_metric.py` — generic; reads `RoundResultRecorded` events written by the game clock from `SimulationScenario.judge_round_result` (a required abstract method). Single-team scenarios emit one Measurement (`metric_name="round_success"`); multi-team scenarios emit one per `team_id` (`round_success_team_a`, etc.). Returns `[]` only when a scenario's `judge_round_result` yields no verdicts.
    - `round_success_after_resume_metric.py` — generic; re-scores `round_success` over the post-resume window. Reads `replace_manifest.json` / `cross_run_replace_manifest.json` and every `AgentSwappedMidRun` event; the per-window scoring delegates to the same `RoundResultRecorded` events as `round_success`. Returns `[]` on non-resume runs.
    - `protocol_explanation_metric.py` — generic; probes each agent under its own model with its full end-of-run history to describe (free-text) the communication protocol it remembers. Renders the scenario's per-role template from `get_protocol_explanation_config()` when present, else a generic prompt. Writes `protocol_explanation_responses.jsonl` + `protocol_explanation_usage.json`; answers also land in `per_agent[].note`.
    - `probe_usage_report.py` — shared per-(model, provider) token-usage aggregation (`ProbeUsageReport`, `accumulate_probe_usage`, `build_probe_usage_report`) used by both `protocol_probe` and `protocol_explanation`.
    - `protocol_learned_after_swap_metric.py` — generic LLM-judge; calls the scenario's `detect_protocol_boundary_window` to find the pre/post split and `build_communication_rounds` to render transcripts. Returns `[]` when either hook opts out.
    - `protocol_probe/` — generic protocol-probe metric family (4 metrics). Reads `SimulationScenario.get_protocol_probe_config()` for the per-scenario question bank and probe-prompt templates; returns `[]` when the hook returns `None`.
      - `protocol_probe_metric.py` — runs the probe LLM calls and writes `protocol_probe_responses.jsonl`
      - `protocol_probe_replica_self_similarity_metric.py` — within-(agent, question, cutoff) replica self-similarity
      - `protocol_probe_agent_pair_similarity_metric.py` — agent × agent matrix per (question, cutoff); skips on single-team runs
      - `protocol_probe_cutoff_trajectory_metric.py` — adjacent-cutoff drift per (agent, question)
      - `probe_agent.py`, `similarity_core.py`, `response_models.py` — shared helpers
    - `round_ended/` — round-end trigger metrics
      - `round_ended_idle_metric.py` — flags rounds whose main phase ended via the `all_agents_idle` trigger
      - `round_ended_timeout_metric.py` — flags rounds whose main phase ended via the `round_timeout` trigger
      - `postmortem_ended_timeout_metric.py` — flags rounds whose *postmortem* phase ended via `postmortem_timeout` (wall-clock) rather than all agents going idle. Reads `PostmortemEnded` events (authoritative; covers the final round) with a fallback to `RoundAdvanced(trigger="postmortem_timeout")` for runs predating that event
      - `trigger_detection.py` — shared helpers for reading `RoundEnded` / `PostmortemEnded` / `RoundAdvanced` trigger events
  - `metric_core/` (additions):
    - `round_result_index.py` — `per_round_joint_success(events)` builds round→bool from `RoundResultRecorded` events (multi-team joint = all teams succeeded)
    - `protocol_boundary.py` — `ProtocolBoundaryWindow` NamedTuple returned by `detect_protocol_boundary_window`
    - `protocol_explanation_config.py` — `ProtocolExplanationConfig` NamedTuple returned by `get_protocol_explanation_config`
    - `protocol_probe_config.py` — `ProtocolProbeConfig` NamedTuple returned by `get_protocol_probe_config`
    - `resume_anchors.py` — manifest + `AgentSwappedMidRun` reading helpers shared by `round_success_after_resume`
  - `log_reader.py` — JSONL event loading + scenario/agent config extraction (cross-cutting; used by CLI, server, runtime, and metrics)
  - `round_transcript_builder.py` — builds per-round message transcripts from events (used by all generic LLM-judge metrics)
  - `prompts/` — Jinja2 templates for LLM judge prompts + the `prompt_renderer.py` loader
- `src/glossogen/server/` — FastAPI web server exposing simulation data via REST and SSE streaming
  - `identity/middleware.py` — Clerk-aware ASGI identity middleware; extracts the active group slug from the URL (`/api/g/{slug}/...` or `/mcp/g/{slug}/...`), validates membership via the Clerk session token, and attaches an `Identity` to `request.state`. Local mode (no `CLERK_SECRET_KEY`) short-circuits to a synthetic `local` group / `local-user`.
  - `identity/clerk_verifier.py` — Networkless Clerk JWT verification. Reads both v2 (`o.id` / `o.slg` nested) and legacy v1 (`org_id` / `org_slug` flat) session token shapes.
  - `identity/settings.py`, `identity/identity_model.py` — env config + `Identity` Pydantic model.
  - `identity/bootstrap.py` — boots the synthetic `local` group at startup (idempotent upsert into `groups`).
  - `identity/webhook_router.py` — Svix-verified `POST /api/clerk/webhook` that upserts/soft-deletes rows in the `groups` table from Clerk `organization.created` / `.updated` / `.deleted` events.
  - `runs/listing.py` — Postgres-backed `list_runs_for_group(request, scenario_filter)`; the active group's `group_id` is read from `request.state.identity`.
  - `runs/lookup.py` — `resolve_run_or_404` (queries `runs` table on `(group_id, scenario, run_dir_name)` before touching disk) and `register_new_run` (inserts a row after `claim_run_dir`).
- `src/glossogen/db/` — Postgres data layer (raw SQL via psycopg3 async; alembic for migrations)
  - `pool.py` — async connection pool wrapper
  - `queries.py` — typed query helpers returning Pydantic rows (`get_group_by_slug`, `list_runs_for_group`, `insert_run`, `upsert_group`, `soft_delete_group_by_clerk_org_id`, `set_last_active_group`, etc.)
  - `rows.py` — `GroupRow`, `RunRow`, `UserLastActiveGroupRow` Pydantic models
  - `local_tenant.py` — canonical constants `LOCAL_USER_ID = "local-user"`, `LOCAL_GROUP_SLUG = "local"`, `LOCAL_GROUP_NAME = "Local"`
  - `run_registry.py` — standalone (own connection) variants used by the CLI / scripts that run outside the FastAPI lifespan
  - `migrations/` — alembic env + raw-SQL revisions (`0001_groups_and_runs.py`, `0002_oauth_tables.py`)
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
| `DATABASE_URL` | No (local) / Yes (Clerk/prod) | Postgres connection string for the tenancy + runs index (e.g. `postgresql://localhost:5432/glossogen_dev`). Leave unset or blank for no-database local mode (runs index derived from the filesystem, OAuth state in memory). Required for Clerk multi-tenant auth and production. |
| `CLERK_SECRET_KEY` | Yes (Clerk mode) | Clerk backend secret. If unset, the server boots in single-tenant **local mode** (every request runs as `local-user` in the `local` group). |
| `CLERK_PUBLISHABLE_KEY` | Yes (Clerk mode) | Clerk publishable key (mirrors `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`). |
| `CLERK_JWT_KEY` | Yes (Clerk mode) | PEM public key from the Clerk dashboard. Used for networkless JWT verification. |
| `CLERK_WEBHOOK_SECRET` | Yes (Clerk mode) | Svix signing secret for `POST /api/clerk/webhook` that keeps the `groups` table in sync with Clerk org create/update/delete events. |
| `CLERK_AUTHORIZED_PARTIES` | Optional (Clerk mode) | Comma-separated list of frontend origins allowed to mint tokens for this backend (e.g. `http://localhost:3000,https://app.example.com`). |
| `ALLOWED_ORIGINS` | Optional | Comma-separated CORS origins (defaults to `http://localhost:3000`) |
| `GLOSSOGEN_RUNS_DIR` | Optional | Directory for simulation run data (defaults to `./runs`) |
| `ENABLE_EVALUATIONS` | Optional | Whether the REST evaluate endpoint (the frontend "Run Eval" button) is enabled. Defaults to enabled; set to `false`/`0`/`no`/`off` to disable (endpoint returns 403, frontend hides the button via `GET /api/server-config`). Does not affect the CLI `glossogen evaluate` command. |
| `OAUTH_ISSUER_URL` | Yes (for MCP) | Public backend URL for MCP OAuth (MCP is disabled if unset) |
| `SELF_HOSTED_BASE_URLS` | Required for `--provider self-hosted` | JSON object mapping model name → OpenAI-compatible `/v1` base URL. Example: `{"meta-llama/Llama-3.3-70B-Instruct":"https://....modal.run/v1","Qwen/Qwen3-32B":"https://....modal.run/v1"}` |
| `SELF_HOSTED_API_KEY` | Required for `--provider self-hosted` | Bearer token shared across all entries in `SELF_HOSTED_BASE_URLS` (matches each server's `--api-key`) |
| `LOG_LEVEL` | Optional | Stdlib logging level for `glossogen` CLI commands and analysis scripts (`DEBUG`/`INFO`/`WARNING`/`ERROR`). Set to `DEBUG` to capture verbatim LLM-judge system prompt, user prompt, and structured-output JSON in stderr. Defaults to `INFO`. |
| `LLM_MAX_TOKENS` | Optional | Per-call output-token cap applied uniformly to the Claude (`max_tokens`), OpenAI (`max_output_tokens`), and HuggingFace (`max_tokens`) providers. Defaults to `16384`; bump higher if structured-output JSON truncates. Note: this does **not** cap the simulation agents — those use the `agent_max_tokens` knob (see below). |
| `LANGFUSE_PUBLIC_KEY` | Optional | Langfuse project public key. When both this and `LANGFUSE_SECRET_KEY` are set, `glossogen run` exports every simulation agent's LLM calls (prompts, completions, tool calls, token usage) to Langfuse as OpenTelemetry traces. `.env.example` pre-fills `pk-lf-local-dev` to match the local Docker stack. Only the `run` path is instrumented — `glossogen evaluate` stays untraced. |
| `LANGFUSE_SECRET_KEY` | Optional | Langfuse project secret key. Pre-filled `sk-lf-local-dev`. Blank both keys to disable telemetry. |
| `LANGFUSE_HOST` | Optional | Langfuse base URL. Defaults to `http://localhost:3001` (the local `make langfuse-up` stack; 3001 because the frontend dev server owns 3000). If the stack isn't running, the run logs one `auth_check` warning and proceeds untraced — telemetry never blocks a simulation. |

Frontend environment variables go in `frontend/.env.local` (see `frontend/.env.local.example`):

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | (unset) | Publishable key from the Clerk dashboard. Leave unset for local mode; the frontend then skips mounting `<ClerkProvider>` and the proxy is a pass-through. |
| `CLERK_SECRET_KEY` | (unset) | Clerk secret key for server-side `auth()` / `clerkMiddleware()` calls inside Next.js Server Components and the proxy. |

## Development

```bash
make dev            # start FastAPI backend on port 8000 (reads from ./runs/)
make dev-frontend   # start Next.js dev server on port 3000
```

## Local Langfuse (observability)

Simulation agents' LLM calls are traced to a **local, self-hosted Langfuse** (never cloud)
via pydantic-ai's OpenTelemetry instrumentation. The stack runs from a vendored compose file.

```bash
make langfuse-up     # start the full Langfuse stack (web, worker, postgres, clickhouse, redis, minio)
make langfuse-down   # stop it
make langfuse-logs   # tail the langfuse-web logs
```

- UI at **http://localhost:3001** (3001 because the Next.js frontend owns 3000); first boot
  takes ~2-3 min. Log in with `local@glossogen.dev` / `local-dev-password` (seeded via
  `LANGFUSE_INIT_*` in `docker-compose.langfuse.yml`). Langfuse's internal postgres is mapped
  to host 5433 to avoid clashing with a local 5432 Postgres.
- The `glossogen` org + project and the API keys (`pk-lf-local-dev` / `sk-lf-local-dev`) are
  headlessly seeded on first boot — no UI setup needed. Those keys are pre-filled in
  `.env.example`, so `glossogen run` traces to this instance out of the box.
- Each run is one Langfuse **session** keyed by `run_id`; every agent's cycles trace under it,
  tagged with `agent_id` / `role_name` / `model` / `provider` / `scenario`.
- Telemetry is initialized only in the `glossogen run` path (`init_langfuse_telemetry` in
  [telemetry_bootstrap.py](src/glossogen/telemetry_bootstrap.py)), so `glossogen evaluate`'s
  probe/judge LLM calls are not traced. If the stack is down or keys are unset, the run logs
  one warning and proceeds untraced — telemetry never blocks a simulation.
- Docker Desktop needs adequate resources for the full stack (Langfuse suggests ~4 cores /
  16 GiB). The stack exposes `langfuse-web` on host :3001 and `minio` on :9090; the other
  services (postgres :5433, redis, clickhouse) bind to localhost only.

## Authentication

The backend is multi-tenant. Each Clerk **organization** corresponds to a study **group**; every run is owned by exactly one group, never shared across groups except via the export/import flow. The active group is identified by the URL slug — `/g/<slug>/...` on the frontend maps to `/api/g/<slug>/...` on the backend.

Two run-time modes, switched by the presence of `CLERK_SECRET_KEY`:

### Local Mode (no Clerk)

Default for dev clones. Leave `CLERK_SECRET_KEY` unset on the backend and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` unset on the frontend.

- `ClerkIdentityMiddleware` short-circuits every request to a synthetic `local` group / `local-user`. The `local` row is upserted into `groups` at server startup by `identity/bootstrap.py:ensure_local_group`.
- The frontend renders without a sign-in flow; `<GroupProvider>` is hard-coded to `LOCAL_GROUP_SLUG = "local"`.
- Postgres is still required (the `local` group + `runs` index live there).
- All endpoints except `GET /api/health` still go through the identity middleware — they just receive the synthetic local identity automatically.

### Clerk Mode (prod / multi-tenant)

Set `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_JWT_KEY`, and `CLERK_WEBHOOK_SECRET` on the backend; set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` on the frontend. See README "Authentication" for the full Clerk-dashboard setup.

- Frontend mounts `<ClerkProvider>`. Clerk-issued session tokens carry the active org as either `o = { id, slg, ... }` (v2 — default for new apps) or flat `org_id` / `org_slug` (legacy v1). The verifier reads both.
- `frontend/src/proxy.ts` wires `clerkMiddleware` with `organizationSyncOptions.organizationPatterns = ["/g/:slug", "/g/:slug/(.*)"]`, so navigating to `/g/<slug>/...` automatically activates that organization on the user's session *server-side, for the current request* — before any token is minted. This is how a user with multiple Clerk orgs can hit any of them by URL without first calling `setActive`.
- The API client (`frontend/src/shared/lib/api-client.ts`) calls `session.getToken({ skipCache: true })` per request and attaches the result as `Authorization: Bearer ...`. `skipCache: true` matters: without it, a token minted before `setActive` (e.g. just after sign-in) is returned with `org_slug=null` and every `/api/g/<slug>/...` call 403s.
- `ClerkIdentityMiddleware` (`src/glossogen/server/identity/middleware.py`) verifies the token via `clerk_backend_api.security.verify_token`, parses the URL's group slug, asserts `claims.org_slug == url_slug` (the slug-vs-active-org check), looks up the group's UUID in Postgres, and attaches `Identity(user_id, active_group_id, active_group_slug, ...)` to `request.state`.
- Clerk webhook events (`organization.created`, `organization.updated`, `organization.deleted`) hit `POST /api/clerk/webhook` (Svix-verified). The handler upserts / soft-deletes rows in `groups`. Membership events are accepted but not mirrored — the JWT's active org claim is the source of truth.
- SSE endpoints use the `?token=<jwt>` query parameter (EventSource cannot set custom headers); the identity middleware accepts the bearer in either the `Authorization` header or the `token` query string.

### MCP OAuth 2.0 Authentication

The MCP server at `/mcp` uses OAuth 2.0 with PKCE and dynamic client registration. It is controlled by the `OAUTH_ISSUER_URL` environment variable.

- **Enabled**: Set `OAUTH_ISSUER_URL` to the public base URL of the backend (e.g. `https://backend.up.railway.app`). The MCP server is mounted and protected by OAuth.
- **Disabled**: Leave `OAUTH_ISSUER_URL` unset. The MCP server is not mounted and the `/mcp` endpoint is unavailable.

OAuth configuration:
- Clients auto-register via `POST /mcp/register` (dynamic client registration, RFC 7591).
- Authorization uses the code flow with PKCE (RFC 7636) via `GET /mcp/authorize`.
- In **local mode** the authorize endpoint auto-approves and binds the issued token to the synthetic `local` group.
- In **Clerk mode** the authorize endpoint parks the request as a `pending_oauth_consents` row keyed by an opaque `request_id` (migration `0003_pending_oauth_consent`) and redirects the browser to `{FRONTEND_URL}/mcp-consent?request_id=<id>`. The frontend page is gated by Clerk's `proxy.ts` (signs in if needed); when the user has an active org via `organizationSyncOptions` it shows "Approve for <slug>" / "Cancel", otherwise it renders `<OrganizationList>` to pick or create one. Approve POSTs `/mcp/consent/approve` with the user's Clerk JWT — the backend asserts membership via the JWT's active `org_slug` claim, materialises the OAuth code bound to that `group_id`, and returns the OAuth-client redirect URL.
- Token exchange at `POST /mcp/token` issues access tokens (1 hour) and refresh tokens (30 days). Each row carries a `group_id` so every tool call is scoped via the `RunContext` contextvar primed by `mcp/asgi_context.py`.
- [`ClerkIdentityMiddleware`](src/glossogen/server/identity/middleware.py) accepts MCP OAuth access tokens as a Bearer fallback on `/api/g/<slug>/...` requests, so the CLI can address REST endpoints with the same token issued for MCP.
- OAuth metadata is discoverable at `GET /mcp/.well-known/oauth-authorization-server`.
- Token state lives in Postgres (`access_tokens`, `refresh_tokens`, `authorization_codes`, `pending_oauth_consents`).

CLI surface (uses the same OAuth flow):
- `glossogen login` — walks the user through the OAuth handshake, stores `{access_token, refresh_token, group_slug}` in `~/.glossogen/credentials.json`. See `src/glossogen/oauth_client.py`.
- `glossogen whoami` — round-trips through `GET /mcp/whoami` to print the token's bound group.
- `glossogen push-to-prod` — bulk-uploads local runs to a configured remote via `/api/g/<slug>/runs/import`. Filters by label / scenario / report-present; idempotent on `run_id`. See `src/glossogen/prod_push.py`.
- `glossogen sync-metadata-to-prod` — for every local-evaluated run that's *already* on prod: PUTs the local labels onto `/api/g/<slug>/runs/{scenario}/{run_dir_name}/labels` when they differ, and PUTs the local evaluation report onto `/api/g/<slug>/runs/{scenario}/{run_dir_name}/evaluation` unconditionally (local is the source of truth — every PUT replaces the on-disk copy). Use `push-to-prod` for runs not yet on prod. See `src/glossogen/prod_metadata_sync.py`.

Implementation files:
- `src/glossogen/server/mcp/oauth_provider.py` — `OAuthAuthorizationServerProvider` implementation; `authorize` parks pending requests in Clerk mode and calls `approve_pending_consent` from the consent router.
- `src/glossogen/server/mcp/consent_router.py` — `POST /mcp/consent/approve` (Clerk JWT auth) and `GET /mcp/whoami` (OAuth token auth).
- `src/glossogen/server/mcp/oauth_storage.py` — Postgres-backed storage for clients, codes, tokens, and pending consents.
- `src/glossogen/server/mcp/asgi_context.py` — ASGI wrapper that reads the bearer token, resolves its `group_id`, and primes `RunContext` for every tool call.
- `frontend/src/app/mcp-consent/` — the consent page (Clerk-gated by `proxy.ts`); `consent-client.tsx` carries the picker + Approve button.

## MCP Integration

The backend exposes an MCP (Model Context Protocol) server at `/mcp` for programmatic access to simulation data from LLM clients like Claude Code or Cursor. The MCP server is mounted inside the existing FastAPI app and uses OAuth 2.0 for authentication. Requires `OAUTH_ISSUER_URL` to be set.

### Available Tools

- `list_scenarios` — lists available scenarios with knobs files, metrics, and supported models/providers
- `list_runs` — paginated run listing with filtering by scenario, model, fork status, run status, and labels (AND-matched)
- `get_run_metadata` — lightweight metadata for a single run: agents, channels, configuration, evaluation summary, labels, and full lineage provenance (`parent_run_id` plus the structured `fork_source` / `replace_agent_source` / `resume_at_round_source` / `cross_run_replace_agent_source`)
- `list_derived_runs` — lists every run derived from a parent run (replace-agent, resume-at-round, cross-run-replace-agent), with derivation type, round boundaries, swapped/imported models, labels, and headline `round_success` scores. Uses the runs-index timeline-parent linkage; this can return fewer runs than an orchestrator `src=<run_id>` grouping label, which may span an entire experiment family
- `get_run` — full run content with messages; opt-in sections for reasoning, tool use, debug logs, and system prompts; filtering by agent or channel
- `get_knobs_schema` — returns a scenario's knobs JSON Schema and available knobs preset files
- `get_knobs_preset` — loads a knobs preset JSON payload by scenario and preset name
- `start_run` — launches a simulation subprocess with scenario, model, provider, and optional knobs
- `export_run_artifacts` — returns a relative download URL for a zip archive of the run's artifacts
- `export_agent_thread` — reconstructs one agent's thread (optional exclusive `cutoff_round`) and returns a drop-in provider-native request body (Anthropic Messages / OpenAI Chat); `output_format` defaults to the agent's own provider. Thin MCP wrapper over `thread_export.export_agent_thread_from_run_dir` (same orchestrator as the `glossogen export-thread` CLI and the `/runs/.../agents/{agent_id}/thread` REST endpoint)

### Connecting

From the web UI, click the **MCP** button on the runs page to see connection instructions. Clients discover OAuth automatically via the well-known metadata endpoint — no auth headers needed in the config.

**Claude Code:**

```bash
claude mcp add-json glossogen-runs '{"type":"http","url":"<API_URL>/mcp"}'
```

**Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "glossogen-runs": {
      "url": "<API_URL>/mcp"
    }
  }
}
```

Replace `<API_URL>` with the backend URL (e.g. `http://localhost:8000` for local development). The client handles OAuth registration, authorization, and token refresh automatically. In local mode the consent step auto-approves to the synthetic `local` group. In Clerk mode the client's browser tab opens the Clerk-gated `/mcp-consent` page — the user signs in (if not already) and clicks Approve to bind the issued token to their active org. See the **MCP OAuth 2.0 Authentication** section above for the full flow.

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

**Backend service**: root directory `/`, volume mounted at `/data/runs`. Attach a Railway Postgres database — its connection string becomes `DATABASE_URL`. The Dockerfile runs `alembic upgrade head` before starting the server.

Environment variables:
- `DATABASE_URL` — Postgres connection string (required; backend won't boot without it)
- `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_JWT_KEY`, `CLERK_WEBHOOK_SECRET` — required for Clerk-gated multi-tenant auth
- `CLERK_AUTHORIZED_PARTIES` — comma-separated frontend origins allowed to mint tokens (e.g. `https://frontend.up.railway.app`)
- `ANTHROPIC_API_KEY` — required for simulations
- `ALLOWED_ORIGINS` — comma-separated frontend URLs for CORS (e.g. `https://frontend.up.railway.app`)
- `OAUTH_ISSUER_URL` — public backend URL to enable MCP OAuth (e.g. `https://backend.up.railway.app`)
- `OPENAI_API_KEY`, `HF_TOKEN` — optional provider keys

**Frontend service**: root directory `frontend`.

Build args:
- `NEXT_PUBLIC_API_URL` — backend service URL (e.g. `https://backend.up.railway.app`)
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` — Clerk publishable key (required to mount `<ClerkProvider>` and gate routes)
- `CLERK_SECRET_KEY` — Clerk secret key used by Next.js Server Components and the proxy

**Deploy order**: Backend first (get URL) → set as frontend `NEXT_PUBLIC_API_URL` build arg → deploy frontend → update backend `ALLOWED_ORIGINS` with frontend URL.

## Run Output Directory Structure

All simulation outputs use a standard directory layout. The JSONL event log is the canonical state ledger for a run — every fork, replace-agent, cross-run, and resume-at-round operation locates the target event in the JSONL and writes a truncated copy into a new run directory.

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl              # Event log (messages, reasoning, round transitions)
├── {scenario_name}_debug.jsonl        # Debug log (JSON lines from Python logger)
├── {scenario_name}_report.json        # Evaluation report (written by evaluate)
├── {scenario_name}_stdout.log         # (pipe stdout here)
├── labels.json                        # JSON array of label strings (e.g. ["baseline_oss"])
├── note.md                            # Optional free-text note for the run
├── fork_manifest.json                 # (forked runs only) provenance: source_run_id, target_message_id
├── replace_manifest.json              # (replace-agent or resume-at-round runs) provenance + post-swap channel visibility; replaced_agent_id/replacement_model/replacement_provider are null for resume-at-round
├── cross_run_replace_manifest.json    # (cross-run replace-agent runs only) source_a/source_b/imported_model + post-swap channel visibility
├── imported_history_source.jsonl      # (cross-run replace-agent runs only) verbatim copy of Sim B's JSONL used to mount the imported agent's history
├── replace_config.json                # (replace-agent / cross-run / resume-at-round runs) merged scenario_config + model_overrides written by the orchestrator
├── resume_context_{agent_id}.json     # (resume / fork / replace-agent / cross-run runs) per-agent reconstructed pydantic-ai message history dumped at resume time for inspection
├── resume_context_{agent_id}_round_{R}.json  # (in-run scheduled swap) one file per AgentSwappedMidRun event capturing the swapped-in agent's seed history
├── language_repetition_messages.jsonl # (language_repetition metric) one row per primary-channel message: its per-message redundancy factor (judge, replica-averaged), keyed by message_id
├── protocol_explanation_responses.jsonl  # (protocol_explanation metric) one row per agent: its own free-text description of the protocol
├── protocol_explanation_usage.json    # (same) per-model token usage + cost for the explanation probe batch
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

Two ways to apply them:

1. **Backend API**: `PUT /api/g/{group_slug}/runs/{scenario}/{run_dir_name}/labels` with body `UpdateLabelsRequest{labels: list[str]}` — see [router.py:409](src/glossogen/server/runs/router.py#L409). The PUT replaces all labels (it does not append), so include any existing labels you want to keep.
2. **Direct file write** (orchestrator scripts): write `labels.json` directly to the run dir as soon as the dir exists. Faster than the API and avoids needing the backend to be running. Example:
   ```bash
   echo '["baseline_oss"]' > "runs/veyru/<timestamp>/labels.json"
   ```

**Important**: do not PUT labels after evaluations have run. Evaluations merge into `labels.json` (preserving prior labels), but a PUT replaces. Apply your labels *before* `glossogen evaluate` if you also want eval-derived labels to coexist.

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

The pattern matched runs labeled `["baseline", "budget=2000", "eval:content_filter_refusal:0", "eval:round_success:pass", ...]` and overwrote all of those eval-derived labels. They have to be regenerated via `glossogen evaluate`.

**Rules when bulk-modifying labels.json:**

1. **Always parse as JSON, never substring-match the file contents.** Use Python (`json.load`) and compare list membership precisely (`labels == ['baseline_oss', 'budget=2000']` not `'baseline_oss' in content`).
2. **Scope by run identity, not by label content.** If you're modifying runs you just created in this session, list those run dirs by mtime or by tracking the run IDs at launch. Don't infer them from current label state.
3. **Never overwrite — append.** If you must modify labels, read existing JSON, append/remove specific entries, write back. Only blow away the whole list if you're certain the run has no eval-derived labels (i.e. you just created it and `glossogen evaluate` has not run on it).
4. **If unsure, dry-run first.** Print which runs you'd modify and their current labels; ask the user to confirm before writing.

### JSONL-Backed Run History

The `{scenario_name}.jsonl` file is the canonical event log for a run. `EventLogger` appends one line per event and never mutates earlier lines, so every event has a stable byte offset for the lifetime of the run.

Forks, replace-agent, cross-run replace-agent, and resume-at-round all locate their target event in the source JSONL (via `find_event_offset` / `find_message_offset` in `src/glossogen/run_archive.py`), copy the source run directory, and truncate the JSONL in the new directory to end at that event. Run dirs created before this change carry a legacy `.git/` subdirectory; `load_events` removes it on first read (`strip_legacy_git_dir`).

## Running Simulations

Agents connect to a shared MCP server via the Pydantic AI framework. A game clock manages round progression. Always run simulations as a background process, piping all output to a log file.

**Canonical seed: `seed=42`.** Always use `seed=42` when launching comparison runs so results are comparable against the baseline. Do not vary the seed across replications — the seed fixes the case set, so running multiple times with the same seed measures LLM stochasticity on an identical workload. Only change the seed if the user explicitly asks for it.

**Canonical judge: `claude-haiku-4-5-20251001`.** Set `judge_model: "claude-haiku-4-5-20251001"` and `judge_provider: "anthropic"` in every scenario knobs file. Keeping the judge fixed across runs holds judge-side noise constant so cross-run comparisons measure agent behavior, not judge variance. Only change the judge if the user explicitly asks for it.

### Hydra-Style Config & Overrides

The `run` subcommand uses a unified config system inspired by Hydra. A base config file (`--config`) provides scenario knobs, and trailing `key=value` arguments override individual fields using dot-notation. The `agents.*` namespace is reserved for per-agent model/provider overrides.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --config <config-file.json> \
  [key=value overrides...] \
  > ./runs/<scenario>_stdout.log 2>&1 &
```

Required flags: `--model`, `--provider` (`anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted`), `--runs-dir`.
Optional flags: `--max-agent-turns` (default: 200), `--config <path>` (base config JSON file).

The `self-hosted` provider points pydantic-ai at any OpenAI-compatible chat-completions endpoint. `SELF_HOSTED_BASE_URLS` is a JSON map from model name → `/v1` URL, so multiple self-hosted models can coexist; `SELF_HOSTED_API_KEY` is the bearer token shared across them. Reference deployments are in `modal/` (Llama 3.3 70B + Qwen3-32B, both vLLM with tool calling) — see `modal/README.md` for deploy steps. Once deployed and the env vars are set:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config src/glossogen/scenarios/veyru/knobs_default.json \
  > ./runs/veyru_stdout.log 2>&1 &
```

The pricing entry in `src/glossogen/token_pricing.py` is keyed by the literal model name (case-sensitive prefix match after dots→dashes); add a new entry there if you serve a different model.

**Self-hosted context budget (`agent_max_tokens` knob).** Simulation agents' per-cycle output cap is the `agent_max_tokens` knob (`BaseKnobs`, default `16384`) — not `LLM_MAX_TOKENS`. Self-hosted models are served at a small fixed context (Llama 3.3 70B is `--max-model-len 24576` in `modal/serve_llama.py`), and `input + agent_max_tokens` must stay under it or vLLM 400s with `"maximum context length is 24576 tokens"` and the run stalls. For **replace-agent / swap / cross-run** runs with a self-hosted agent, the swapped-in agent's *reconstructed history accumulates* (the veyru observer grows to ~18k tokens over a 10-round swap), so the default `16384` output cap overflows. **Set `agent_max_tokens: 2048` in the `--knobs` for self-hosted swap runs** (veyru outputs are short tool calls, so it truncates nothing). Raising `--max-model-len` instead risks KV-cache OOM on H100:2 — see `modal/README.md`. The platform also serializes parallel tool calls in reconstructed history for self-hosted agents automatically (vLLM rejects multi-tool-call turns); no action needed there.

Examples:

```bash
# Veyru with base config
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/veyru/knobs_default.json \
  > ./runs/veyru_stdout.log 2>&1 &

# Veyru with per-agent model overrides
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/veyru/knobs_default.json \
  agents.stabilization_engineer.model=gpt-5.4 agents.stabilization_engineer.provider=openai \
  > ./runs/veyru_stdout.log 2>&1 &

# Override knobs inline on top of a base config
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/veyru/knobs_default.json \
  max_round_duration_seconds=120 round_count=20 \
  > ./runs/veyru_stdout.log 2>&1 &
```

Override values are auto-parsed as JSON: `rounds=5` becomes int, `enabled=true` becomes bool, `name=alice` stays string.

Check progress by reading the stdout log file or the JSONL event log.

#### Knob co-dependencies: watch for cross-field validators

Scenarios' knob Pydantic models can have cross-field validators that reject otherwise-valid-looking inline overrides. Toggling one knob without its sibling fails preflight validation, the glossogen run subprocess exits before claiming a run directory, and any orchestrator that simply launches and polls for a new dir will silently lose the spec.

Known cases:

- **veyru**: `postmortem_after_swap=true` requires `postmortem_enabled=true`. When sweeping with `postmortem_enabled=false`, also pass `postmortem_after_swap=false` (the default knobs JSON has it set to true).

Defensive launcher pattern: when overriding a knob, also override every knob the scenario's `model_validator` checks against it. If you're unsure, run one foreground launch first to surface validation errors before queueing a sweep — those errors land in the launch's stdout/stderr log, not in the orchestrator log.

### Live Streaming

Every `glossogen run` starts an embedded streaming server on an ephemeral port and writes a `stream.json` manifest to the run directory. The `glossogen serve` process discovers this file and proxies the simulation's SSE stream to connected frontends. When the simulation ends, `stream.json` is deleted and the server falls back to JSONL tailing for the completed run.

### Resuming Failed Simulations

If a simulation errors midway through, resume from the last checkpoint using the `--resume` flag pointing at the existing run directory.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --resume ./runs/<scenario>/<timestamp> \
  --config <original-config.json> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The `--resume` flag requires the same `--config` as the original run. The `--runs-dir` flag is still required but ignored when resuming.

### Replacing an Agent (Round-Level Rewind)

Replay a finished run from the start of a chosen round with one specific agent restarted on a fresh history while every other agent keeps its full reconstructed history. Useful for asking "could a fresh agent follow the engineer from here on?" — a direct, empirical alternative to a judge.

```bash
glossogen replace-agent veyru \
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

Replace-agent runs appear in the run list with a "Replaced" badge.

### Cross-Run Replacing an Agent (Round-Level Rewind, Different Source for the Imported Agent)

Cross-run replace-agent is a sibling of replace-agent that imports an agent from a *different* completed run (Sim B) into a target run (Sim A) at a chosen round boundary. Same scenario and same `agent_id` only. The imported agent retains its **full pydantic-ai history** (text + thinking + tool calls) from Sim B; non-replaced agents in Sim A continue with their full Sim A history.

```bash
glossogen cross-run-replace-agent veyru \
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

**Postmortem on cross-run runs.** The CLI does not auto-set `postmortem_disabled_at_start` — pass `--knobs /tmp/cross_team_knobs.json` with `{"postmortem_disabled_at_start": true}` for veyru cross-team experiments so opus and gpt-5.4 don't have a backchannel to re-align protocols after the swap. Forgetting this contaminates cross-team experiments.

**Manifest + provenance.** Persisted as `cross_run_replace_manifest.json` (parallel to `replace_manifest.json`). Carries both `source_a_run_id` (target timeline) and `source_b_run_id` (where the imported agent came from), plus `imported_model`/`imported_provider`, `round_start`, `source_b_round_end`, `rounds_after_swap`, `replaced_agent_id`, `channels_with_visible_history`, `blocked_tool_call_channels`. The discovery layer surfaces this on `RunSummary` / `RunDetailResponse` as `cross_run_replace_agent_source`. Cross-run runs appear in the run list with a violet "Cross-run" badge that links back to both sources.

**Verifying the imported history.** Each resumed run writes `resume_context_{agent_id}.json` to the new run dir capturing the exact reconstructed pydantic-ai messages handed to that agent on its first turn. For cross-run runs, `resume_context_<replaced_agent_id>.json`'s tail should match Sim B's last few `field_observer` (or whichever role) messages verbatim — that confirms the cross-run history is being mounted from Sim B and not contaminated by Sim A.

**Label convention.** Cross-run runs are labelled `cross_team` plus a range tag like `15-25` (rounds played post-swap). The streamlit results viewer's "Cross-swap" tab filters on `cross_team` and plots `round_success_after_resume` per `(imported_model, round_start)` bucket against both Source A and Source B accuracy on the same rounds. Apply labels by writing `labels.json` directly *before* `glossogen evaluate` runs (the eval-derived labels merge into that file).

**`round_success_after_resume` works for both flows.** The metric reads either `replace_manifest.json` or `cross_run_replace_manifest.json` and projects to a common `_ResumeAnchor` (`round_start`, `rounds_after_swap`, `source_run_id`, `source_run_dir`). For cross-run runs, the comparison is against Sim A (`source_a_*`) — i.e. "did the imported agent perform better/worse than what the original agent achieved over the same window?".

### Resume at a Round (Post-Hoc, No Agent Replacement)

Round-anchored resume clones a finished run at the start of a chosen round and continues execution without restarting any agent. Every agent keeps its full reconstructed history; the resumed simulation differs from the source only through merged knob overrides. Useful for post-hoc multi-swap studies (inject new `scheduled_events`), toggling `postmortem_enabled` mid-experiment, extending `round_count` past where the source stopped, or just replaying a finished run on a different configuration.

```bash
glossogen resume-at-round veyru \
  --source-run-dir ./runs/veyru/<source_timestamp> \
  --round-start 16 \
  --runs-dir ./runs \
  [--knobs path/to/overrides.json] \
  [--rounds-after-resume K]
```

Required: `scenario_name` (positional), `--source-run-dir`, `--round-start` (≥ 2), `--runs-dir`. Optional: `--knobs <file.json>` (shallow-merged onto source `scenario_config`), `--rounds-after-resume K` (`round_count` is set to `round_start + rounds_after_resume`; default is `source_round_count - round_start`).

**Mechanism.** The flow reuses the `replace-agent` machinery with `replaced_agent_id=None`. `resolve_round_start_anchor` finds the source's `RoundAdvanced(round_start)` event id, the git repo is cloned and checked out at that commit, `model_overrides` is built by pinning every agent to its source-active registration (so a multi-swap source's per-phase models survive the resume), the merged config writes `replace_config.json`, and the resumed subprocess launches via `glossogen run --resume`. The manifest is the standard `replace_manifest.json` with `replaced_agent_id`, `replacement_model`, `replacement_provider` all `null` and `channels_with_visible_history` / `blocked_tool_call_channels` empty.

**Resume ordering on the boundary round.** The game clock's resume branch defers `deliver_round_injections` until after agent runners are launched and the boundary hook fires. The supervisor calls `dispatch_resume_boundary_events()` (which executes any `scheduled_events` bucketed at `round_start`) then `deliver_initial_round_injections()`. This mirrors the normal `_advance_round` order (boundary hook → injection delivery) and ensures that when a `swap_agent` event fires exactly at `round_start`, the round's injection lands in the post-swap session rather than the cancelled predecessor's queue. The `RoundBoundaryScheduler` is pre-seeded from `RewindState.rounds_with_fired_scheduler_events` (set of round numbers carrying `AgentSwappedMidRun` or `PostmortemDisabledMidRun` in the loaded events) so boundaries that already fired in the source — or in a crashed-and-resumed run — are not re-dispatched.

**Inherited `scheduled_events` semantics.** When the source's config carries `scheduled_events`, those entries are preserved unless overridden. Events at `at_round < round_start` are silently skipped (the resumed clock never visits those rounds). Events at `at_round == round_start` fire on resume — by design — because the cloned JSONL captures the state at `RoundAdvanced(round_start)`, which is committed *before* the source's scheduler dispatches that boundary. Pass `--knobs '{"scheduled_events": [...]}'` to override the list (e.g. add a post-hoc swap at a later round, or clear the schedule entirely).

**Picking the subprocess `--model`/`--provider`.** Since every agent is pinned via `model_overrides`, the top-level `--model`/`--provider` flags are unused. The CLI selects the first source-active registration's pair as the defaults so `glossogen run`'s required argparse flags are satisfied.

**Knob-schema evolution caveat.** If the scenario's knobs schema gained a required field after the source was created, validation will reject the merged config until the missing key is supplied. Pass it via `--knobs` for that resume (example: veyru's `easy_round_numbers: frozenset[int]` was added later — older veyru runs need `--knobs '{"easy_round_numbers": [1, 2, 3, 6, 13]}'` to resume).

**Discovery.** The manifest is surfaced as `RunSummary.resume_at_round_source` / `RunDetailResponse.resume_at_round_source` (`ResumeAtRoundSource { source_run_id, round_start, rounds_after_resume, target_event_id, resumed_at }`); when `replaced_agent_id` is null, `replace_agent_source` is suppressed in favour of this field.

**FE surfaces.** The run-detail header shows a green `Resumed @ round N (+K)` badge linking back to the source. The runs-list row shows a green `↺R{N}` badge. Multi-swap runs render one `AgentSwapPointFab` per scheduled swap so users can scroll directly to any boundary.

**Lineage chain.** `replace_manifest.json` carries `source_run_id` + `source_run_dir`, so chaining resume-of-resume-of-resume is traceable: walk `source_run_id` recursively to reach the root. The same field powers the badge's link target.

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
glossogen run veyru --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
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

**MCP `start_run`:** the MCP tool accepts a knobs/config payload containing `model_overrides` (no top-level override field). Preflight validation reads `model_overrides` from knobs/config, validates provider names, and validates agent IDs against scenario roles before launch.

### IMPORTANT: Monitoring Long-Running Processes

When running simulations, evaluations, or any long-running background process, **always** follow this pattern:

**No `sleep`. Use a background heartbeat wake-up and do the checks yourself on wake.** Never run a foreground `sleep` (including any sleep→check→report loop) — it blocks the whole session so the user cannot chat. The working mode:

1. Launch the process in the background (with `run_in_background` or `&`).
2. Arm a **periodic heartbeat** monitor whose only job is to wake you every ~30–60s — the Monitor tool with `while true; do echo "$(date) tick"; sleep 45; done`, or an equivalent `run_in_background` loop that keeps emitting. Each emitted line is a notification. The internal `sleep` inside a *background* watcher is fine; only a *foreground* block is forbidden.
3. On EACH heartbeat notification, run the real check yourself in your turn — an instant snapshot (parse the JSONL with Python/`json`, tail the log, count rounds, grep for errors) — report briefly, and stop the heartbeat (TaskStop) once done.
4. **Do NOT gate the wake-up on a single condition** (`until grep -q '<pattern>' <file>; do sleep; done`). A condition embeds an assumption — a grep string that doesn't match the real (often compact, no-space) JSONL serialization, a guessed event field, a wrong path — and if it's wrong the monitor fires **never** and you hang silently. A heartbeat can't silently fail: a bad assumption costs one wasted tick, not an infinite hang. Only use a condition-based exit when you've *verified* the exact match string against real output first. See memory `feedback_monitor_heartbeat_not_condition`.
5. For on-demand status, run a single instant snapshot command — never a sleep loop.

**Sim runs cost money and time — actively monitor, do not just wait.** Every 1–2 minutes while a launcher or eval is running, tail its log, count running sims per model, and verify no errors / no stuck sims / no duplicate launches. Long unattended gaps are not acceptable: a launcher that's silently looping on a misconfigured spec, a sim caught in a death-spiral retry loop, or a duplicate launch can burn through hours of API spend before the user notices. If you've already launched something and have downtime, fill it with a check — don't wait for the user to ask.

**Per-launch sanity checks** (after every launcher iteration, not just at the end):

- Tail the orchestrator log (last 5-10 lines). Look for `WARN`, `ERROR`, `Traceback`, or empty `new_run_id=` (failed launch). Any of those = investigate immediately.
- `pgrep -f "Python -m glossogen run veyru --model <model>"` for each provider. If a queue's count is below cap and there are unlaunched specs in that queue, the launcher is stuck or misconfigured — diagnose now.
- For each launched run, audit `(labels.json, source_run_id, model)` against the spec list. Per-cell replica counts must match the plan exactly. Duplicates from re-launching, restarts, or buggy queue logic are the #1 wasted-spend bug.
- Tail at least one sim's `<scenario>_stdout.log` to confirm rounds are advancing — `grep -c '"round_advanced"' <jsonl>` and verify the count is climbing between checks.

**Never set wakeups longer than ~10 min while runs are active** unless the runs themselves take many hours. The user expects active oversight: short-interval checks that catch bugs in their first iteration, not 30-min snoozes that let 20 mis-specced sims run to completion before the next look.

### Launching Replace-Agent Runs in the Background

`glossogen replace-agent` is a one-shot CLI that prepares the new run directory and spawns the simulation as a detached subprocess (`subprocess.Popen` with `start_new_session=True`). The CLI returns immediately with `new_run_id=...` and `new_run_dir=...`; the simulation runs independently and writes its own `<scenario>_stdout.log` inside the new run directory.

Single replace-agent run, monitor pattern:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
  --source-run-dir ./runs/veyru/<source_timestamp> \
  --round-start 15 \
  --replaced-agent-id field_observer \
  --model gpt-5.4 --provider openai \
  --runs-dir ./runs \
  --knobs /tmp/replace_knobs.json
# CLI prints new_run_id=veyru/<new_timestamp>; that subprocess is now running detached.
# Monitor via a background wake-up (run_in_background until-loop or Monitor tool) on
# ./runs/veyru/<new_timestamp>/veyru_stdout.log — never a foreground sleep loop.
```

### Parallel Replace-Agent Orchestration

To run several replace-agent variants while keeping at most N simulations live, use a small bash orchestrator. Each `glossogen replace-agent` call returns in ~25s after spawning its detached `python -m glossogen run veyru ... --resume` subprocess; the orchestrator polls active simulations via `pgrep` against the `Python -m glossogen run ... --resume` cmdline, sleeps when full, and launches the next spec when a slot frees up.

**Parallelism policy — per-provider, never shared.** Each provider has independent rate limits and capacity, so the orchestrator must:

- **Cap per model at 15 concurrent sims** (the Anthropic + OpenAI accounts comfortably sustain this).
- **Run a separate queue per model in parallel** so a paused `gpt-5.4` queue (waiting for an OpenAI slot) never holds back the `claude-sonnet-4-6` queue. Strict-sequential single-queue orchestrators are a bug: with mixed-model specs, the queue blocks on the current spec's model and idles every slot on the other provider until the current spec launches. Always use per-provider parallel queues — typically two background subshells joined by `wait`.

Reference shape — per-provider parallel orchestrator (save as `/tmp/replace_orchestrator.sh` or anywhere outside the repo):

```bash
#!/bin/bash
cd "$(git rev-parse --show-toplevel)"

RUNS_DIR=runs
LOG=/tmp/replace_orchestrator.log

# Per-model specs (entries are scenario-specific — at minimum source + knobs).
declare -a GPT_SPECS=(
  "<source_a> /tmp/replace_knobs.json"
  "<source_b> /tmp/replace_knobs.json"
)
declare -a SONNET_SPECS=(
  "<source_c> /tmp/replace_knobs.json"
  "<source_d> /tmp/replace_knobs.json"
)

count_running_for_model() {
  # Match python simulation processes only — capital "Python" comes from the
  # homebrew python.framework binary path, so bash/pgrep subshells that quote
  # the pattern literally do not false-match.
  pgrep -f "Python -m glossogen run veyru --model $1" 2>/dev/null | wc -l | tr -d ' '
}

launch_one() {
  local model=$1 provider=$2 source=$3 knobs=$4
  echo "$(date) [$model] launching source=$source knobs=$knobs" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
    --source-run-dir "runs/veyru/$source" \
    --round-start 15 --rounds-after-swap 10 \
    --replaced-agent-id field_observer \
    --model "$model" --provider "$provider" \
    --runs-dir "$RUNS_DIR" \
    --knobs "$knobs" >> "$LOG" 2>&1
  sleep 2  # let claim_run_dir get a unique unix-second slot
}

process_queue_gpt() {
  for spec in "${GPT_SPECS[@]}"; do
    read -r source knobs <<< "$spec"
    while [ "$(count_running_for_model gpt-5.4)" -ge 6 ]; do sleep 30; done
    launch_one gpt-5.4 openai "$source" "$knobs"
  done
  echo "$(date) [gpt-5.4] queue complete" >> "$LOG"
}

process_queue_sonnet() {
  for spec in "${SONNET_SPECS[@]}"; do
    read -r source knobs <<< "$spec"
    while [ "$(count_running_for_model claude-sonnet-4-6)" -ge 6 ]; do sleep 30; done
    launch_one claude-sonnet-4-6 anthropic "$source" "$knobs"
  done
  echo "$(date) [sonnet] queue complete" >> "$LOG"
}

echo "=== Started at $(date) ===" >> "$LOG"
process_queue_gpt &
process_queue_sonnet &
wait
echo "$(date): all launches complete" >> "$LOG"
```

**Key points:**
- Two background subshells (`process_queue_gpt &`, `process_queue_sonnet &`) + `wait` to join — gpt and sonnet queues advance fully in parallel.
- Each `count_running_for_model` query is tightly anchored on `--model <name>` so the two queues never count each other's sims.
- `-ge 6` per model means at most 12 concurrent sims total across both providers.
- If you only have a single-model workload, just remove the unused queue function — but never go back to a single shared `count_running` that mixes models.

Launch the orchestrator detached so it survives the session:

```bash
nohup bash /tmp/replace_orchestrator.sh > /tmp/replace_orchestrator.stdout 2>&1 &
disown
```

Monitoring pattern (every ~30s):

```bash
tail -20 /tmp/replace_orchestrator.log
pgrep -af "Python -m glossogen run veyru .* --resume"
```

`pgrep` pitfalls:
- The pattern **must** anchor on `Python` (capital) so bash/zsh subshells that contain the string verbatim don't false-match. The same applies to any wrapper command (e.g. a `Bash` tool call running `pgrep` on a string that quotes the pattern — that command's argv contains the pattern, and a loose pattern like `glossogen run veyru` will count it).
- Same caveat for the orchestrator's `count_running` function — keep it in a function (not inlined into a wrapping command) and use the tight pattern.

The orchestrator has no automatic recovery: if it dies, simulations keep running but no further launches happen. To resume, recompute the remaining queue (subtract already-launched specs from your full plan) and relaunch with the trimmed `queue=(...)`.

## Running Evaluations

### NEVER evaluate a run before it has emitted `simulation_ended`

**The only safe "this run is finished" signal is the `simulation_ended` event in the JSONL.** Do not gate evaluation (or any "completed" check) on a round count such as `grep -c '"round_advanced"' >= round_count` or `round_advanced.round_number == <last>`. `round_advanced` to round N fires when round N **starts**; round N's `RoundResultRecorded` is not written until round N **ends** (after its game phase + postmortem). So a count-based gate fires while the final round is still running and evaluates a run that is missing its last round — `round_success` then reads `N-1` rounds (e.g. `6/14` instead of `7/15`), and any per-round export keyed off `round_success` silently drops the final round's data.

This exact bug clipped the last round from 13 veyru `channel_noise` runs (their `rolling_eval.sh` used a `round_advanced >= 15` gate); re-evaluating the untouched JSONL produced the correct `/15`. The data was always complete — only the premature eval was wrong.

Rules for any launch-then-evaluate or scan-for-complete orchestration:

- Wait for / filter on `simulation_ended`, e.g. `grep -q '"simulation_ended"' <run>/<scenario>.jsonl`. The shared `wait_for_simulation_end` helper in `scripts/run_rerun_plan.py` (reused by `rerun_18_parallel.py` and `run_self_hosted_reruns.py`) does this correctly — prefer it.
- `round_advanced` counts are fine only for *progress monitoring* (watching rounds climb), never for *completion*.

After a simulation completes, score the log with one or more **metrics** — both deterministic ones and LLM-as-judge ones live behind the same `Metric` abstraction, returning a `Measurement` (`score`, `score_unit`, `summary`, `per_round`, `per_agent`). Evaluation uses `--provider` to select the LLM judge for the LLM-driven metrics; deterministic metrics ignore it. The evaluate command reads the scenario configuration from the JSONL event log, so no scenario-specific flags (like `--knobs`) are needed.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate <scenario> \
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

Metrics that DO emit a zero-score Measurement keep doing so when the count is a legitimate observation: `round_ended_idle`, `round_ended_timeout`, and `content_filter_refusal` all use `score = 0` to mean "this run had zero rounds/refusals with the trigger." (`postmortem_ended_timeout` is a hybrid: `score = 0` when postmortem ran but never timed out, but `[]` when the run had no postmortem phase at all.)

**`evaluation_cost` accumulates across invocations.** Each call to `glossogen evaluate` adds its provider usage onto the existing report's `evaluation_cost.usage` (via `merge_evaluation_costs` in [evaluation_report.py](src/glossogen/evaluation/reports/evaluation_report.py)) when the `(model, provider_name)` pair matches. Mismatched model/provider resets the cumulative cost to the new invocation's value (a mid-stream judge swap invalidates the running total). The `estimated_cost_usd` is recomputed each write from the summed usage. Implication: a re-run with no real LLM calls (e.g. a metric that errors before generating, or a not-applicable invocation) no longer clobbers prior cost data to zero.

Metrics no longer write `eval:` labels into `labels.json` — filter on `score` or on the `per_round` list directly.

Available metrics per scenario:

Generic metrics (available to all scenarios):

- `language_repetition` — how much each message redundantly re-encodes information on the primary channel under noise (repeated tokens like `Lf Lf 12 12`, digit+word dual-encoding like `12 twelve`, abbreviation+expansion like `gnt gentle`). **Per-message LLM judge**: for each round, that round's `#link` messages (pristine pre-noise text) are fed as an enumerated list and the judge returns one `repetition_factor` per message (≥1.0; 1.0 = each piece of info once, 2.0 ≈ twice, 3.0 ≈ thrice). Each round is judged **3 times** (`rounds × 3` calls/run) and per-message factors are averaged across replicas. Per-message factors are written to a `language_repetition_messages.jsonl` sidecar keyed by `message_id`. `score` = mean per-message factor across rounds (run mean); `per_round[].value` = that round's mean per-message factor. Within-message only (cross-message repetition is not counted). Not bit-reproducible (judge-derived), but per-message framing + 3-replica mean make it far more stable than round-level lumping.
- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style (NOT codes, slang, or new words). LLM judge; `score` = number of rounds with detected anomalies.
- `slang_emergence` — informal register shifts, existing-word repurposing (NOT codes or new words). LLM judge; `score` = number of rounds with detected slang.
- `neologism` — genuinely invented words with new meanings (NOT abbreviations or code mappings). LLM judge; `score` = number of rounds with detected neologisms.
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding (NOT new words or slang). LLM judge; `score` = number of rounds with detected codes.
- `perplexity` — mean per-token surprisal of primary-channel messages under `gpt2`, reported per round (deterministic, no LLM judge). `score` = overall mean nats; `per_round` carries per-round mean+std+message count. Skips scenarios with no primary channel.
- `mean_chars_per_round` — total characters of all primary-channel messages in a round, averaged across rounds (deterministic, no LLM judge). `score` = mean chars/round; `per_round` carries per-round total + message count. Skips scenarios with no primary channel. The headline throughput number — in Veyru this maps directly to `time_budget_seconds` (one char = one second).
- `mean_chars_per_message` — characters per primary-channel message, averaged across all messages (deterministic, no LLM judge). `score` = overall mean chars/message; `per_round` carries per-round mean+std+message count. Skips scenarios with no primary channel. Normalizes MCR by message count: rounds that need more back-and-forth no longer inflate the score, so MCM isolates per-message verbosity from message density.
- `round_ended_idle` — flags rounds whose main phase ended because all agents went idle on `read_notifications` (deterministic, no LLM). `score` = count of idle-ended rounds. Requires `round_ended` events in the log.
- `round_ended_timeout` — flags rounds whose main phase ended because the wall-clock duration limit was reached (deterministic, no LLM). `score` = count of timeout-ended rounds. Requires `round_ended` events in the log.
- `postmortem_ended_timeout` — flags rounds whose *postmortem* phase ended because the wall-clock duration limit was reached, rather than because all agents went idle (deterministic, no LLM). `score` = count of postmortem phases that hit the timeout; `per_round` lists the flagged rounds. Reads `PostmortemEnded` events (authoritative; includes the final round, whose postmortem end is otherwise unrecorded) and falls back to `RoundAdvanced(trigger="postmortem_timeout")` for runs predating that event — attributing each such advance to the round before it. **Returns `[]`** when the run had no postmortem phases (no `PostmortemStarted` events).
- `content_filter_refusal` — counts `ContentFilterError` refusals across the run (deterministic, no LLM). `score` = total refusal count; `per_round` lists rounds with at least one refusal; `per_agent` lists per-agent counts.
- `communication_open_coding` — pass 1 of the open-coding → ontology → relabel pipeline. One LLM call per run feeds the judge every primary-channel message plus the scenario-rendered per-round ground truth (via `SimulationScenario.build_communication_rounds`), and asks for free-form short labels naming communication-pattern features (multi-label per run, no pre-specified vocabulary). Writes `communication_open_coding.json` to the run dir with each label's evidence round and quote. `score` = number of free-form labels. Followed by `scripts/consolidate_communication_ontology.py` (one LLM call across N runs of one scenario, writes a versioned ontology under `runs/<scenario_name>/_ontology/<version>.json`) and then `communication_feature_presence` for relabel. **Returns `[]` (no Measurement)** when the scenario does not implement the `build_communication_rounds` hook.
- `communication_feature_presence` — pass 3 of the same pipeline. Accepts `--ontology-path PATH` to pin a specific ontology JSON; when omitted the metric auto-resolves the most recently modified ontology JSON under `runs/<scenario>/_ontology/`. One LLM call per run re-reads the same per-round transcript view against the ontology's categories and emits a 0–1 confidence per category. Writes `communication_feature_presence.json` (full feature-presence vector + ontology provenance). `score` = number of categories scoring ≥0.5. Passes 1 and 3 read the same `CommunicationRoundView` rows so confidences are commensurable with the open-coding labels. **Returns `[]` (no Measurement)** when the scenario does not implement the `build_communication_rounds` hook.
- `round_success` — generic; reads `RoundResultRecorded` events. Single-team scenarios emit one Measurement (`metric_name="round_success"`); multi-team scenarios emit one per `team_id` (`round_success_team_a`, etc.). `judge_round_result` is a required abstract method; **returns `[]`** only when a scenario's `judge_round_result` yields no verdicts.
- `round_success_after_resume` — generic; same accounting as `round_success` over the post-resume window. Reads `replace_manifest.json` / `cross_run_replace_manifest.json` and every `AgentSwappedMidRun` event; the comparison in `summary` is against the source run's same-window `round_success`. **Returns `[]`** on non-resume runs.
- `protocol_explanation` — generic; probes each agent post-simulation under its own original model (read from `AgentRegistered`), not the eval `--model`, with its full end-of-run reconstructed history, asking it to describe in free text the communication protocol it remembers. When the scenario implements `get_protocol_explanation_config()` the metric renders that scenario's per-role template; otherwise it uses a generic prompt, so it runs on any scenario where agents communicate. Writes one row per agent to `protocol_explanation_responses.jsonl` and per-model cost to `protocol_explanation_usage.json`; each answer is also stored in `per_agent[].note`. `score` = number of agents probed. **Returns `[]`** only when no agent has any reconstructable history.
- `protocol_learned_after_swap` — generic LLM judge; uses `detect_protocol_boundary_window` (default: first `AgentSwappedMidRun`) to find the pre/post split and `build_communication_rounds` to render transcripts. `score` = number of post-boundary rounds with observable newcomer protocol evidence. **Returns `[]`** when either hook opts out (no boundary, or scenario doesn't implement `build_communication_rounds`).
- `protocol_probe` — generic; probes each agent post-simulation against the scenario's fixed test bank, writing one row per (agent, question, replica) to `protocol_probe_responses.jsonl`. Each agent is probed under its own original model (read from `AgentRegistered`), not the eval `--model`. The scenario supplies the question bank, probe-prompt templates, and role-name mapping via `get_protocol_probe_config()`. Requires `--probe-replicas N` (≥1); optional `--probe-round R` is an **exclusive** cutoff — every tool call with `round_number >= R` is dropped, so the reconstructed history covers rounds `1..R-1` (inclusive). To capture state at the END of round R, pass `--probe-round=R+1`. Token usage + dollar cost go to `protocol_probe_usage.json`. `score` = total probe rows written. **Returns `[]`** when `get_protocol_probe_config()` returns `None`.
- `protocol_probe_replica_self_similarity` — generic; for each `(agent_id, question_id, cutoff_round)` group with ≥2 replicas, computes the upper-triangle mean of the replica × replica normalized-Levenshtein matrix on `response_text`. `score` = macro mean across groups; matrices persisted to `protocol_probe_replica_self_similarity.json`. Saturation at 1.0 is the expected signal for a converged protocol. **Returns `[]`** when `protocol_probe_responses.jsonl` is missing or no group has ≥2 replicas.
- `protocol_probe_agent_pair_similarity` — generic; agent × agent matrix per (question, cutoff). `score` = macro mean across groups; persisted to `protocol_probe_agent_pair_similarity.json`. Only meaningful in two-team / cross-team runs. **Returns `[]`** on single-team runs.
- `protocol_probe_cutoff_trajectory` — generic; for each `(agent_id, question_id)` pair where the JSONL contains rows from ≥2 distinct `cutoff_round` values, computes the mean cross-replica similarity between each adjacent cutoff snapshot. `score` = macro mean across all adjacent-cutoff pairs; persisted to `protocol_probe_cutoff_trajectory.json`. **Returns `[]`** when the JSONL has only one cutoff value.

Scenarios opt into most platform metrics by implementing the corresponding hooks on `SimulationScenario`. `judge_round_result` and `get_primary_channels` are **required** (abstract) — every scenario must implement them, since round-success and primary-channel throughput/language metrics are core; the rest below are opt-in:

| Hook | Enables |
|---|---|
| `judge_round_result(round_number, trigger) -> list[RoundResult]` (required) | `round_success`, `round_success_after_resume` |
| `get_primary_channels() -> list[PrimaryChannel]` (required) | `perplexity`, `mean_chars_per_round`, `mean_chars_per_message`, language-emergence judges |
| `build_communication_rounds(events) -> list[CommunicationRoundView]` | `communication_open_coding`, `communication_feature_presence`, `protocol_learned_after_swap` |
| `detect_protocol_boundary_window(events, agent_configs) -> ProtocolBoundaryWindow \| None` | `protocol_learned_after_swap` (default returns first `AgentSwappedMidRun`; override to also detect scenario-specific boundaries like intern takeover / two-team observer swap) |
| `get_protocol_probe_config() -> ProtocolProbeConfig \| None` | `protocol_probe`, `protocol_probe_replica_self_similarity`, `protocol_probe_agent_pair_similarity`, `protocol_probe_cutoff_trajectory` |
| `get_protocol_explanation_config() -> ProtocolExplanationConfig \| None` | Tailors `protocol_explanation` with scenario per-role describe templates (optional; the metric runs with a generic prompt when this returns `None`) |
| `restore_state_from_events(events)` | Accurate "previous round" injection context after fork / resume / replace-agent |
| `get_replace_agent_blocked_tool_call_channels() -> frozenset[str]` | Strips scenario-private channel traffic (e.g. postmortem) from replaced agent's reconstructed history |

There are no scenario-specific metrics left — every scoring concept (round-success, post-resume re-scoring, language emergence, protocol learning, protocol probing) is platform code that consumes scenario data through these hooks. Scenarios only ship their domain-specific events + the hooks that surface them.

## Judge Replay and Rerun Pipeline

When the stabilization judge prompt changes, the full retroactive cleanup pipeline (re-judge old verdicts → surface flips in the FE/streamlit → build affected-set plan → re-execute originals → re-execute derived runs → re-replay) is documented in [docs/judge-replay-and-rerun-pipeline.md](docs/judge-replay-and-rerun-pipeline.md).

Quick reference for the scripts (all live in `scripts/`):

- `replay_veyru_judge.py` — re-judge previously-accepted verdicts; writes `runs/_judge_replay/{pair_cache,flips_by_run,summary}.{jsonl,json}`.
- `write_judge_replay_sidecars.py` — fan the replay output into per-run `judge_replay.json` sidecars (read by the FE / streamlit).
- `build_rerun_plan.py` — compute the affected-set (seed runs above threshold + transitive descendants), topologically sort, emit `rerun_plan.json` with per-spec `cli_invocation`.
- `run_rerun_plan.py` — orchestrator: launch → wait-for-end → eval → archive each spec; concurrency is per-provider; state in `rerun_state.json`.
- `recover_errored_reruns.py` — finish the pipeline for `sim_wait_timeout` casualties whose sim completed naturally on disk.
- `rerun_network_impacted.py` (dry-run preview) and `rerun_18_parallel.py` (parallel re-execution alongside a running orchestrator) — re-execute archived runs whose round-timeouts were network-induced.

Artifact directories: `runs/_judge_replay/` (cache + plan + state), `runs/_superseded/<scenario>/<old>/` (archived predecessors), `runs/_failed_network_timeout/<scenario>/<bad_new>/` (audit trail for re-executed failures).

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
