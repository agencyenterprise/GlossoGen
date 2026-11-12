# GlossoGen Architecture

A platform for running controlled experiments on teams of LLM agents. LLM-based agents interact through communication tools the runtime offers. Each agent is a Pydantic AI agent running as an asyncio task in the run's process, with the runtime's tools bound to it as function tools. A game clock manages round progression and injection delivery. No centralized turn control.

A web UI exposes simulation runs and evaluation results through a FastAPI backend and Next.js frontend.

## Design Decisions


| Decision            | Choice                                                       |
| ------------------- | ------------------------------------------------------------ |
| LLM Backend         | Pydantic AI (supports Anthropic, OpenAI, Ollama, self-hosted OpenAI-compatible endpoints) |
| Transport           | In-process function tools; the agent id is bound when a tool is built |
| Scenario Definition | Python classes                                               |
| Agent Autonomy      | Agents decide when to speak; no central turn controller      |
| Round Advancement   | Hybrid: all-agents-idle OR round timeout                     |
| Channels            | Scenario-defined channels with membership lists              |
| Agent Runtime       | Pydantic AI function tools (pluggable runner interface)      |
| Coordination        | Reaction delays + per-channel write locks                    |
| Agent Framing       | Agents do not know they are in a simulation; tools feel like Slack |
| Observability       | Structured JSONL log (one file per run)                      |
| Run Storage         | Filesystem: `runs/{scenario}/{unix_timestamp}/`              |
| End Conditions      | Scenario-defined round count + max round duration            |
| Entrypoint          | CLI (`python -m glossogen run|evaluate|serve|replace-agent|cross-run-replace-agent|fork-at-round`)   |
| Metrics             | Post-hoc LLM-as-judge, user-selected metrics, JSON report   |
| Web Server          | FastAPI with structured Pydantic response models             |
| Frontend            | Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4   |
| API Client          | openapi-fetch with generated types from OpenAPI schema       |
| Data Fetching       | TanStack React Query                                         |
| MCP Runs API        | FastMCP mounted at `/mcp` on the FastAPI server (Streamable HTTP) |
| MCP Authentication  | OAuth 2.0 with PKCE and dynamic client registration (MCP library built-in); the identity provider's consent page in multi-tenant mode, auto-approval in single-tenant mode |
| MCP Token Storage   | Postgres (`access_tokens`, `refresh_tokens`, `authorization_codes`, `pending_oauth_consents`) |
| Tenancy             | One external organization = one `groups` row. Every run is owned by exactly one group; URL slug `/g/<slug>/` is the source of truth |
| Identity Layer      | `IdentityMiddleware` (ASGI) delegates credential checks to a pluggable `IdentityProvider`, or stamps a synthetic identity when none is installed; also accepts an MCP OAuth token |
| Tenancy Storage     | Postgres via psycopg3 async + alembic migrations (raw SQL `op.execute(...)`) — no SQLAlchemy in app code |



## Package layers

The list groups the top-level packages from the bottom up. It is a grouping, not a full layer order: only the boundaries named in each item hold, and others are crossed on purpose (`dashboards/postgres_dashboard_store.py` imports `db.pool`, for example). Nothing enforces the boundaries automatically, so a review checks them.

1. **Contracts**: `model_catalog/`, `models/`, `run_storage/`. The LLM catalog, the event schema and everything that reads a run directory or selects finished runs from it, including `knob_filter.py`. They import no web framework and none of the groups after them. `models/` imports only `models/` and `model_catalog/`.
2. **LLM access**: `llm/`. The provider judges call, token counters and per-provider model construction. It imports only the contracts.
3. **Scenario contract**: `scenario_contract/`. What a scenario implements and what it receives: `ScenarioBase` and `SimulationScenario`, `BaseKnobs`, `ScenarioWorld` and the `WorldContext` it reaches the run through, `ScenarioTool`, the notification and wake types a `read_notifications` override renders, the `Metric` contract and the evaluation configs a scenario declares, and the platform's runner prompts. Where the runtime implements one of these (`WorldContext`, `NotificationInbox`, the event log behind `ScenarioRuntimeHandle`), the contract holds the abstract type and `runtime/` the implementation. It imports the groups above and `template_renderer`, and nothing from `runtime/`, `runners/`, `evaluation/` or `scenarios/`.
4. **Replay**: `run_replay/`. Rebuilds agent histories and simulation state from a run's log. It imports the groups above, and the runtime uses it for resume and in-run swaps.
5. **Simulation**: `runtime/`, then `runners/`. The runtime owns the runner interface (`runtime/agent_runner.py`, `runtime/agent_tool_specs.py`) and imports nothing from `runners/` or `evaluation/`; the entry point hands the supervisor a runner factory. The runner does not import `server/`, `db/` or `cli/`, except `runtime.autonomous_supervisor`, which writes run status through `db.run_registry`.
6. **Scenarios**: `engine/` and `scenarios/`, on top of the scenario contract and the runtime. Platform code reaches a scenario only through `scenario_contract.catalog`, `scenario_contract.loader` and `scenario_contract.scenario_sources`, which decides what the catalog imports. Nothing outside `scenarios/` imports `glossogen.scenarios.*` except `testing/`, which names concrete scenarios by design.
7. **After-the-run work**: `evaluation/`, `run_derivation/`, `run_export/`, `run_analysis/`, `dashboards/`, and the exporters (`atif_export/`, `thread_export/`). `evaluation/` imports the scenario contract, the contracts, `llm/` and `run_replay/`, and nothing from `runtime/` or `runners/`.
8. **Serving**: `server/`, `db/`, `prod_sync/`. Nothing imports `server/`.
9. **Entry point**: `cli/`. Nothing but `__main__` imports it.

`models/` and `run_storage/` import no scenario code. Which event types a run's scenario declares reaches `run_storage/event_parsing.py` through a lookup the scenario catalog installs there when it loads (see "Scenario Event Parsing").

`models/` also holds what a run's log records beyond the events themselves: the round-end triggers, the scheduled events, the base tool names, the `read_notifications` schema and elapsed-time conversion. The runtime, the runners and evaluation all read them from there.

No two top-level packages import each other, directly or through other packages, counting module-level imports.

## Simulation Flow

1. **CLI** parses arguments in two passes (first to identify the scenario, then to parse known flags plus `key=value` overrides). Builds the scenario, agent configs and event logger, and starts the embedded server that streams events over SSE. Passes everything into the `AutonomousSupervisor`, with a factory for the agent runner and the function that lists its tool definitions.
2. **AutonomousSupervisor.run()** opens the event logger, builds per-agent `AgentSession` objects, creates the `SimulationRuntime` (the shared state the tools act on), and wires a `GameClock`. Logs `SimulationStarted` and one `AgentRegistered` event per agent.
3. **Agent runners start** as concurrent asyncio tasks, one per agent, each running a Pydantic AI agent with the runtime's tools bound to its agent id.
4. **Game clock triggers round-1 injection delivery** through `runtime.deliver_round_injections(1)`, which pushes `NewInfoNotification` messages to agent session queues. Agents receive these via the `read_notifications` tool and begin interacting.
5. **Agents act autonomously** by calling tools: `read_notifications` (blocks until a notification arrives), `read_channel` (fetches recent messages), `send_message` (posts to a channel), `list_channels` (discovers available channels), and `get_channel_members` (sees who is in a channel). There is no central turn controller.
6. **Round advancement** uses a hybrid condition. The game clock polls at 500ms intervals and advances the round when either (a) all agents are idle (blocked on `read_notifications` with empty queues) *and* at least 5 seconds have passed since the last message, or (b) the round duration exceeds `max_round_duration_seconds` since the last message. When a round advances, the clock bumps `runtime.current_round`, logs `RoundAdvanced`, and calls `runtime.deliver_round_injections(round_number)` to push that round's injections.
7. **Termination** occurs when the game clock reaches `max_rounds`. The runtime broadcasts a `DoneNotification` to all agents, waits `RUNNER_DRAIN_SECONDS` for agent tasks to finish (plus `CLOSING_PROMPT_TIMEOUT_SECONDS` when an agent has a closing prompt), and logs `SimulationEnded` with total message count.

## Simulation Runtime

`SimulationRuntime` is the shared-state container that the game clock, the agent tools, the world context, scenarios, and runners all interact with. It owns the channel router, per-agent sessions, agent tool allowlists, the world context, and the active round number (`current_round`, written by the game clock via `set_current_round`, seeded by the supervisor on resume). It also owns injection delivery: `deliver_round_injections`, `deliver_postmortem_injections`, and `has_postmortem_for_round` look up scenario-defined injection content, push it to agent sessions, and emit the corresponding `InjectionDelivered` / `PostmortemStarted` events. Resume bookkeeping (`_last_injected_rounds`) lives on the runtime and is seeded via `seed_last_injected_rounds`.

Scenarios receive a `ScenarioRuntimeHandle` (a `Protocol` exposing `event_logger` and `current_round`) via `bind_runtime`, used to emit custom events and read the active round.

## Agent Tools

Every agent is offered five base tools, unless its scenario withholds one through `hidden_base_tools`, plus the scenario's own tools from `get_tools()`. The runtime describes them as `ToolSpec`s and the runner binds them as function tools. Agents interact with the simulation exclusively through these tools.

| Tool                 | Parameters                          | Behavior                                                                                                    |
| -------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `read_notifications`     | `wait_for`, `timeout_s`    | Parks the agent until what `wait_for` names arrives (`any`, `message` or `next_round`). `any` returns `no_activity` after the scenario's default timeout when `timeout_s` is not given.  |
| `read_channel`       | `channel_id`, `last_n`     | Returns the last N messages from a channel the agent belongs to. Validates membership.                      |
| `send_message`       | `channel_id`, `text`       | Posts a message under a per-channel write lock, notifies other channel members, fires on-message callbacks.  |
| `list_channels`      | *(none)*                   | Returns channels the agent belongs to with scenario-defined display names.                                  |
| `get_channel_members`| `channel_id`               | Returns the members of a channel with display names. Validates membership.                                  |

Agent identity is bound when the runner builds an agent's tools: each executor receives `agent_id` and the model never supplies it, so agents cannot impersonate each other.

Agents see these as generic communication primitives, not simulation APIs.

## Agent Runners

The runtime owns the runner interface and `runners/` implements it. `AgentRunner` ([`runtime/agent_runner.py`](src/glossogen/runtime/agent_runner.py)) defines one method, `start(agent_config, runtime, cost_tracker)`, which returns an `AgentRunResult`. The same module holds `CLOSING_PROMPT_TIMEOUT_SECONDS`, the bound the supervisor waits for a closing prompt. The tools an agent is offered are `ToolSpec`s ([`runtime/agent_tool_specs.py`](src/glossogen/runtime/agent_tool_specs.py)), each an executor that takes `agent_id` first. A runner binds them to its framework's tool type. The entry point (`cli/run_command.py`, and the test harness in `testing/simulation_harness.py`) builds the supervisor with a factory for `PydanticAIRunner` and with `runners.agent_tools.list_tool_definitions`, which records the schema the model sees on `AgentRegistered`. That way `runtime/` imports nothing from `runners/`. Each runner instance handles one agent.

**PydanticAIRunner** is the primary implementation. It uses the Pydantic AI framework to launch an agent with:
- The agent's system prompt (from `AgentConfig`)
- The runtime's tool specs bound as pydantic-ai function tools (`runners/agent_tools.py`), running in the runner's process
- A configurable `max_turns` limit (default: 200)
- An initial prompt instructing the agent to start by checking for messages

The runner uses `agent.run()` with an `event_stream_handler` to stream token deltas and message previews to the EventBus. It re-prompts the agent via `message_history` after each cycle and stops when a done notification arrives via `read_notifications`. When the run completed and the agent's runner prompts set `closing`, it sends that closing prompt first (see `runners/closing_prompt.py`), then exits. The supervisor creates one runner per agent through the factory.

An agent on an open-weight provider, one whose `PROVIDER_SPECS` row has `weights=WeightClass.OPEN`, also gets `OpenModelAntiCorruptionLayer` (`runners/open_model_anti_corruption_layer.py`). It is a pydantic-ai capability that drops the top-level arguments a tool's schema does not declare, before the call is validated. The tools keep their strict schemas, and agents on other providers reach them unchanged. Each drop is logged as a warning with the call's id, and the event log keeps the call as the model sent it.

## Telemetry & Observability (Langfuse)

Agent and round-judge LLM calls are traced to a local, self-hosted Langfuse via pydantic-ai's OpenTelemetry instrumentation. This is a distinct output channel from the JSONL Event Log (which remains the canonical state ledger); telemetry is for human-facing debugging/inspection, not simulation state.

- **Settings** — `telemetry/telemetry_settings.py` reads `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST`; `enabled` is true only when both keys are present.
- **Bootstrap** — `telemetry/telemetry_bootstrap.py`'s `init_langfuse_telemetry` is called once per process, only in the `glossogen run` path (`cli._run_simulation`). It calls `langfuse.get_client()` (which installs a global OpenTelemetry `TracerProvider` wired to Langfuse's OTLP endpoint), verifies connectivity with `auth_check()`, then `Agent.instrument_all(InstrumentationSettings(include_content=True))`. Bootstrapping only in the run path is what scopes tracing to live runs, their agents and round judges: `glossogen evaluate`'s probe and judge agents run in a separate process and stay untraced. Any failure (keys absent, stack down, unexpected error) degrades to an untraced run; telemetry never raises into the simulation.
- **Trace grouping** — `PydanticAIRunner._agent_trace_context` wraps each agent cycle in `langfuse.propagate_attributes(session_id=run_id, metadata={agent_id, role_name, model, provider, scenario}, tags=[...])`, so all agents of one run group under a single Langfuse session and each span carries the agent's identity. When telemetry is disabled it returns a `nullcontext`, adding no overhead.
- **Round attribution** — because a trace spans every round and rounds advance on a wall-clock timer mid-cycle, round is a per-model-request property. `telemetry/telemetry_round_processor.py`'s `RoundStampingSpanProcessor` (added to the global tracer provider at bootstrap) stamps `round_number` on each `chat {model}` generation span at span-start, reading the live round via `current_round_source` — which the runner points at `runtime.current_round`. The value surfaces as `langfuse.observation.metadata.round_number`, so generations are filterable by simulation round. The agent-run / tool spans are intentionally left unstamped.
- **Flush** — short-lived run subprocesses flush buffered spans before exit via `flush_telemetry` in `_run_simulation`'s `finally`, plus an `atexit` backstop registered at init.
- **Stack** — `docker-compose.langfuse.yml` (repo root) vendors the Langfuse v3 stack (web, worker, postgres, clickhouse, redis, minio), started with `make langfuse-up`. Host ports are shifted off upstream defaults (web 3001, internal postgres 5433) to avoid colliding with the frontend dev server (3000) and a local Postgres (5432). `LANGFUSE_INIT_*` seed a deterministic org/project/user/key pair on first boot.

## Game Clock

The `GameClock` runs as an asyncio task and manages two responsibilities:

1. **Round progression**: Polls at 500ms intervals, checking two advancement conditions:
   - *All agents idle*: Every agent is blocked on `read_notifications` with an empty notification queue.
   - *Round timeout*: Time since the last message exceeds `max_round_duration_seconds`.
2. **Termination**: When `runtime.current_round >= max_rounds` and an advancement trigger fires, the clock returns `RunStatus.SCENARIO_COMPLETE` to the supervisor.

When a round advances, the clock calls `runtime.set_current_round(...)`, logs `RoundAdvanced`, fires the round-boundary hook, and then delegates injection delivery to `runtime.deliver_round_injections(round_number)`. Postmortem phases work the same way: the clock owns the `_in_postmortem` flag and timing resets, then calls `runtime.deliver_postmortem_injections(round_number)` (which logs `PostmortemStarted` and pushes the per-agent injections).

The game clock receives a callback from the runtime (via `add_on_message_callback`) that resets the quiet-period timer whenever a message is sent.

## Agent Sessions

Each agent has an `AgentSession` that tracks:

- **Notification queue**: An `asyncio.Queue` of `ActivityNotification` objects (new messages, new info, done).
- **Idle flag**: Set to `True` when the agent is blocked on `wait_for_notification()`, `False` when a notification arrives or is pushed.

The idle flag is how the game clock determines whether all agents have finished processing.

## Activity Notifications

Three notification types flow through agent session queues:

- **NewMessagesNotification**: One or more messages appeared in channels the agent belongs to. Contains a list of channel IDs.
- **NewInfoNotification**: New information delivered from a scenario injection. Contains the injection text.
- **DoneNotification**: The simulation has ended. Contains the termination reason.

## Coordination Mechanisms

**Per-channel write locks**: Each channel has an `asyncio.Lock`. The `send_message` tool acquires the lock before appending a message and notifying other members, serializing writes to the same channel.

## Channel and Message Routing

The ChannelRouter stores messages and validates membership.

- Scenarios define channels with membership lists (e.g., "planning-meeting" with all agents, "eng-private" with two agents).
- The scenario provides per-agent display names for each channel via `get_channel_display_name(channel_id, agent_id)` (e.g., the engineer sees "private conversation with the PM" while the PM sees "private conversation with the engineer" for the same channel). Agents never see technical channel IDs.
- The scenario provides per-agent display names via `get_agent_display_name(agent_id)`, used when rendering message history in `read_channel`.
- The `send_message` tool validates agent membership before appending a message to a channel.

## Scenario Protocol

The `SimulationScenario` ABC in [scenario_contract/protocol.py](src/glossogen/scenario_contract/protocol.py) defines a contract for scenario plug-ins. The `scenario_contract/` package holds the rest of the contract: `ScenarioBase`, the run-detail extension, the `@scenario` decorator (`registration.py`), the scenario catalog (`catalog.py`), the loader, and the scenario sources a process loads (`scenario_sources.py`, `scenario_source_kinds.py`).

**Core methods (required by all scenarios):**
- `knobs_model()` — return the knobs Pydantic model class. The JSON Schema (`knobs_json_schema()`) and per-field defaults derive from it on the base, so scenarios declare the model here rather than reimplementing schema/default accessors.
- `get_knobs()` — return the validated knobs instance. The base derives `get_round_count()`, `get_max_round_duration_seconds()`, and `get_scenario_config()` from it, so scenarios no longer implement those getters.
- `get_agent_roles(knobs)` — return agent IDs and display names for a (possibly partial or `None`) knobs/config payload; read role-determining flags via `resolve_bool_knob`
- `create_from_config(config)` — reconstruct a scenario from its serialized config dict (used by fork/resume)
- `name()` (the name given to `@scenario`), `scenario_description()`, `get_agents()`, `get_channels()`
- `get_channel_display_name()`, `get_agent_display_name()`, `get_injection()`
- `get_primary_channels()` — the channels evaluators score (throughput/language metrics); required so the choice is explicit
- `judge_round_result(round_number, trigger)` — per-team round verdicts that power `round_success` / `round_success_after_resume`

**Runtime extensions:**
- `get_world()` — scenario world (state, per-message async reactions via `on_message_async`, tool handlers). The `run` event loop is provided by the base `ScenarioWorld`.
- `get_tools()` — scenario-specific tools, one `ScenarioTool` each (agent_id injected automatically)
- `bind_runtime(runtime)` and the `runtime` property are provided by the base; scenarios that emit custom events read `self.runtime` (raises if accessed before binding).

Scoring is not a scenario method: `run_scenario_evaluation(...)` ([scenario_evaluation_runner.py](src/glossogen/evaluation/scenario_evaluation_runner.py)) is platform code that runs the requested metrics against a run's log. The game clock uses the timing getters to manage round progression and termination; injection delivery is triggered by the clock and performed by the runtime via `deliver_round_injections` / `deliver_postmortem_injections`, which read scenario-defined injection content and push it onto agent sessions.

### Scenario Package Layout

Each built-in scenario is a Python sub-package under `glossogen/scenarios/<name>/`. The layout below is the built-ins' convention; nothing reads a file by its name. A scenario's event types are whatever its `event_types()` returns, wherever they are defined.

```
src/glossogen/scenarios/<scenario_name>/
├── __init__.py
├── scenario.py              # the SimulationScenario subclass, decorated with @scenario
├── ids.py                   # agent IDs, channel IDs, tool names, markers
├── knobs.py                 # the Pydantic knobs model extending BaseKnobs
├── knobs_default.json       # canonical preset
├── events.py                # scenario-specific EventBase subclasses, returned by event_types()
├── world.py                 # scenario-specific ScenarioWorld
├── prompts/                 # Jinja2 templates for system prompts and injections
└── evaluation/              # scenario-specific Metric subclasses
```

Each scenario class is registered with `@scenario(name="<scenario_name>")` from [scenario_contract/registration.py](src/glossogen/scenario_contract/registration.py), which records it in a process-wide registry and makes `name()` return that name. A second class registering a name already held raises, naming both modules. The built-ins use their package directory name, which is what their run directories and recorded runs carry.

The registry fills as scenario modules are imported; [scenario_contract/catalog.py](src/glossogen/scenario_contract/catalog.py) decides what is imported. `load_scenario_catalog(sources=...)` imports each source and keeps the classes registered from the modules it imported, after checking each name and that no two scenarios read their files from one directory (see "Scenario sources"). The built-in source is a `PackageScanSource` over `glossogen.scenarios`: it walks the package's directory, descending only into subpackages, and imports a file only if its syntax tree shows a class decorated with `@scenario` from `glossogen.scenario_contract.registration`, so scripts and helpers beside a scenario are never executed. Loading makes the catalog the process's current one.

Each process loads its catalog once, from the sources described in "Scenario sources" below. `cli/cli_entry.py` does it before dispatching any command. `glossogen.server.app` loads the configured catalog when uvicorn imports it directly (`make dev`), the helpers in `testing/` do the same when a test process has not loaded one, `scripts/export_openapi.py` and `scripts/generate_demo_snapshot.py` load the built-in catalog only, before building the app or reading a run, and the test suite loads the built-in catalog in its root `conftest.py`. A lookup, or a read of a run's events, before that raises `ScenarioCatalogNotLoaded`.

Nothing looks up a name in the catalog directly. Every caller goes through `glossogen/scenario_contract/loader.py`, which asks the current catalog. `find_scenario_class` answers None for a name the catalog does not hold, for callers that degrade (run detail, the run list, export); `get_scenario_class` raises `ScenarioNotLoaded`, whose message names the scenario, lists every source the process loaded and where each was configured, and says to add the scenario to `[tool.glossogen] scenarios` or pass `--scenarios`. The CLI prints that message and exits.

### Scenario Event Parsing

A scenario declares the event types it logs beyond the platform's by returning them from `event_types()`. The platform's own are `core_event_types()` in [models/event.py](src/glossogen/models/event.py), which imports no scenario code.

A run logs only the platform's events and its own scenario's, and its first line, `simulation_started`, names that scenario. So a run is parsed with exactly those types. [run_storage/event_parsing.py](src/glossogen/run_storage/event_parsing.py) holds one parser per scenario name, built on first use and cached: `run_event_parser(scenario_name)`. `load_events(log_path)` reads the scenario from the log's first line and raises `ValueError` when that line is not a `simulation_started`. The readers that parse lines on their own (the run-summary scan, the message-export scan, bundle import) pass the scenario name to `parse_event` / `parse_event_bytes`.

`run_storage` does not ask the catalog. When a catalog becomes the process's current one, it installs its `event_types_of` lookup in `event_parsing` with `install_scenario_event_types`, and installing another catalog (or restoring one after `scenario_catalog_installed`) replaces it and drops the cached parsers. A read before any catalog has loaded raises `ScenarioCatalogNotLoaded`, so an ordering bug fails at the first read instead of silently parsing with the platform's events alone.

An event whose type is neither a platform event nor declared by the run's scenario is read into an `UnrecognizedEvent` ([models/event.py](src/glossogen/models/event.py)). It holds the line's `event_type` and the whole line as `payload`, reads `event_id`, `timestamp` and `round_number` like any event, and serializes back to an equal JSON object, byte for byte for a line the event logger wrote. `load_events` counts them per type in one warning per read. When the run's scenario is not in this process's catalog, every scenario event is one, and the warning names the missing scenario. Code that dispatches on event classes passes over them; run detail returns them as `unrecognized_events`, and the run page shows them in its timeline at the time they were logged. A malformed event of a type the parser does read still raises. Because no reader holds two scenarios' events at once, two scenarios may declare the same `event_type`.

The write side keeps logs readable: [runtime/event_logger.py](src/glossogen/runtime/event_logger.py) is built with the classes it may log, `loggable_event_types(scenario_cls)` from [scenario_contract/event_types.py](src/glossogen/scenario_contract/event_types.py), and raises `UndeclaredEventType` for any other class, a subclass of an accepted one included, and for an `UnrecognizedEvent`, which is never emitted live. The derivation flows copy a source run's JSONL lines as bytes, unrecognized ones included, and resume it under the same scenario, so the check applies only to what the resumed run logs.

The catalog refuses, at load, a declared event type with no fixed `event_type` literal, or one that repeats a platform event's or another of the scenario's own. `glossogen validate` also reports an event class defined in the scenario's module or package that `event_types()` leaves out, unless another loaded scenario declares it.

`SimulationEvent` is typed as `EventBase` statically, since the union a run is parsed with is built at runtime. Concrete subclass attributes still require `isinstance(event, ConcreteEvent)` narrowing at use sites.

### Scenario Run-Detail Extensions

Scenarios that want to surface custom data on the run-detail API (per-round case ground truth, judge metadata keyed by tool `call_id`, scenario-specific SSE events) return a `ScenarioRunDetailExtension` from `SimulationScenario.run_detail_extension()`, with a `ScenarioRunExtrasBase` payload class whose `scenario_name` literal is the scenario's name. Both classes live in [scenario_contract/run_detail_extension.py](src/glossogen/scenario_contract/run_detail_extension.py), outside `glossogen.server`, because the scenario contract names them. The module defining a scenario's extension can sit anywhere; nothing looks for it by file name.

[server/runs/scenario_extension.py](src/glossogen/server/runs/scenario_extension.py) asks a scenario class for its extension. [server/runs/models.py](src/glossogen/server/runs/models.py) names no scenario: `RunDetailResponse.scenario_extras` is typed as `SerializeAsAny[ScenarioRunExtrasBase]`, so it serializes as whichever subclass it holds. The API schema is completed when the app is built: `create_app` passes the extensions of every scenario loaded at that point to `publish_scenario_schemas` ([server/runs/scenario_openapi.py](src/glossogen/server/runs/scenario_openapi.py)), which publishes `scenario_extras` as a discriminated union over their `ScenarioRunExtrasBase` subclasses (discriminated by `scenario_name`) and the live event stream as the union of the platform's SSE events and every extension's `sse_event_classes`. `scripts/export_openapi.py` builds the app over the built-in catalog only, so `api.gen.ts` does not depend on which scenarios a developer has configured. After the generic event walk, [server/runs/detail_reader.py](src/glossogen/server/runs/detail_reader.py) calls `extension.build_extras(events, agents_by_id, messages)` for the run's scenario and attaches the result. `glossogen validate` checks the payload's `scenario_name` matches the scenario.

Veyru is the canonical example; see [scenarios/veyru/run_detail_extension.py](src/glossogen/scenarios/veyru/run_detail_extension.py) for `VeyruRunExtras`, the FIFO `(agent_id, call_id)` matcher that builds `stabilize_metadata_by_call_id`, the observer-swap / intern-join / intern-takeover anchors, and the per-round `VeyruCaseSummary` projection.

### Scenario Frontend Plug-ins

On the frontend side, each scenario optionally ships a `ScenarioPlugin` at `frontend/src/features/runs/<scenario>/plugin.tsx` and registers it in [scenario-registry.ts](frontend/src/features/runs/scenario-registry.ts). Platform components look the plug-in up via `getScenarioPlugin(scenarioName)` and route scenario-specific concerns through it instead of hardcoding `scenarioName === "veyru"` checks. The contract lives in [scenario-plugin.ts](frontend/src/features/runs/scenario-plugin.ts): `RoundDetailPanel`, `renderToolMetadata`, `summarizeToolVerdict`, `liveJudge`, `getTimelineMarkers`, `classifyRoundTrigger`. The default plug-in returns null/empty for every slot. `extras` is typed `unknown` at the boundary so the registry can store every plug-in under a single type; each plug-in narrows internally.

These are compiled into the bundle, so a scenario loaded from outside glossogen has no plug-in and resolves to `DEFAULT_SCENARIO_PLUGIN`. That is the intended outcome rather than a gap: the platform UI is driven by the run's event log and the scenario's knobs model, both of which an external scenario supplies.

### Scenario sources

A scenario does not have to live in this repo. Any module that defines a class decorated with `@scenario` is a scenario once a process imports it, and [scenario_contract/scenario_sources.py](src/glossogen/scenario_contract/scenario_sources.py) decides what each process imports. A source is a module name, a `.py` file or a directory ([scenario_contract/scenario_source_kinds.py](src/glossogen/scenario_contract/scenario_source_kinds.py)). The built-in package always comes first; after it, the first of these that is set decides the rest:

1. `--scenarios <source>`, a repeatable global CLI option given before the subcommand;
2. `GLOSSOGEN_SCENARIOS`, `os.pathsep`-separated;
3. `[tool.glossogen] scenarios = [...]` in the nearest `pyproject.toml` at or above the working directory, with paths relative to that file.

With none of them set, the project directory is scanned: the directory holding that `pyproject.toml`, or the working directory when there is none. An empty list in any of the three, `scenarios = []` and `--scenarios ""` included, means no scan.

A spec that names an existing path is a file or directory source; otherwise it is a module name. A module is imported with `importlib`, and when it is a package its directory is scanned the way the built-in package is, so naming an installed scenario pack is enough. A file or directory is imported by module name relative to an import root, the project directory when the path is inside it, which goes on `sys.path` as pytest's `pythonpath` does: `experiments/reactor.py` becomes `experiments.reactor`. A name that resolves to a different file, because another importable module has the same top-level name, is refused.

A directory is walked rather than imported. It imports only files whose syntax tree shows the `@scenario` decorator (the same check the built-in scan uses), and below the directory it starts at it does not descend into hidden or `_`-prefixed directories, `venv`, `.venv`, `env`, `node_modules`, `site-packages`, `__pycache__`, `tests`, `build`, `dist`, the installed glossogen package (so a glossogen checkout does not register the built-ins twice), the runs directories (every `--runs-dir` on the command line, `GLOSSOGEN_RUNS_DIR`, and `runs`, each read relative to the working directory and to the project root), or any run directory, recognised by its `<scenario>.jsonl` event log. The name rules do not apply to the directory the walk starts at, so a project or a configured folder called `tests` is read; the runs directories, the glossogen package and run directories are refused there too. The runs-directory rule is a safety rule: bundle import and pulling runs from prod extract whatever files a bundle carries into a run directory, so a run directory must never become a place code is imported from. A walk logs the files it registered scenarios from, and logs at INFO a folder it skipped for a name that is not an identifier when a file in it uses `@scenario`. It stops after a few thousand `.py` files, warning and suggesting `[tool.glossogen] scenarios`; a scan with no `pyproject.toml` above it warns before it starts.

The default scan is the one source that is not strict. A file it finds that fails to import, or that registers a name another class holds, and a scenario from it the catalog refuses, are logged and left out, so one broken draft under the project does not stop every command, `--help` included. A configured source fails the command instead. One file imported under two module names (`src.pack.mod` by the scan, `pack.mod` by the pack's tests) is one definition: the registry keeps one class for the name, and a source's scenarios are matched by the files it imported.

Nothing a run records is imported. A run records only its scenario's name, and a reader looks that name up in its own catalog. Prod's server sets `GLOSSOGEN_SCENARIOS=""` in the `Dockerfile`, so it loads the built-ins and nothing it would have to find by scanning.

**Children inherit the list.** The server and the derivation flows spawn `python -m glossogen run` and `evaluate` children (`server/run_launcher.py`, `server/runs/router.py`, `run_derivation/run_launching.py`) with `child_process_environment()`, which sets `GLOSSOGEN_SCENARIOS` to the modules the parent loaded beyond the built-ins, by name (a package `__init__.py` a walk imported as `<package>.__init__`, so the child imports that file without scanning the rest of the package), and puts the import roots of its file and directory sources first on `PYTHONPATH`. The child imports the same modules under the same names, so relative imports inside a scenario package keep working, whatever its working directory and without scanning. An empty value is set rather than unset, so a child of a parent that loaded only the built-ins does not scan either.

**`validate <path>`** loads the path as one more source on top of the ones the process already loaded ([scenario_contract/path_loader.py](src/glossogen/scenario_contract/path_loader.py)) and checks every scenario it registers. When the project around the path has a `pyproject.toml` with a `[build-system]`, [scenario_authoring/scenario_package_checks.py](src/glossogen/scenario_authoring/scenario_package_checks.py) also checks that setuptools `package-data` covers the scenario's prompts and presets, which a wheel would otherwise leave out.

Assets come from the scenario, not from a path under `glossogen`. `knobs_preset_names` / `load_knobs_preset` read `knobs_*.json` from `scenario_package_files()`, the directory of the module that defines the scenario class, via `importlib.resources`, and prompts resolve relative to that module. So each scenario needs a directory of its own: `load_scenario_catalog` refuses two loaded scenarios whose `scenario_package_files()` is the same directory, naming both scenarios, their modules and the directory, and `validate <path>` reports the same error. The built-ins each have a package. `glossogen new-scenario <name>` ([scenario_authoring/scenario_scaffold.py](src/glossogen/scenario_authoring/scenario_scaffold.py)) writes only `<target-dir>/<name>/`: the module, its `knobs_default.json` and `prompts/`, an `__init__.py` and a test. The scan of the project directory reaches it with no configuration. After writing, the command imports the configured sources again (`sources_reach`) and, when none of them loads the new module, says how to add it rather than writing the configuration.

Which metrics apply to a scenario's runs is decided per scenario:
`metric_registry.available_metrics(scenario_cls)` merges the generic metrics and
the scenario's own `scenario_metrics()`, and both the evaluation runner and the
keyed-observation reader resolve through it. A generic metric wins a name
collision, so a scenario cannot change what `round_success` means and make two
reports incomparable. The API and `--metrics` validation read names only,
through `scenario_metric_names.available_metric_names(scenario_cls)`;
`generic_metric_names.py` holds the generic names separately so listing them
does not import every metric class.

### Scenario-declared parts and the contract split

A scenario declares its own event types, its own metrics and its run-detail
extension by returning them from classmethods on `SimulationScenario`
(`event_types()`, `scenario_metrics()`, `run_detail_extension()`), so no platform
module names a scenario and a scenario adds them without editing platform code.
Built-in scenarios are listed nowhere: each registers itself with `@scenario`.

Returning metric classes makes the contract import the metric contract, and a
metric's `compute` takes the scenario, so the two would import each other. The
contract is therefore split. `scenario_contract.scenario_base.ScenarioBase` holds every hook the
runtime and the metrics call; `Metric.compute` takes a `ScenarioBase`.
`scenario_contract.protocol.SimulationScenario` subclasses it and adds the declaring hooks,
importing `metric_protocol` and `scenario_contract.run_detail_extension`, which import only
the base. Scenarios subclass `SimulationScenario`; code that only runs or scores a
simulation types against `ScenarioBase`.

A run's events are parsed with its scenario's `event_types()`; see "Scenario Event
Parsing".

## Agent Prompt Framing

Agents are framed as AI assistants helping a person in a role, not as the role itself.

Instead of:

> "You are a product manager. Negotiate the deadline."

The system prompt reads:

> "I'm a product manager. My stakeholders gave me a hard deadline. Between us, the deadline has about 1 extra week of flexibility, but I was told to push for the aggressive date. Help me run this planning meeting effectively."

This keeps agents grounded as genuine assistants (which they are), avoids roleplay artifacts, and makes secret-leak evaluation more meaningful, because confidential information is shared as trusted context between user and assistant.

Agents do not know they are in a simulation. The tools are named after generic communication primitives (`read_notifications`, `read_channel`, `send_message`). From the agent's perspective, it is using a messaging system.

## Event Log

Every simulation event is serialized as one JSON object per line in a JSONL file (one file per run).

A run is read back with the platform's event types plus those its scenario declares in `event_types()`, discriminated on `event_type`; a line of any other type reads back as an `UnrecognizedEvent` holding the line unchanged (see "Scenario Event Parsing"). The platform's include:

- `simulation_started` — run ID, scenario name, scenario description, channel IDs, scenario config
- `agent_registered` — agent ID, role name, system prompt, channel IDs, tool names, model
- `agent_connected` — agent ID, role name, model (emitted when an autonomous agent connects)
- `round_advanced` — new round number, trigger reason (`simulation_start`, `all_agents_idle`, `round_timeout`)
- `injection_delivered` — agent ID, round number, injection text
- `message_sent` — full SimulationMessage (channel, sender, content, timestamp)
- `llm_response_received` — agent ID, text (includes thinking blocks), tool calls, stop reason, token usage
- `closing_prompt_answered` — agent ID, model, the scenario's closing prompt, the agent's text answer, token usage. Logged after the agent's last turn, for scenarios whose runner prompts set `closing`
- `closing_prompt_failed` — the same exchange when no answer came back: error type and message, token usage
- `simulation_ended` — reason (RunStatus enum), total_messages

`EventLogger` ([`runtime/event_logger.py`](src/glossogen/runtime/event_logger.py)) logs only the platform's events and the running scenario's declared ones, and only appends; it never rewrites an earlier line, so every event keeps a stable byte offset for the life of the run. Replace-agent, cross-run replace-agent and fork-at-round use that: `find_event_offset` ([`run_storage/run_archive.py`](src/glossogen/run_storage/run_archive.py)) locates the target event in the source JSONL, and `copy_run_at_event` copies the run directory and truncates the copy's JSONL there. Run directories created before this design carry a legacy `.git/` subdirectory, which `load_events` removes on first read (`strip_legacy_git_dir`).

## Run Storage

All simulation outputs use a standard directory layout:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl              # Event log (one JSON object per line)
├── {scenario_name}_debug.jsonl        # Debug log (JSON lines from Python logger, visible in FE)
├── {scenario_name}_report.json        # Evaluation report (written by evaluate command)
├── {scenario_name}_stdout.log         # the run's stdout, when piped here
├── fork_manifest.json                 # (legacy forked runs only) provenance: source_run_id, target_message_id
├── replace_manifest.json              # (replace-agent or fork-at-round runs) provenance tracking; replaced_agent_id/replacement_model/replacement_provider are null for fork-at-round
├── cross_run_replace_manifest.json    # (cross-run replace-agent runs only) source A/B + imported model
├── imported_history_source.jsonl      # (cross-run replace-agent runs only) verbatim copy of Sim B's JSONL
├── replace_config.json                # (replace-agent / cross-run / fork-at-round runs) merged scenario_config + model_overrides written by the orchestrator
├── resume_context_{agent_id}.json     # (resume / fork / replace-agent / cross-run runs) per-agent reconstructed pydantic-ai history dumped at resume time
├── resume_context_{agent_id}_round_{R}.json  # (in-run scheduled swap) one file per AgentSwappedMidRun event
├── labels.json                        # JSON array of label strings, for filtering and grouping
├── note.md                            # (optional) free-text note for the run
├── stream.json                        # (live runs only) SSE discovery file; deleted when the run ends
└── multi_swap_cache.json              # cached per-phase round_success for multi-swap runs
```

Metrics write their own sidecars next to the report, each one named after the
metric that produced it:

```
├── language_repetition_messages.jsonl           # per-message redundancy factors, keyed by message_id
├── protocol_explanation_responses.jsonl         # one row per agent: its own account of the protocol
├── protocol_explanation_usage.json              # per-model token usage + cost for that probe batch
├── protocol_probe_responses.jsonl               # one row per (agent, question, replica)
├── protocol_probe_usage.json                    # per-model token usage + cost for that probe batch
├── protocol_probe_replica_self_similarity.json  # replica × replica matrices per (agent, question, cutoff)
├── protocol_probe_agent_pair_similarity.json    # agent × agent matrices per (question, cutoff); two-team runs only
├── protocol_probe_cutoff_trajectory.json        # per (agent, question) adjacent-cutoff series; multi-cutoff probe JSONLs only
├── communication_open_coding.json               # free-form open-coding labels
└── communication_feature_presence.json          # per-category confidence against a consolidated ontology
```

The CLI `run` command computes the output path automatically from `--runs-dir`, the scenario name, and the current unix timestamp. The `evaluate` command takes `--run-dir` pointing to a specific run directory and writes the report as a sibling to the JSONL file.

[`run_storage/`](src/glossogen/run_storage/) reads this tree without the web server or Postgres, so the CLI, the exports and the analysis read runs the same way the server does:

- [`event_log_reader.py`](src/glossogen/run_storage/event_log_reader.py): `load_events(log_path)` parses a run's JSONL event log into typed events, reading event types this build has no class for into `UnrecognizedEvent`; `extract_agent_configs`, `extract_simulation_id` and `extract_scenario_config` read those events back into configs
- [`run_discovery.py`](src/glossogen/run_storage/run_discovery.py): `discover_runs(runs_dir)` walks the tree and `build_summary` builds one run's `RunSummary`, cached per run in `run_summary_cache.json`
- [`run_summary_models.py`](src/glossogen/run_storage/run_summary_models.py): `RunSummary` and its parts (`AgentModelSummary`, the `*Source` provenance records, `EvaluationScore`, `RoundResultTally`). The runs list API returns `RunSummary` as is
- [`derivation_manifest_reader.py`](src/glossogen/run_storage/derivation_manifest_reader.py): the derivation manifests read into `*Source` records
- [`evaluation_score_reader.py`](src/glossogen/run_storage/evaluation_score_reader.py): the per-metric scores out of a run's evaluation report
- [`knob_filter.py`](src/glossogen/run_storage/knob_filter.py): `<knob><operator><value>` filters over a run's recorded `scenario_config`, shared by the runs listing, the export request model and the CLI's run selection
- [`run_bundle.py`](src/glossogen/run_storage/run_bundle.py): the tar.gz bundle the server's export endpoint and `push-to-prod` build, and its `bundle_manifest.json`
- [`run_file_paths.py`](src/glossogen/run_storage/run_file_paths.py), [`run_labels_file.py`](src/glossogen/run_storage/run_labels_file.py), [`run_identity.py`](src/glossogen/run_storage/run_identity.py): the scenario-named file paths in a run directory, the one reader of `labels.json`, and the `<scenario>/<run_dir_name>` identifier
- [`run_archive.py`](src/glossogen/run_storage/run_archive.py), [`run_lineage.py`](src/glossogen/run_storage/run_lineage.py), [`archive_member_filter.py`](src/glossogen/run_storage/archive_member_filter.py): directory claiming and copy-at-event, a derived run's timeline parent, and which files an archive carries
- [`jsonl_lines.py`](src/glossogen/run_storage/jsonl_lines.py), [`event_parsing.py`](src/glossogen/run_storage/event_parsing.py): reading JSONL line by line and parsing one event
- [`replace_manifest.py`](src/glossogen/run_storage/replace_manifest.py), [`cross_run_replace_manifest.py`](src/glossogen/run_storage/cross_run_replace_manifest.py), [`derived_run_start.py`](src/glossogen/run_storage/derived_run_start.py): the manifests a derived run keeps, and when its own simulation began
- [`eval_manifest.py`](src/glossogen/run_storage/eval_manifest.py), [`stream_manifest.py`](src/glossogen/run_storage/stream_manifest.py): the `eval_in_progress.json` and `stream.json` discovery files, with their stale-PID check

The channels a finished run's scenario scores are resolved by [`scenario_contract/primary_channel_resolution.py`](src/glossogen/scenario_contract/primary_channel_resolution.py), which sits outside `run_storage/` because it rebuilds the scenario from its recorded config (`scenario_contract/recorded_scenario_rebuild.py`). Run detail reads the ordered channel ids from it, and the message export reads the team behind each channel and whether the scenario rebuilt at all.

Discovery reads the first and last lines of each JSONL file to extract metadata (scenario name, timestamp, total messages, end reason) without loading the full log. Replace-agent, cross-run replace-agent, and fork-at-round runs are identified by the presence of `replace_manifest.json` (with `replaced_agent_id` set vs null) or `cross_run_replace_manifest.json`. Legacy fork runs (created when the message-level fork UI was active) are identified by the presence of `fork_manifest.json`; only their badge and lineage link are still rendered.

## Replace-Agent System (Round-Level Rewind)

The replace-agent system forks a finished simulation after a chosen round and plays the following rounds with one specific agent restarted on a fresh history. Rounds 1..`after_round` stay complete, verdict and postmortem included; the replacement agent enters round `after_round + 1`. Every other agent resumes from its full reconstructed history. The replacement agent's model/provider can differ from the original. Replace-agent creates a new run directory, so the original is preserved.

The clone keeps every agent's events on disk. The replaced agent's *reconstructed history* is filtered at resume time (`AgentHistoryFilter(tool_calls_only=True)`): `text` and `thinking` parts are stripped and tool calls on blocked channels dropped, while every other agent's history is rebuilt in full.

### Replace-Agent Flow

1. **Entry**: User invokes `python -m glossogen replace-agent <scenario> --source-run-dir <dir> --after-round <N> --replaced-agent-id <id> --model <model> --provider <provider> --runs-dir <dir>`. The CLI calls the shared core helper `replace_agent.replace_agent_in_run`, which is `prepare_replace_agent_run` (everything on disk) followed by `run_launching.launch_prepared_run` (the detached subprocess). Tests call prepare alone.
2. **Boundary resolution**: `resolve_fork_boundary(events, after_round)` picks the truncation anchor: the source's `RoundAdvanced(after_round + 1)` when one exists, or, when `after_round` was the source's final round, the last event before the agents were woken with the run's terminated `done` notice (see the fork-at-round section for that path's resume semantics).
3. **Clone + truncate**: `copy_run_at_event` copies the source run directory and truncates the copied JSONL at the anchor's byte offset.
4. **JSONL rewrite**: `run_jsonl_rewriter.rewrite_run_jsonl` rewrites the cloned log's `run_id` and drops its `simulation_ended` lines.
5. **Per-agent model overrides**: An explicit `model_overrides` dict is built that pins every source agent to its original `(model, provider)` pair (read from `AgentRegistered` events at or before the boundary) and overwrites just the replaced agent's entry with the new model/provider. This guarantees non-replaced agents stay on their exact original models even if the top-level CLI defaults differ.
6. **Manifest**: `replace_manifest.json` records `source_run_id`, `round_start` (the entry round, `after_round + 1`), `rounds_after_swap` (`round_count - round_start`), `target_event_id` (the resolved anchor, kept for traceability), `replaced_agent_id`, `replacement_model`, `replacement_provider`, `channels_with_visible_history`, `channel_history_floors`, `replaced_at`. The field names are the frozen on-disk schema every previously recorded run carries; API readers translate them to `after_round = round_start - 1`, `rounds_after = rounds_after_swap + 1`.
7. **Resume**: Launches `glossogen run --resume <new_dir> --config replace_config.json` as a background subprocess.
8. **Supervisor resume**: `resume_state_loader.load_resume_state` reads the manifest and rebuilds `RewindState` with the replaced agent's history filtered as above. The supervisor applies the manifest's channel visibility so `read_channel` returns prior messages only for whitelisted channels; all others have the agent's `member_join_index` bumped to the current message count, hiding pre-fork history without affecting any other agent's view. Before the agents start, the CLI calls `scenario.restore_state_from_events(events)`. Veyru uses it to re-seed each team's `outcomes` list from the source's `message_sent`, `veyru_stabilization_judged` and `round_ended` events, so the entry round's `PREVIOUS VEYRU RESULT` block reports the source's actual round-N outcome.

### Per-Channel History Visibility (Platform Feature)

The replace-agent flow lets the caller choose, per channel, whether the replaced agent retains visibility of pre-resume messages on that channel. This is generic across scenarios.

- **Request field**: `ReplaceAgentRequest.channels_with_visible_history: list[str]` (CLI flag `--visible-history-channel CHANNEL`, repeatable). Empty list = wipe history visibility on every channel the agent is in.
- **Default policy**: `BaseKnobs.replace_agent_default_channel_visibility: dict[str, bool]` (channel ID → visible). Channels absent from the map default to visible. The CLI consults this knob when no `--visible-history-channel` flag is passed. New scenarios opt in by setting the map in their preset JSONs — no code change required.
- **Persistence**: stored on `replace_manifest.json`; the CLI's `--resume` path reads it and threads it onto `RewindState.replaced_agent_channels_with_visible_history` (a `dict[str, list[str]]` keyed by `agent_id`).

### Veyru-Specific Knob: Drop Postmortem After Replacement

Setting `postmortem_disabled_at_start: true` in the merged `knobs` payload makes `VeyruWorld.__init__` flip `_postmortem_globally_disabled = True` immediately. From resume onward `validate_outgoing_message`, `get_postmortem_injection`, and `get_max_postmortem_duration_seconds` all short-circuit, so the postmortem channel exists but is inert (no sends, no injections, no postmortem phase). Pass `--knobs '{"postmortem_disabled_at_start": true}'` on the CLI to opt in.

### Key Modules

- `run_derivation/replace_agent.py` — `ReplaceAgentRequest`/`ReplaceAgentResult`/`ForkBoundary` named tuples, `resolve_fork_boundary`, `resolve_rounds_after`, `prepare_replace_agent_run`, and `replace_agent_in_run` (shared core called by the CLI)
- `run_derivation/run_launching.py` — `PreparedForkRun` + `launch_prepared_run`, the seam between preparing a fork on disk and spawning its subprocess
- `run_derivation/run_jsonl_rewriter.py` — `rewrite_run_jsonl` (run-id rewrite, `simulation_ended` dropped) and `patch_simulation_started_scenario_config`
- `cli/derivation_commands.py` `handle_replace_agent` — CLI subcommand implementation

### Provenance

Replace-agent runs store a `replace_manifest.json`, which carries `source_run_id` and `source_run_dir`. Following `source_run_id` recursively reaches the root of a fork-of-fork chain. The run discovery and detail endpoints expose the manifest as `replace_agent_source` on the response models. The frontend shows a "Replaced X → model after round N" badge in the run detail header, linking to `source_run_id`, and the runs list shows an `R{N}` badge naming the boundary round.

## Cross-Run Replace-Agent System (Round-Level Rewind, Different Source for the Imported Agent)

The cross-run replace-agent system is a sibling of replace-agent that imports an agent from a *different* completed run (Sim B) into a target run (Sim A) at a chosen round boundary. Same scenario and same `agent_id` only. The imported agent retains its **full** pydantic-ai history from Sim B (text + thinking + tool calls); non-replaced agents continue with their full Sim A history.

This shares replace-agent's primitives (clone of Sim A truncated at the fork boundary, JSONL rewrite, `--resume` subprocess, per-channel visibility, optional postmortem disable) but introduces a dual-event-stream architecture for history reconstruction: the imported agent's history is built from Sim B's JSONL while every other agent's history is built from Sim A's JSONL.

### Cross-Run Flow

1. **Entry**: `python -m glossogen cross-run-replace-agent <scenario> --source-a-run-dir <dir> --source-b-run-dir <dir> --after-round <N> --replaced-agent-id <id> --runs-dir <dir>`. The CLI calls the shared core helper `cross_run_replace_agent.cross_run_replace_agent_in_run` (prepare + launch, same seam as replace-agent).
2. **Validate**: Sim A and Sim B exist, scenarios match, `replaced_agent_id` exists in both, `after_round >= 1`, Sim B reached at least `source_b_round_end`. Default `source_b_round_end = min(after_round, B_max_round)` so the imported agent gets the largest temporally-aligned slice of B's history without exceeding what B reached.
3. **Resolve model**: when `--model` / `--provider` are absent, read Sim B's `AgentRegistered` for `replaced_agent_id` and use those values. Both must be passed together to override.
4. **Clone Sim A** truncated at the fork boundary (same resolution as replace-agent), rewrite the JSONL run-id, copy Sim B's full JSONL to `<new_dir>/imported_history_source.jsonl`, build merged scenario_config (knobs + `model_overrides` pinning every Sim A agent to its Sim A model and the replaced agent to the imported model), write `replace_config.json`.
5. **Compute blocked tool-call channels**: scenario default (`get_replace_agent_blocked_tool_call_channels`) ∪ Sim-B-only channels (channel IDs the imported agent had in Sim B but doesn't exist in Sim A — necessary to avoid pydantic-ai schema validation rejecting reconstructed tool calls referencing dead channel IDs).
6. **Manifest**: write `cross_run_replace_manifest.json` with both `source_a_run_id` and `source_b_run_id`, the imported model/provider, `round_start`, `source_b_round_end`, `rounds_after_swap`, `replaced_agent_id`, `channels_with_visible_history`, `blocked_tool_call_channels`. `round_start` here is the entry round, as in `replace_manifest.json`.
7. **Resume**: launches `glossogen run --resume <new_dir> --config replace_config.json` as a background subprocess.
8. **Supervisor resume**: the CLI's resume path detects `cross_run_replace_manifest.json` (in addition to the existing `replace_manifest.json` detection) and builds an `AgentHistoryFilter` for the replaced agent with an `imported: ImportedHistory` slot containing Sim B's events, target_timestamp, and cutoff_round. The history reconstruction loop in `_build_rewind_state_at_timestamp` dispatches per-agent: when `filter.imported is not None`, that agent's history is built from Sim B's events and its system prompt is taken from Sim B's `AgentRegistered`; otherwise the agent's history is built from Sim A's events as usual. Channel visibility on Sim A's channels is applied identically to replace-agent.

### Dual-Event-Stream History Reconstruction

The single non-trivial architectural change vs replace-agent is the extension of `AgentHistoryFilter` (in `run_replay/message_rewind.py`) with a sub-NamedTuple:

```python
class ImportedHistory(NamedTuple):
    events: tuple[SimulationEvent, ...]
    target_timestamp: datetime
    cutoff_round: int

class AgentHistoryFilter(NamedTuple):
    tool_calls_only: bool
    blocked_channel_ids: frozenset[str]
    imported: ImportedHistory | None
```

Grouping the three correlated fields into one Optional sub-tuple makes invalid combinations unrepresentable (you can't have two of three set). When `imported is None` (replace-agent, fork, plain `--resume`), the agent's history comes from the caller's primary event list. When set (cross-run flow), it overrides the events / target_timestamp / cutoff_round / system_prompt for that one agent. The state walk (channels, injections, current round) always uses the primary event list. Only history reconstruction is per-agent redirected.

### Validation: `resume_context_{agent_id}.json`

Same as replace-agent, `glossogen run --resume` calls `write_resume_context_files` before it launches the supervisor. For cross-run runs this dumps the imported agent's reconstructed pydantic-ai history (built from Sim B) to disk, so the operator can verify by hand that the tail matches Sim B's last few `MessageSent` events for that agent, confirming the cross-run history was mounted correctly and not contaminated by Sim A.

### Key Modules

- `run_derivation/cross_run_replace_agent.py` — `CrossRunReplaceAgentRequest`/`CrossRunReplaceAgentResult` named tuples, `_resolve_source_b_cutoff_event_id`, `_compute_blocked_tool_call_channels`, `prepare_cross_run_replace_agent_run`, and `cross_run_replace_agent_in_run` (shared core called by the CLI)
- `run_storage/cross_run_replace_manifest.py` — `CrossRunReplaceManifest` Pydantic model + `read_cross_run_replace_manifest` reader (kept separate from `run_storage/replace_manifest.py` so metrics / discovery can dispatch on file presence)
- `run_replay/message_rewind.py` — `AgentHistoryFilter` extended with `imported: ImportedHistory | None`; `_find_imported_registration` looks up the imported agent's `AgentRegistered` in the imported event stream
- `cli/derivation_commands.py` `handle_cross_run_replace_agent` + `_resolve_source_b_max_round` + `_resolve_imported_model_from_source_b` — CLI subcommand implementation
- `evaluation/metrics/round_success_after_resume_metric.py` — reads either `replace_manifest.json` or `cross_run_replace_manifest.json` and projects to a common `_ResumeAnchor` (so the same metric works for both flows)

### Provenance

Cross-run replace-agent runs store a `cross_run_replace_manifest.json` plus a `imported_history_source.jsonl` (verbatim copy of Sim B's JSONL). The run discovery and detail endpoints expose the manifest as `cross_run_replace_agent_source` on the response models alongside `replace_agent_source`. The frontend shows a violet "Cross-run X: A=… · B=… → imported_model after round N" badge in the run detail header with both sources as links, and a violet floating action button to scroll to the swap divider in the chat pane.

## Fork-at-Round System (Post-Hoc Fork, No Agent Replacement)

Fork-at-round is the simplest sibling of replace-agent: it clones a finished run keeping rounds 1..`after_round` complete and plays round `after_round + 1` onward without restarting any agent. Every agent keeps its full reconstructed history; the fork differs from the source only through merged knob overrides. The flow reuses the replace-agent machinery with `replaced_agent_id=None` — same clone and truncation, same JSONL rewrite, same subprocess launch, same manifest file.

### Fork-at-Round Flow

1. **Entry**: `python -m glossogen fork-at-round <scenario> --source-run-dir <dir> --after-round <N> --runs-dir <dir> [--knobs <file>] [--rounds-after K]`. The CLI builds a `ReplaceAgentRequest` with `replaced_agent_id=None`, `model=None`, `provider=None`, `channels_with_visible_history=None` and calls `replace_agent.replace_agent_in_run`.
2. **Boundary resolution**: `resolve_fork_boundary` picks the anchor. When the source advanced into round `after_round + 1`, that `RoundAdvanced` is the anchor and the resumed clock re-opens the round. When `after_round` was the source's final round, the anchor is the last event before the agents were woken with the run's terminated `done` notice: the first `AgentResumed(terminated=True)` after the final round's closing events (its `round_ended`, `round_result_recorded` verdicts and `postmortem_ended`), or the last event before `SimulationEnded` when no agent was woken that way. Starting after the closing events keeps an in-run swap's wake, which looks the same, from cutting them out of the clone. A clone holding that notice rebuilds agents who remember the game ending, and they stop playing. The resumed clock then advances into a round the source never played (see below).
3. **Source agent collection**: `collect_source_agents` filters `AgentRegistered` events to those at or before the boundary timestamp, so each agent is pinned to the model it was running at the boundary. A boundary behind an in-run swap that already fired is refused earlier, by `refuse_boundary_with_swapped_seats`.
4. **Clone + truncate**: Same as replace-agent — `copy_run_at_event` copies the run directory and truncates the JSONL at the anchor's byte offset.
5. **JSONL rewrite**: The `run_id` is rewritten and `simulation_ended` lines are dropped; no message edits.
6. **Merged config**: `request.knobs` is shallow-merged onto the source's `scenario_config`. `round_count` is set to `after_round + rounds_after`. `model_overrides` pins every agent to its source-active registration. The merged config is written to `replace_config.json` and patched into the cloned JSONL's `SimulationStarted` event.
7. **Manifest**: Written as `replace_manifest.json` with `replaced_agent_id`, `replacement_model`, `replacement_provider` all `null`; `channels_with_visible_history` and `blocked_tool_call_channels` empty. `round_start` records the entry round and `rounds_after_swap` records `round_count - round_start` (the frozen on-disk schema).
8. **Subprocess launch**: `_pick_subprocess_default_model` picks the first source-active registration as the `--model`/`--provider` defaults (every agent has an explicit `model_overrides` entry, so these defaults are never read but `glossogen run` requires the flags). Subprocess runs detached.
9. **Resume-side reconstruction**: `resume_state_loader.load_resume_state` reads `replace_manifest.json`; when `replaced_agent_id is None`, calls `build_rewind_state_at_event(events, target_event_id, cutoff_round=None, agent_filters={})` and skips populating `replaced_agent_ids` / `replaced_agent_channel_visibility`. Every agent gets a full pass-through history.

### Crash Recovery of Forks

The manifest's anchor describes a fork that has not yet played. ``load_resume_state`` classifies what the log holds past that anchor. Agent re-registrations alone mean a launch that never got going, so the boundary anchor still applies. Play is the set of event types the agents themselves produce, which is exact by construction: history reconstruction reads precisely those types. Everything else is clock, world, or scenario lifecycle (a fresh ``RoundAdvanced(trigger="fork_after_round")``, delivered injections, a round that ended with no agent activity, a scenario's case events from ``on_round_advanced``), progress the anchor would replay, so recovery re-anchors at the log's end. The state walk keeps an injection only when a ``read_notifications`` result from the same agent and round contains its text; an unmatched delivery is sent again. It matches the delivery and read regardless of their log order because the runtime can return the read before persisting ``InjectionDelivered``. Play is also recovered at the log's end, with the replaced seat's seeding filters bounded to the rounds before the entry round so the replacement keeps its own text and thinking, and with its hidden channels re-anchored at the boundary (``ChannelVisibilityFromRound(entry_round)``) so the post-boundary messages it already saw stay visible. A played cross-run fork is refused instead: the imported agent's history is rebuilt exclusively from source B's events, so its post-boundary turns cannot be re-seeded. A cross-run run cannot itself be forked, for the same reason: its log holds the replaced-away agent's turns before the import boundary. A replace-agent run accepts only a re-replacement of the same seat, because the filters that hid its predecessor's turns live only in its manifest, which clones do not inherit. The same test refuses a boundary behind an already-fired ``scheduled_events`` swap, whose filters and swapped-in model live only in its config and ``AgentSwappedMidRun`` event.

Fork clones also carry no ``simulation_ended`` lines (the rewrite drops them) and no inherited derivation manifests (`fork_manifest.json`, `replace_manifest.json`, `cross_run_replace_manifest.json`, `imported_history_source.jsonl` are excluded from the copy; each flow writes its own). A stale end marker from a killed-then-recovered source would otherwise trip evaluation gates while the fork still runs, and an inherited cross-run manifest would win the resume dispatch and silently move the boundary.

### Forking After the Final Round

A completed run can be forked past its own end: `--after-round <final round>` requires an explicit `--rounds-after` (the default replays the source's remaining rounds, and a final-round fork has none). The clone then holds no `RoundAdvanced` for the entry round, so `load_resume_state` derives the difference from the log: an entry round at or behind the last advanced round means re-open (the shape every previously recorded manifest produces, and where recovery of an already-advanced fork lands), one past it means advance. `apply_fork_boundary` marks the state with `enter_round_by_advancing` and synthesizes the entry round's `channel_message_count_at_round_start` snapshot: without it, `ChannelVisibilityFromRound(entry_round)` on a later swapped-in agent would find no snapshot and silently grant full history. On resume the supervisor opens one round past the clone's last, and the game clock records the advance fresh as `RoundAdvanced(trigger="fork_after_round")`.

### Boundary-Round Event Ordering

The game clock's resume branch defers `deliver_round_injections` until after agent runners are launched and the boundary hook fires. The supervisor calls `dispatch_resume_boundary_events()` (which executes any `scheduled_events` bucketed at the entry round) then `deliver_initial_round_injections()`. This mirrors `_advance_round`'s normal order (boundary hook → injection delivery) so that when a `swap_agent` event fires exactly at the entry round, the round's injection lands in the post-swap session rather than the cancelled predecessor's queue.

The `RoundBoundaryScheduler` is pre-seeded from `RewindState.completed_scheduler_event_count_by_round`, a per-round count built by walking the loaded events for `AgentSwappedMidRun`, `PostmortemDisabledMidRun`, and `CaseInjectedMidRun`. The scheduler resumes at the first event not represented by that count, including when a run stopped between two events assigned to the same round.

### Inherited `scheduled_events` Semantics

The source's `scheduled_events` list is preserved unless overridden by `--knobs`. Events at `at_round <= after_round` never re-fire: the fork keeps those rounds as the source played them. An event at `after_round + 1` fires on resume, by design, because the cloned JSONL is captured before the source dispatched that boundary's scheduler events. Pass `--knobs '{"scheduled_events": [...]}'` to override the list (e.g. add a post-hoc swap at a later round, or clear the schedule entirely).

### Knob-Schema Evolution

When the scenario's knobs schema gained a required field after the source was created, validation will reject the merged config until the missing key is supplied. Pass it via `--knobs` for that fork. Example: veyru's `easy_round_numbers: frozenset[int]` was added later, so older veyru runs need `--knobs '{"easy_round_numbers": [1, 2, 3, 6, 13]}'` to fork.

### Key Modules

- `run_derivation/replace_agent.py` — shared core with `replaced_agent_id: str | None`; `_validate_replacement_payload`, `_pick_subprocess_default_model`, `collect_source_agents` (boundary-timestamp filtered), `find_boundary_timestamp`
- `run_storage/replace_manifest.py` — `ReplaceManifest` Pydantic model with nullable `replaced_agent_id` / `replacement_model` / `replacement_provider`
- `run_replay/resume_state_loader.py` — `load_resume_state` (dispatches on the manifests present), `read_replace_manifest_info` / `read_cross_run_manifest_info` (projections carrying `entry_round`), `apply_fork_boundary` (advance derivation + snapshot synthesis)
- `runtime/game_clock.py` — `dispatch_resume_boundary_events()` + `deliver_initial_round_injections()`; `start_initial_round`'s resume branch delivers no injections inline, and records the fresh `RoundAdvanced` when `advance_on_resume` is set
- `runtime/scheduler.py` — `RoundBoundaryScheduler(events, completed_event_count_by_round)` resumes each round after its recorded completed-event count
- `run_replay/message_rewind.py` — `RewindState.completed_scheduler_event_count_by_round` and `RewindState.enter_round_by_advancing`
- `runtime/autonomous_supervisor.py` — pre-seeds the scheduler from `resume_state.completed_scheduler_event_count_by_round`, opens one round past the clone's last when advancing, and calls `dispatch_resume_boundary_events` + `deliver_initial_round_injections` after agent runners launch
- `cli/derivation_commands.py` — `handle_fork_at_round` handler and the `fork-at-round` argparse parser
- `run_storage/run_summary_models.py` — `ForkAtRoundSource`
- `run_storage/derivation_manifest_reader.py` — `read_fork_at_round_source` (returns `None` when the manifest's `replaced_agent_id` is non-null); `read_replace_agent_source` returns `None` when it is null so a single manifest never surfaces under both fields. Both translate the stored window to `after_round` / `rounds_after`

### Provenance

Fork-at-round runs store a `replace_manifest.json` with `replaced_agent_id=null` (the discriminator). Discovery reads `read_fork_at_round_source` which returns a `ForkAtRoundSource { source_run_id, after_round, rounds_after, target_event_id, forked_at }` on `RunSummary` / `RunDetailResponse` as `fork_at_round_source`. The frontend renders a green "↺ Forked after round N (+K)" badge in the run-detail header (links back to `source_run_id`) and a green chip in the runs-list row.

### Multi-Swap Navigation

Runs with `scheduled_events` (in-run swaps), whether direct or via post-hoc fork-at-round inheritance, render one `AgentSwapPointFab` per `AgentSwappedMidRun` event. Each FAB scrolls to its `agent-swap-divider-r{N}-{agent_id}` anchor. The stack capacity is 8 to accommodate multi-phase protocol-transmission runs.

## In-Run Agent Swaps (Round-Boundary Scheduler)

The in-run scheduler swaps one agent's seat for a fresh instance at scheduled round boundaries inside a single live simulation. Multiple swaps can fire across the same run; a run with three swaps produces four phases (A → B → C → D) on one continuous timeline.

### Knobs Surface

`BaseKnobs.scheduled_events: list[ScheduledEvent]` is a discriminated Pydantic union. Two variants:

```jsonc
{ "type": "swap_agent", "at_round": 16, "agent_id": "field_observer",
  "model": "claude-sonnet-4-6", "provider": "anthropic",
  "channel_visibility": { "link": { "kind": "from_round", "round_floor": 16 } } }

{ "type": "set_postmortem", "at_round": 16, "enabled": false }
```

`channel_visibility` is itself a discriminated union (`Full` / `None` / `FromRound(round_floor)`), the same shape used by replace-agent's per-channel visibility and by the history reconstruction filter.

### Swap Flow

1. **Round boundary fires** in `RoundBoundaryScheduler` (driven by the game clock's `signal_round_advanced`). The scheduler dispatches every event whose `at_round` matches.
2. **`SwapAgent` dispatch** calls `execute_agent_swap` in `runtime/agent_swap.py` with an `AgentSwapResources` bundle (runtime, runner factory, runner-task table, log path, run dir, cost tracker).
3. **Drain old runner**: push `DoneNotification(reason="agent_swap")` to the existing `AgentSession`; wait `SWAP_RUNNER_GRACE_SECONDS`; force-cancel on timeout.
4. **Compose effective channel visibility**: query `runtime.scenario.get_world().get_globally_disabled_channels()` and force `ChannelVisibilityNone` for each (so a previously-disabled channel like Veyru postmortem can never bleed into the new agent's view, even if the swap config didn't explicitly list it).
5. **Rebuild seed history** by replaying the live JSONL through `build_message_history` with `cutoff_round=at_round`, `tool_calls_only=True`, and the effective channel visibility. The same builder produces the notification round-floor filter automatically (see below).
6. **Apply `member_join_index`** on the channel router via `compute_per_channel_join_index` so the swapped-in agent's `read_channel` calls only see post-window content.
7. **Replace `AgentSession` and `AgentConfig`** on the runtime (new system prompt + reconstructed `initial_message_history`). Persist the seed history to `resume_context_<agent_id>_round_<R>.json` for inspection.
8. **Spawn fresh runner** via the supplied factory; wake it via `NewMessagesNotification` on every channel it can still read (excluding globally disabled ones).
9. **Notify the world** via `ScenarioWorld.on_agent_swapped_mid_run(agent_id, round_number)` so scenarios can suppress prior-round injection content for the just-swapped agent (e.g. Veyru drops the `--- PREVIOUS VEYRU RESULT ---` block on the swap-round injection — the new agent didn't participate in the round being summarised).
10. **Emit `AgentSwappedMidRun`** event to the JSONL.

`SetPostmortem` dispatch calls a scenario-provided method on the world (Veyru exposes `disable_postmortem_globally`) and emits `PostmortemDisabledMidRun`. Scenarios opt in to global channel disablement by overriding `get_globally_disabled_channels()` to return the channel IDs closed for the rest of the run.

### `ScenarioWorld` ABC Hooks

The base `ScenarioWorld` exposes two hooks for the in-run swap flow, both no-op by default:

- `get_globally_disabled_channels() -> frozenset[str]` — channel IDs the runtime treats as dead for any swapped-in agent. The swap logic forces `ChannelVisibilityNone` on these and excludes them from the wake-up notification.
- `on_agent_swapped_mid_run(agent_id, round_number)` — invoked after a fresh agent is instantiated. Scenarios use this to suppress injection content the swapped-in agent should not see. Veyru tracks `_just_swapped_agent_round[agent_id]` and drops the `--- PREVIOUS VEYRU RESULT ---` block on that round's injection.

### Notification Round-Floor Filter

`read_notifications` is not channel-scoped, so its tool returns are not filtered by `channel_visibility`. The predecessor's `read_notifications` returns carry round-start injection text (e.g. `--- PREVIOUS VEYRU RESULT ---`), which would land in the swapped-in agent's seed history even when channel windowing is in effect.

`run_replay/message_history_builder.py` derives a notification round floor from the `channel_visibility` config: `min(v.round_floor for v in channel_visibility.values() if isinstance(v, ChannelVisibilityFromRound))`, or `None` when no channel uses `FromRound`. `read_notifications` calls whose source `ToolCallInvoked.round_number` falls below the floor are dropped, in both the parented-cycle and orphan-cycle paths.

The filter applies to every caller that builds an agent history with a `FromRound` entry: replace-agent, fork, cross-run, and in-run swap.

### Per-Swap Resume Context Files

`write_swap_resume_context_file` writes one `resume_context_<agent_id>_round_<R>.json` per swap into the run directory. The filename includes the round number so multiple swaps in the same run keep separate files. The payload mirrors the replace-agent `resume_context_<agent_id>.json` shape and captures the swapped-in agent's pydantic-ai message history at swap time for audit.

### Key Modules

- `models/channel_visibility.py` — `ChannelVisibility` discriminated union (`Full` / `None` / `FromRound`)
- `models/scheduled_events.py` — `SwapAgent`, `SetPostmortem`, `InjectCase`, `ScheduledEvent` discriminated union
- `runtime/scheduler.py` — `RoundBoundaryScheduler` and the `SchedulerOps` Protocol
- `runtime/agent_swap.py` — `AgentSwapResources` named tuple + `execute_agent_swap`
- `scenario_contract/scenario_world.py` — `get_globally_disabled_channels()` and `on_agent_swapped_mid_run()` ABC hooks
- `models/event.py` — `AgentSwappedMidRun`, `PostmortemDisabledMidRun` event types
- `run_replay/message_history_builder.py` — notification round-floor derivation + filter
- `run_replay/resume_context_writer.py` — `write_swap_resume_context_file`
- `evaluation/metrics/round_success_after_resume_metric.py` — walks every `AgentSwappedMidRun` event and emits one Measurement per anchor (named `round_success_after_resume_round_<R>_<agent_id>`); the in-run baseline window is the previous phase in the same run

### FE Per-Agent-Instance Tabs

The run viewer derives one `AgentInstance` per `(agent_id, generation)` from `agents` + `agent_swap_events` on the run-detail response. Single-instance agents render a flat sidebar row. Multi-instance agents render a parent role row with indented `Gen k · rA-B` sub-rows; the latest generation pulses green on live runs. Per-instance drawer tabs filter messages by round range and show round-banner dividers. The chat pane renders a dashed indigo `agent-swap-divider` between adjacent rounds that straddle a swap event.

`server/runs/models.py` exposes `AgentSwapEventDTO` and a `agent_swap_events: list[AgentSwapEventDTO]` field on `RunDetailResponse`. `server/runs/detail_reader.py` populates it from the JSONL events.

### Provenance

In-run swap runs carry no manifest file. The `AgentSwappedMidRun` events in the JSONL are the source of truth. Run discovery and detail endpoints surface swaps via the `agent_swap_events` field on `RunDetailResponse`.

## Evaluation System

After a simulation completes, the evaluation system analyzes the JSONL log via a uniform `Metric` abstraction. Both deterministic metrics and LLM-as-judge metrics implement `Metric.compute(...)` and return one or more `Measurement` instances.

**CLI**: `python -m glossogen evaluate <scenario> --run-dir ./runs/<scenario>/<timestamp> --metrics language_strangeness,perplexity --model MODEL`

The user selects which metrics to run. They are not automatically applied.

**Generic metrics** (available to all scenarios). LLM judges scope each to a specific phenomenon; their prompts explicitly exclude what the other metrics cover, preventing overlap:

- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style (LLM judge)
- `slang_emergence` — informal register shifts, colloquial expressions, casual nicknames (LLM judge)
- `neologism` — genuinely invented words with new meanings (LLM judge)
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding (LLM judge)
- `round_ended_idle` / `round_ended_timeout` — count rounds whose main phase ended via the `all_agents_idle` or `round_timeout` trigger (deterministic, reads `RoundEnded.trigger`)
- `content_filter_refusal` — counts LLM content-filter refusals across the run with per-round + per-agent breakdowns (deterministic, scans `AgentRunCycleFailed` events)
- `perplexity` — mean per-token surprisal (in nats) of primary-channel messages under a fixed `gpt2` language model loaded via `minicons.IncrementalLMScorer`. Scoping uses `scenario.get_primary_channels()` so the metric stays scenario-agnostic (Veyru returns `#link`; scenarios without a primary channel get a no-op result). The score is the overall mean nats; `per_round` carries mean+std+message_count per round. No LLM judge.
- `mean_chars_per_round` — total characters of all primary-channel messages summed per round, then averaged across every positive-numbered round in the log, a silent round counting as zero. Same scoping rule as `perplexity`. The score is the mean of per-round totals; `per_round` lists each round's total chars + message count. The headline channel-utilization number; in Veyru this is exactly the unit that ``time_budget_seconds`` is denominated in. No LLM judge.
- `mean_chars_per_message` — characters per individual primary-channel message, averaged across all messages in the run (flattened, not mean of round means). Same scoping rule as `perplexity`. The score is the overall mean chars/message; `per_round` carries per-round mean+std+message_count. Normalizes MCR by message count, isolating per-message verbosity from message density — MCR is biased upward by rounds that simply need more back-and-forth. No LLM judge.

The LLM-judge metrics (`language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes`, `protocol_learned_after_swap`, `communication_open_coding`, `communication_feature_presence`) share a common flow: build per-round transcripts from `MessageSent` events (LLM-judge metrics that need ground-truth per-round case state go through `scenario.build_communication_rounds(events)` instead), render a Jinja2 prompt, call the LLM judge with a structured output schema (returning `per_round_notes: list[RoundNote]` or similar), and turn each note into a `RoundObservation`. The deterministic metrics skip the prompt+LLM step entirely.

**Scenario-specific metrics:** there are no scenario-private metric classes any more. Every scoring concept (round success, post-swap re-scoring, communication-feature analysis, protocol probing) is platform code that consumes scenario data through hooks on `SimulationScenario`:

| Platform metric | Required scenario hook |
|---|---|
| `round_success`, `round_success_after_resume` | `judge_round_result(round_number, trigger) -> list[RoundResult]` |
| `protocol_learned_after_swap` | `detect_protocol_boundary_window(...)` + `build_communication_rounds(events)` |
| `communication_open_coding`, `communication_feature_presence` | `build_communication_rounds(events)` |
| `protocol_probe`, `protocol_probe_*_similarity`, `protocol_probe_cutoff_trajectory` | `get_protocol_probe_config()` |

A scenario that does not implement a given hook returns `[]` from the corresponding metric and the measurement is simply absent from the report. There is no zero-score sentinel.

**No automatic labels**: Metrics no longer write `eval:*` labels into `labels.json`. Filter on `score` or on the `per_round` / `per_agent` lists directly.

**Output**: A JSON report with structured measurements:

```json
{
  "simulation_id": "...",
  "scenario_name": "...",
  "measurements": [
    {
      "metric_name": "language_strangeness",
      "score": 12.0,
      "score_unit": "rounds with non-standard language (out of 15)",
      "summary": "12/15 rounds contained non-standard language ...",
      "per_round": [
        {"round_number": 3, "value": 1.0, "note": "telegraph-style: dropped articles, ..."},
        {"round_number": 5, "value": 1.0, "note": "..."}
      ],
      "per_agent": []
    }
  ]
}
```

The evaluation system reuses the same LLM provider layer (ClaudeProvider) for judge calls.

## Web Server

A FastAPI backend exposes simulation data via REST endpoints. The frontend consumes these endpoints through a typed API client.


### Architecture

- Postgres holds tenancy + the runs index (`groups`, `runs`, `user_last_active_group`, OAuth tables). Run bodies (JSONL event log, manifests, eval reports) stay on disk under `GLOSSOGEN_RUNS_DIR`. A request resolves a run via the DB lookup keyed on `(group_id, scenario, run_dir_name)` and only then opens files on disk; cross-tenant access is structurally impossible because the DB query is the gate.
- `DATABASE_URL` is optional: unset, the backend runs in no-database local mode (runs index from the filesystem, OAuth state in memory). It becomes required once an identity provider is installed, since resolving a group slug needs Postgres. Migrations run via `alembic upgrade head` at container start before the server begins accepting requests.
- `GLOSSOGEN_RUNS_DIR` configures the on-disk runs root.
- CORS origins are read from `ALLOWED_ORIGINS` (comma-separated). Defaults to `http://localhost:3000`.
- Authentication is handled by `IdentityMiddleware` (pure ASGI, so SSE streams pass through without buffering). It asks the installed provider to verify the credential, or falls back to an MCP OAuth access token, then attaches an `Identity(user_id, active_group_id, is_local_mode)` to `request.state`. See [Multi-Tenancy & Authentication](#multi-tenancy--authentication).
- Every endpoint declares a `response_model` and returns a Pydantic model instance. No dicts or strings are returned.
- Status-like fields use enums (`HealthStatus`, `RunStatus`) instead of bare strings. `RunStatus` includes `IN_PROGRESS` for runs that have not yet completed.
- The run detail endpoint returns separate `messages` (ChannelMessage) and `reasoning` (ReasoningEntry) arrays, plus `debug_logs` (DebugLogEntry) parsed from the debug JSONL file.

### Multi-Tenancy & Authentication

One organization in the installed identity provider corresponds to one glossogen **group**. Every run is owned by exactly one group; runs are never visible across groups except via the export/import bundle flow (`glossogen push-to-prod`).

#### Two operating modes

- **Single-tenant mode**: no provider installed. On startup `ensure_local_group(pool)` upserts a synthetic `(slug='local', name='Local', external_org_id=NULL)` row plus a `user_last_active_group` entry for the synthetic `local-user`. `IdentityMiddleware` short-circuits every request to that identity. The frontend's auth adapter answers "not configured" to every slot, so `proxy.ts` is a pass-through and no sign-in UI mounts. The landing page's Dashboard link points at `/g/local/runs` (`LOCAL_GROUP_SLUG` in `frontend/src/shared/lib/local-tenant.ts`), and `<GroupProvider>` takes the slug from that URL as in multi-tenant mode.
- **Multi-tenant mode**: a provider installed on the backend and an auth adapter overlaid on the frontend. The adapter's proxy delegate gates routes; the backend asks the provider to verify the credential against the URL slug.

#### URL slug as source of truth

REST routes are prefixed `/api/g/{group_slug}/...`. Frontend pages live under `/g/[groupSlug]/...`. The slug *in the URL* declares which group the request operates on; the bearer token *proves* the user is allowed to do so. This shape lets a user belonging to several groups open them in parallel browser tabs, provided the adapter activates the URL's group server-side on each navigation.

#### `IdentityMiddleware`

Pure ASGI (not `BaseHTTPMiddleware`, so SSE streams pass through unbuffered). Lives in [`src/glossogen/server/identity/middleware.py`](src/glossogen/server/identity/middleware.py). Per request:

1. Unauthenticated paths (`/api/health`, `/api/server-config`, `/.well-known/oauth-*`, `/mcp/...`, plus whatever prefixes the provider declares) skip the check.
2. Local mode: attach the synthetic local `Identity`.
3. Multi-tenant mode: extract the bearer (header, or `?token=` for SSE) and hand it to `provider.resolve_identity`. On a 401 rejection, fall back to verifying it as an MCP OAuth access token — that's how a CLI token authenticates `/api/g/<slug>/runs/import` calls. A 403 is not retried, because re-reading a recognised credential cannot change that answer.
4. Parse the slug from the URL via `_GROUP_SLUG_PATTERN = ^/(?:api|mcp)/g/([a-zA-Z0-9_-]+)` and resolve it to a `groups` row *before* calling the provider, so a provider never queries that table itself. An OAuth token must match the row's id.
5. Resolve the group row from Postgres; attach `Identity` to `request.state`.

How a credential is verified is entirely the provider's business; the platform never inspects one. The loader that finds the provider refuses to boot on ambiguity (two declared, or one declared under an unread contract version), because falling back to no provider would serve every request unauthenticated. The scenario and metric loaders warn and continue in the same situation, since there an unreadable declaration only costs a missing feature ([`identity_provider_loader.py`](src/glossogen/server/identity/identity_provider_loader.py)).

#### Postgres schema

Tooling: alembic for migration scheduling, raw SQL via `op.execute("""...""")` inside each revision, psycopg3 async in application code. Connection pool via `psycopg_pool.AsyncConnectionPool`. Query helpers in [`src/glossogen/db/queries.py`](src/glossogen/db/queries.py) return Pydantic rows (`GroupRow`, `RunRow`, `UserLastActiveGroupRow`, `PendingConsentRow`); no raw dicts cross the boundary.

| Table | Purpose |
| --- | --- |
| `groups` | Authoritative locally so a `group_id` never dangles if the external organization is deleted. `(id UUID PK, external_org_id TEXT UNIQUE NULL, slug TEXT UNIQUE NOT NULL, name TEXT, created_at)`. `external_org_id` is NULL for the synthetic `local` group. |
| `runs` | Postgres-indexed mirror of filesystem run identity. `(group_id → groups, scenario, run_dir_name, status, created_at, created_by_user_id NULL, source_run_scenario NULL, source_run_dir_name NULL, labels NULL)`. Unique `(scenario, run_dir_name)`; index `(group_id, created_at DESC)` for the list endpoint. |
| `user_last_active_group` | `(user_id PK, group_id, updated_at)`. |
| OAuth (`oauth_clients`, `authorization_codes`, `access_tokens`, `refresh_tokens`) | All token rows carry `group_id`. |
| `pending_oauth_consents` | `(request_id PK, client_id, scopes, code_challenge, redirect_uri, …, expires_at)` — multi-tenant authorize parks its parameters here keyed by an opaque `request_id` while the user is on the consent page. |

Memberships are deliberately *not* mirrored. The JWT's active `org_slug` claim is the source of truth, which avoids the "user added but webhook hasn't fired" sync window.

#### Provider → DB sync

Keeping `groups` in step with an external directory is the provider's job: it contributes its own webhook router and declares that path unauthenticated, since its identity service calls it rather than a signed-in user. The platform supplies `upsert_group` and `soft_delete_group_by_external_org_id`; the soft delete preserves the row so `runs.group_id` foreign keys stay valid.

#### Lookup + listing

- [`server/runs/lookup.py`](src/glossogen/server/runs/lookup.py): `get_identity(request)`, `resolve_run_or_404(request, scenario, run_dir_name)` (DB lookup keyed on `(group_id, scenario, run_dir_name)` before touching disk), and `register_new_run(request, scenario, run_dir_name, status, source_*)` (called from every place that creates a new run on disk — fork, replace-agent, cross-run, fork-at-round, import, CLI).
- [`server/runs/listing.py`](src/glossogen/server/runs/listing.py): `list_runs_for_group(request, scenario_filter)` queries Postgres for the group's runs, then enriches each row by reading the on-disk summary cache (or scanning the JSONL on a miss).
- [`server/runs/label_mirror.py`](src/glossogen/server/runs/label_mirror.py): a run's `labels.json` is the source of truth for its labels, and `runs.labels` is a mirror the label union and label filtering read instead of opening one file per run. Rows never mirrored (`labels IS NULL`) are backfilled at startup. Orchestrator scripts write the file without going through the server, so drift is repaired wherever the server reads the file anyway: the listed page's rows and a run's detail.

#### CLI tenancy surface

- `glossogen run` accepts `--group-slug` (default `local`); the launcher inserts a `runs` row with that ownership after `claim_run_dir`.
- `glossogen login --url <remote>` ([`oauth_client.py`](src/glossogen/prod_sync/oauth_client.py)) walks the OAuth flow against a remote backend, opening the user's browser to the consent page; the loopback HTTP server collects the authorization code, exchanges it for tokens, calls `/mcp/whoami` to discover the bound group, and writes `~/.glossogen/credentials.json` (mode 0600).
- `glossogen push-to-prod` ([`prod_push.py`](src/glossogen/prod_sync/prod_push.py)) bulk-uploads matching local runs to the configured remote via `/api/g/<slug>/runs/import`. Supports `--label` (AND), `--scenario`, `--include-incomplete`, `--dry-run`, `--concurrency` (default 1; the import endpoint is idempotent on `run_id` so re-running is safe).
- `glossogen sync-metadata-to-prod` ([`prod_metadata_sync.py`](src/glossogen/prod_sync/prod_metadata_sync.py)) handles local runs the remote already has. It PUTs the local labels onto `/api/g/<slug>/runs/{scenario}/{run_dir_name}/labels` when the lists differ, and the local evaluation report onto `.../evaluation` when its measurements hash differs from the remote's `evaluation_content_hash` or the remote has none. It also PUTs every local label description the remote is missing or records differently onto `/api/g/<slug>/labels/descriptions`; descriptions only the remote has are left alone. Runs missing from the remote are skipped; `push-to-prod` is for those.

### MCP Runs Browser

An MCP server is mounted at `/mcp` on the FastAPI backend, providing programmatic access to simulation data and run launch flows for LLM clients (Claude Code, Cursor). Uses `FastMCP` with Streamable HTTP transport; the sub-app is wrapped by `McpRunContextMiddleware` ([`server/mcp/asgi_context.py`](src/glossogen/server/mcp/asgi_context.py)) which reads the bearer token, recovers the bound `group_id` from the OAuth storage, and primes a `RunContext` contextvar so every tool runs scoped to that group. Requires `OAUTH_ISSUER_URL` to be set; the MCP endpoint is disabled if unset.

The MCP server exposes these tools:

| Tool                   | Description                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------ |
| `list_scenarios`       | Lists available scenarios with knobs files, metrics, and supported models/providers              |
| `list_runs`            | Paginated run listing with filtering by scenario, model, fork status, and run status             |
| `get_run_metadata`     | Lightweight metadata for a single run: agents, channels, configuration, evaluation summary       |
| `list_derived_runs`    | Lists runs derived from a parent (replace-agent, fork-at-round, cross-run) with derivation type, round boundaries, swapped/imported models, and headline `round_success` scores |
| `get_run`              | Full run content with messages; opt-in sections for reasoning, tool use, debug logs, system prompts; filtering by agent or channel |
| `get_knobs_schema`     | Returns a scenario knobs JSON Schema (field types, enums, descriptions) and available presets    |
| `get_knobs_preset`     | Loads a knobs preset JSON payload for a scenario                                                  |
| `start_run`            | Launches a simulation subprocess with scenario, model, provider, and optional knobs               |
| `export_run_artifacts` | Returns a download URL for a tar.gz bundle of the run's artifacts                                |
| `export_agent_thread`  | Reconstructs one agent's thread (optional exclusive `cutoff_round`) and returns a drop-in provider-native request body (Anthropic Messages / OpenAI Chat); `output_format` defaults to the agent's own provider |

All tools return structured JSON via Pydantic response models. `list_runs` and `get_run` support pagination. `get_run` uses flags (`with_reasoning`, `with_tool_use`, `with_debug_logs`, `with_system_prompts`) to control which sections are included. `export_agent_thread` is a thin wrapper over `thread_export.export_agent_thread_from_run_dir`, the same code behind `glossogen export-thread` and the `/runs/{scenario}/{run_dir_name}/agents/{agent_id}/thread` REST endpoint.

For run launch from MCP clients, a typical flow is:
1. `get_knobs_schema` to inspect available fields and preset names.
2. `get_knobs_preset` to load a baseline knobs payload.
3. `start_run` with model/provider and any knob overrides.

The MCP server reuses the same data layer as the REST API (`discover_runs()`, `load_run_detail()`) and shares simulation launch helpers with the REST start endpoint (`run_launcher.py`). Run ID parameters accept unique prefixes (e.g., first 8 characters) for convenience.

#### MCP OAuth Authentication

The MCP endpoint uses OAuth 2.0 with PKCE for authentication. The `/mcp` path is excluded from `IdentityMiddleware`, because MCP carries OAuth tokens rather than session credentials, and authentication is enforced by the MCP library's `BearerAuthBackend` against the OAuth provider's token storage.

The OAuth flow:

1. **Discovery**: Clients fetch `/.well-known/oauth-protected-resource` (RFC 9728) for the authorization server, then `/.well-known/oauth-authorization-server` (RFC 8414) for endpoint URLs. Both are served at the host root because the MCP sub-app is mounted at `/mcp`.
2. **Client registration**: `POST /mcp/register` (RFC 7591 dynamic client registration). `client_id` + `client_secret` are stored in the `oauth_clients` Postgres table.
3. **Authorization**: `GET /mcp/authorize` with PKCE `code_challenge`.
   - **Single-tenant mode** (no identity provider): the OAuth provider auto-approves and mints an authorization code bound to the synthetic `local` group.
   - **Multi-tenant mode**: the OAuth provider parks the parameters as a `pending_oauth_consents` row (migration `0003_pending_oauth_consent`) keyed by an opaque `request_id`, then redirects the browser to `provider.deferred_consent_url(request_id)`, which is `{FRONTEND_URL}/mcp-consent?request_id=<id>`. That page's shell renders the auth adapter's `ConsentGate`, which signs the user in and settles which group is being authorized; the platform's consent panel then POSTs `/mcp/consent/approve` with a session token. That endpoint is contributed by the identity provider, which verifies the caller and calls [`provider_services.approve_parked_consent`](src/glossogen/server/identity/provider_services.py) to mint the code, returning the OAuth-client redirect URL. The wrapper is what a provider calls: it reads the OAuth provider off `app.state` so a provider never reaches into it, and it translates the MCP library's `AuthorizeError` into `ConsentNotApprovable` so handling an expired link needs no `mcp` import. That exception means the link expired, was already used, or its OAuth client is gone: the provider answers it with a 4xx, not a server error. The frontend `window.location` redirects there, completing the loop with the MCP client. The parking machinery itself is platform code, because deferring consent is about having more than one group to choose from rather than about any one vendor.
4. **Token exchange**: `POST /mcp/token` exchanges the authorization code for an access token (1 hour) and refresh token (30 days). Both rows carry `group_id` so the binding is preserved across refresh.
5. **Authenticated requests**: Bearer token in the `Authorization` header. `McpRunContextMiddleware` resolves the token to its `group_id` and primes `RunContext` before the tool body runs.

`IdentityMiddleware` also accepts MCP OAuth tokens as a Bearer fallback on `/api/g/<slug>/...` REST routes, so the same token issued to the CLI works for both MCP tool calls and REST imports.

Implementation:
- [`server/mcp/oauth_provider.py`](src/glossogen/server/mcp/oauth_provider.py) — `GlossoGenOAuthProvider` implementing `OAuthAuthorizationServerProvider`; parks consents when a provider is installed and materialises codes via `approve_pending_consent`, which providers reach through `provider_services.approve_parked_consent` rather than directly.
- [`server/mcp/whoami_router.py`](src/glossogen/server/mcp/whoami_router.py) — `GET /mcp/whoami` (OAuth token auth, used by the CLI to discover its bound group). `POST /mcp/consent/approve` is contributed by the identity provider.
- [`server/mcp/oauth_storage.py`](src/glossogen/server/mcp/oauth_storage.py) — psycopg3 async Postgres storage for clients, codes, tokens, and pending consents.
- [`server/mcp/asgi_context.py`](src/glossogen/server/mcp/asgi_context.py) — primes `RunContext`.
- [`frontend/src/app/mcp-consent/`](frontend/src/app/mcp-consent/) — the consent page. A shell: the auth adapter's `ConsentGate` settles which group is being authorized, and [`features/mcp-consent/consent-panel.tsx`](frontend/src/features/mcp-consent/consent-panel.tsx) carries the copy and the Approve button.
- CLI surface ([`src/glossogen/prod_sync/oauth_client.py`](src/glossogen/prod_sync/oauth_client.py) + [`src/glossogen/prod_sync/prod_push.py`](src/glossogen/prod_sync/prod_push.py)): `glossogen login` walks the OAuth flow against a remote, learns `group_slug` from `/mcp/whoami`, and stores `{access_token, refresh_token, group_slug}` in `~/.glossogen/credentials.json`; `glossogen push-to-prod` bulk-uploads local runs to `/api/g/<slug>/runs/import` using the stored token.

The frontend includes an MCP integration modal (accessible via the **MCP** button on the runs page) that shows connection instructions for Claude Code and Cursor.

### Frontend

- **Stack**: Next.js 16 (App Router), React 19, TypeScript (strict mode), Tailwind CSS v4
- **Data fetching**: TanStack React Query with openapi-fetch for type-safe API calls. In-progress runs auto-refresh every 5 seconds (configurable via a Stop/Resume button).
- **Type generation**: `openapi-typescript` generates TypeScript types from the backend's OpenAPI schema. CI enforces that generated types stay in sync with the backend.
- **Lint enforcement**: ESLint forbids raw `fetch()` — all API calls must go through the typed client at `@/shared/lib/api-client`. This ensures compile-time validation of request paths, parameters, and response types.
- **Auth + tenancy**:
  - [`features/auth/auth-adapter.ts`](frontend/src/features/auth/auth-adapter.ts) is the contract the platform reads identity through; [`features/auth/adapter/`](frontend/src/features/auth/adapter/) holds the implementation, and a deployment needing different authentication replaces that directory. Four modules, one per runtime that imports them: `proxy.ts`, `server.ts`, `browser.ts`, `client.tsx`.
  - [`frontend/src/proxy.ts`](frontend/src/proxy.ts) (Next.js 16's renamed `middleware.ts`) delegates to the auth adapter's handler, or passes through when there is none. Its `matcher` stays a literal in that file because Next.js reads it statically. An adapter typically uses the delegate to activate the URL's group on the session for the current request, which is what lets a user switch groups by URL alone.
  - All authenticated pages live under [`app/g/[groupSlug]/`](frontend/src/app/g/[groupSlug]/); the active slug threads through React via [`GroupProvider`](frontend/src/features/auth/group-context.tsx) and `useActiveGroupSlug()`.
  - Standalone routes, each a shell rendering one adapter component: [`/sign-in`](frontend/src/app/sign-in/[[...rest]]/page.tsx) / [`/sign-up`](frontend/src/app/sign-up/[[...rest]]/page.tsx) (catch-all, so a provider's internal flow URLs resolve), [`/select-org`](frontend/src/app/select-org/page.tsx) for signed-in users with no active group, [`/mcp-consent`](frontend/src/app/mcp-consent/page.tsx) for the OAuth consent loop.
  - The API client at [`shared/lib/api-client.ts`](frontend/src/shared/lib/api-client.ts) calls `session.getToken({ skipCache: true })` per request and substitutes `{group_slug}` in the URL template with the active slug. `skipCache: true` matters: without it, a token minted before `setActive` returns with `org_slug=null` and every `/api/g/<slug>/...` call 403s.
- **Lineage badges**: derived runs (replace-agent, cross-run replace-agent, fork-at-round, legacy fork) display a badge in the run-detail header linking to the source run, plus floating-action buttons in the chat pane to scroll to each lineage event. Simulations are launched from the CLI (or via the MCP `start_run` tool); the frontend is a read-only viewer.

