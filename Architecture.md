# Schmidt-POC Architecture

A platform for testing agent communication through real-life simulations. LLM-based agents interact via MCP tools exposed by a central runtime. Agents are processes launched via the Pydantic AI framework that connect to a shared MCP server. A game clock manages round progression and injection delivery. No centralized turn control.

A web UI exposes simulation runs and evaluation results through a FastAPI backend and Next.js frontend.

## Design Decisions


| Decision            | Choice                                                       |
| ------------------- | ------------------------------------------------------------ |
| LLM Backend         | Pydantic AI (supports Anthropic, OpenAI, Ollama, self-hosted OpenAI-compatible endpoints) |
| Transport           | MCP over Streamable HTTP (agents are external processes)     |
| Scenario Definition | Python classes                                               |
| Agent Autonomy      | Agents decide when to speak; no central turn controller      |
| Round Advancement   | Hybrid: all-agents-idle OR round timeout                     |
| Channels            | Scenario-defined channels with membership lists              |
| Agent Runtime       | Pydantic AI with MCP toolsets (pluggable runner protocol)    |
| Coordination        | Reaction delays + per-channel write locks                    |
| Agent Framing       | Agents do not know they are in a simulation; MCP server named "comms", tools feel like Slack |
| Observability       | Structured JSONL log (one file per run)                      |
| Run Storage         | Filesystem: `runs/{scenario}/{unix_timestamp}/`              |
| End Conditions      | Scenario-defined round count + max round duration            |
| Entrypoint          | CLI (`python -m schmidt run|evaluate|serve|replace-agent|cross-run-replace-agent`)   |
| Metrics             | Post-hoc LLM-as-judge, user-selected evaluators, JSON report |
| Web Server          | FastAPI with structured Pydantic response models             |
| Frontend            | Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4   |
| API Client          | openapi-fetch with generated types from OpenAPI schema       |
| Data Fetching       | TanStack React Query                                         |
| MCP Runs API        | FastMCP mounted at `/mcp` on the FastAPI server (Streamable HTTP) |
| MCP Authentication  | OAuth 2.0 with PKCE and dynamic client registration (MCP library built-in) |
| MCP Token Storage   | SQLite via aiosqlite (`$SCHMIDT_RUNS_DIR/oauth.db`)              |



## Simulation Flow

1. **CLI** parses arguments in two passes (first to identify the scenario, then to parse known flags plus `key=value` overrides). Builds the scenario, agent configs, event logger, and agent runner. Passes everything into the `AutonomousSupervisor`.
2. **AutonomousSupervisor.run()** opens the event logger, builds per-agent `AgentSession` objects, creates the `SimulationRuntime` (FastMCP server), and wires a `GameClock`. Logs `SimulationStarted` and one `AgentRegistered` event per agent.
3. **MCP server starts** on a configured port, exposing the `comms` MCP server. Agent runners are launched as concurrent asyncio tasks, each starting an external Claude Code process connected to the MCP server URL.
4. **Game clock triggers round-1 injection delivery** through `runtime.deliver_round_injections(1)`, which pushes `NewInfoNotification` messages to agent session queues. Agents receive these via the `read_notifications` MCP tool and begin interacting.
5. **Agents act autonomously** by calling MCP tools: `read_notifications` (blocks until a notification arrives), `read_channel` (fetches recent messages), `send_message` (posts to a channel), `list_channels` (discovers available channels), and `get_channel_members` (sees who is in a channel). There is no central turn controller.
6. **Round advancement** uses a hybrid condition. The game clock polls at 500ms intervals and advances the round when either (a) all agents are idle (blocked on `read_notifications` with empty queues) *and* at least 5 seconds have passed since the last message, or (b) the round duration exceeds `max_round_duration_seconds` since the last message. When a round advances, the clock bumps `runtime.current_round`, logs `RoundAdvanced`, and calls `runtime.deliver_round_injections(round_number)` to push that round's injections.
7. **Termination** occurs when the game clock reaches `max_rounds`. The runtime broadcasts a `DoneNotification` to all agents, waits up to 120 seconds for agent tasks to finish, and logs `SimulationEnded` with total message count.

## Simulation Runtime

`SimulationRuntime` is the shared-state container that the game clock, MCP tools, world context, scenarios, and runners all interact with. It owns the channel router, per-agent sessions, agent tool allowlists, the world context, and the active round number (`current_round`, written by the game clock via `set_current_round`, seeded by the supervisor on resume). It also owns injection delivery: `deliver_round_injections`, `deliver_postmortem_injections`, and `has_postmortem_for_round` look up scenario-defined injection content, push it to agent sessions, and emit the corresponding `InjectionDelivered` / `PostmortemStarted` events. Resume bookkeeping (`_last_injected_rounds`) lives on the runtime and is seeded via `seed_last_injected_rounds`.

Scenarios receive a `ScenarioRuntimeHandle` (a `Protocol` exposing `event_logger` and `current_round`) via `bind_runtime`, used to emit custom events and read the active round.

## MCP Tools

The `SimulationRuntime` registers five MCP tools on a FastMCP server named `comms`. Agents interact with the simulation exclusively through these tools.

| Tool                 | Parameters                          | Behavior                                                                                                    |
| -------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `read_notifications`     | *(none)*                   | Blocks until a notification arrives in the agent's queue, or returns a `no_activity` notification after a 120s timeout.  |
| `read_channel`       | `channel_id`, `last_n`     | Returns the last N messages from a channel the agent belongs to. Validates membership.                      |
| `send_message`       | `channel_id`, `text`       | Posts a message under a per-channel write lock, notifies other channel members, fires on-message callbacks.  |
| `list_channels`      | *(none)*                   | Returns channels the agent belongs to with scenario-defined display names.                                  |
| `get_channel_members`| `channel_id`               | Returns the members of a channel with display names. Validates membership.                                  |

Agent identity is resolved from the MCP connection URL query parameter (`?agent_id=engineer`), not from tool arguments. Agents cannot impersonate each other.

Agents see these as generic communication primitives (the MCP server is named `comms`), not simulation APIs.

## Agent Runners

Agent runners launch and manage external agent processes that connect to the MCP server. The `AgentRunner` ABC defines a single method: `start(agent_config, mcp_server_url)`. Each runner instance handles one agent.

**PydanticAIRunner** is the primary implementation. It uses the Pydantic AI framework to launch an agent with:
- The agent's system prompt (from `AgentConfig`)
- An `MCPServerStreamableHTTP` toolset pointing to the runtime's HTTP endpoint
- A configurable `max_turns` limit (default: 200)
- An initial prompt instructing the agent to start by checking for messages

The runner uses `agent.run()` with an `event_stream_handler` to stream token deltas and message previews to the EventBus. It re-prompts the agent via `message_history` after each cycle and exits when a done notification arrives via `read_notifications`. The supervisor creates a new `PydanticAIRunner` per agent.

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
- The `send_message` MCP tool validates agent membership before appending a message to a channel.

## Scenario Protocol

The `SimulationScenario` ABC defines a contract for scenario plug-ins.

**Core methods (required by all scenarios):**
- `get_agent_roles(knobs)` — return agent IDs and display names for a knobs/config payload
- `knobs_json_schema()` — return the JSON Schema for the scenario knobs model
- `prepare_config(config)` — normalize raw config before validation/instantiation
- `create_from_config(config)` — reconstruct a scenario from its serialized config dict (used by fork/resume)
- `name()`, `scenario_description()`, `get_agents()`, `get_channels()`
- `get_channel_display_name()`, `get_agent_display_name()`, `get_injection()`
- `run_evaluation(log_path, metric_names, report_path, model, provider_name, inference_provider, reasoning_effort)`

**Timing and round structure:**
- `get_round_count()` — total number of rounds
- `get_max_round_duration_seconds()` — max wall-clock seconds per round

**Runtime extensions:**
- `get_world()` — scenario world (state, world-event delivery, tool handlers)
- `get_mcp_tools()` — scenario-specific MCP tools (agent_id injected automatically)

The game clock uses the timing methods to manage round progression and termination; injection delivery is triggered by the clock and performed by the runtime via `deliver_round_injections` / `deliver_postmortem_injections`, which read scenario-defined injection content and push it onto agent sessions.

### Scenario Package Layout

Each scenario is a Python sub-package under `schmidt/scenarios/<name>/` with intentionally-empty `__init__.py` files at the namespace and scenario-package levels. The empty inits matter — see "Scenario Event Discovery" below.

```
src/schmidt/scenarios/<scenario_name>/
├── __init__.py              # empty (avoids eager-load circular import)
├── scenario.py              # the SimulationScenario subclass
├── ids.py                   # agent IDs, channel IDs, tool names, markers
├── knobs.py                 # the Pydantic knobs model extending BaseKnobs
├── knobs_default.json       # canonical preset
├── events.py                # scenario-specific EventBase subclasses
├── world.py                 # scenario-specific ScenarioWorld
├── prompts/                 # Jinja2 templates for system prompts and injections
└── evaluation/              # scenario-specific Metric subclasses
```

`SCENARIO_REGISTRY` lives in `schmidt/scenario_registry.py` (not in `schmidt/scenarios/__init__.py`) so importing event-related modules doesn't trigger eager loading of every scenario.

### Scenario Event Discovery

Scenarios register new event types by adding them to their `events.py` — no edit to `schmidt/models/event.py` is required.

At module load time, `schmidt.models.event._discover_scenario_event_types()` walks the `schmidt.scenarios` namespace package via `pkgutil.iter_modules`, imports every `<scenario_pkg>.events` submodule when present, and collects every module member that subclasses `EventBase`. The discovered classes are combined with the core platform events into `_ALL_EVENT_TYPES`, which is then wrapped in a discriminated-union `TypeAdapter` exposed as `SIMULATION_EVENT_ADAPTER` for the JSONL parser.

The auto-discovery works because:

1. **Scenario `events.py` modules only import from `schmidt.models.event_base`** (where `EventBase` and `TokenUsage` live), never from `schmidt.models.event`. This breaks the would-be cycle.
2. **Scenario package `__init__.py` files are empty**, so importing `schmidt.scenarios.<name>.events` does NOT cascade into loading `scenario.py` (which imports `schmidt.models.event` and would re-enter the partial module).
3. **`SimulationEvent` is typed as `EventBase`** statically — the runtime-built discriminated union cannot be expressed as a static type. Concrete subclass attributes still require `isinstance(event, ConcreteEvent)` narrowing at use sites. The discriminator field `event_type: str` is declared on `EventBase` with `model_config = ConfigDict(frozen=True)` so subclasses can override it with `Literal[...]` covariantly.

## Agent Prompt Framing

Agents are framed as AI assistants helping a person in a role — not as the role itself.

Instead of:

> "You are a product manager. Negotiate the deadline."

The system prompt reads:

> "I'm a product manager. My stakeholders gave me a hard deadline. Between us, the deadline has about 1 extra week of flexibility, but I was told to push for the aggressive date. Help me run this planning meeting effectively."

This keeps agents grounded as genuine assistants (which they are), avoids roleplay artifacts, and makes secret-leak evaluation more meaningful — confidential information is shared as trusted context between user and assistant.

Agents do not know they are in a simulation. The MCP server is named `comms` and the tools are named after generic communication primitives (`read_notifications`, `read_channel`, `send_message`). From the agent's perspective, it is connected to a messaging system.

## Event Log

Every simulation event is serialized as one JSON object per line in a JSONL file (one file per run).

Event types (discriminated union on `event_type`):

- `simulation_started` — run ID, scenario name, scenario description, channel IDs, scenario config
- `agent_registered` — agent ID, role name, system prompt, channel IDs, tool names, model
- `agent_connected` — agent ID, role name, model (emitted when an autonomous agent connects)
- `round_advanced` — new round number, trigger reason (`simulation_start`, `all_agents_idle`, `round_timeout`)
- `injection_delivered` — agent ID, round number, injection text
- `message_sent` — full SimulationMessage (channel, sender, content, timestamp)
- `llm_response_received` — agent ID, text (includes thinking blocks), tool calls, stop reason, token usage
- `simulation_ended` — reason (RunStatus enum), total_messages

## Run Storage

All simulation outputs use a standard directory layout:

```
runs/{scenario_name}/{unix_timestamp}/
├── {scenario_name}.jsonl              # Event log (one JSON object per line)
├── {scenario_name}_debug.jsonl        # Debug log (JSON lines from Python logger, visible in FE)
├── {scenario_name}_report.json        # Evaluation report (written by evaluate command)
├── fork_manifest.json                 # (forked runs only) provenance tracking
├── replace_manifest.json              # (replace-agent runs only) provenance tracking
├── cross_run_replace_manifest.json    # (cross-run replace-agent runs only) source A/B + imported model
├── imported_history_source.jsonl      # (cross-run replace-agent runs only) verbatim copy of Sim B's JSONL
└── resume_context_{agent_id}.json     # per-agent reconstructed pydantic-ai history dumped at resume time
```

The CLI `run` command computes the output path automatically from `--runs-dir`, the scenario name, and the current unix timestamp. The `evaluate` command takes `--run-dir` pointing to a specific run directory and writes the report as a sibling to the JSONL file.

The web server scans this directory tree to discover runs, reading the first and last lines of each JSONL file to extract metadata (scenario name, timestamp, total messages, end reason) without loading the full log. Forked, replace-agent, and cross-run replace-agent runs are identified by the presence of `fork_manifest.json`, `replace_manifest.json`, or `cross_run_replace_manifest.json` respectively.

## Fork System (Message-Level Rewind)

The fork system allows rewinding a completed simulation to any message, editing it, and re-running from that point. Forking creates a new run directory — the original is preserved.

### Fork Flow

1. **Frontend**: User hovers over a message in the run detail view, clicks the edit button, modifies the text, and clicks the play button. The frontend calls `POST /api/runs/{run_id}/fork` with target message ID, text edits, model/provider, and optional knobs/config overrides.
2. **Fork router** (`server/runs/fork_router.py`): Resolves the target message to a git commit, clones the source run repo to a new run directory, and checks out the target commit.
3. **Edit application**: Rewrites the forked JSONL in-place (`_apply_edits_and_new_run_id`) to apply message text edits and assign a new run ID. Writes `fork_manifest.json` for provenance and commits the fork edits.
4. **Preflight validation**: Validates merged scenario config (source config plus optional fork knobs) with `validate_run_config`, including `model_overrides` provider checks and scenario-aware agent ID checks.
5. **Resume**: Launches `schmidt run --resume <new_dir> --config fork_config.json` as a background subprocess.
6. **Supervisor resume**: CLI rebuilds `RewindState` from the forked JSONL and resumes the simulation from the restored round/channel state.
7. **Agents continue**: Fresh agent sessions start with reconstructed message history and continue naturally from the edited world state.

### Key Modules

- `message_rewind.py` — `RewindState` and rewind state reconstruction helpers
- `message_history_builder.py` — builds per-agent transcript history from events
- `run_jsonl_rewriter.py` — shared JSONL rewriter (used by both fork and replace-agent) that walks the cloned log once and applies a caller-supplied drop predicate plus run-id / message-text edits
- `server/runs/fork_router.py` — `POST /api/runs/{run_id}/fork` API endpoint

### Provenance

Forked runs store a `fork_manifest.json` containing `source_run_id` and `target_message_id`. The run discovery and detail endpoints expose this as `fork_source` on the response models. The frontend shows a "Fork" badge in the run list and a lineage link in the run detail header.

## Replace-Agent System (Round-Level Rewind)

The replace-agent system rewinds a finished simulation to the start of a chosen round and re-runs from there with one specific agent restarted on a fresh history. Every other agent resumes from its full reconstructed history. The replacement agent's model/provider can differ from the original. Like fork, replace-agent creates a new run directory — the original is preserved.

This shares the fork primitives (git clone + checkout, JSONL rewrite, `--resume` subprocess) but differs in two ways: (1) the user picks a **round number** instead of a message ID — the system resolves it to the last `MessageSent` whose `round_number < round_start`; (2) the JSONL rewriter strips `llm_response_received` / `tool_call_invoked` / `tool_result_received` events **only** when their `agent_id` matches the replaced agent, so reconstructed message history for non-replaced agents stays intact.

### Replace-Agent Flow

1. **Entry**: User invokes `python -m schmidt replace-agent <scenario> --source-run-dir <dir> --round-start <N> --replaced-agent-id <id> --model <model> --provider <provider> --runs-dir <dir>`, or `POST /api/runs/{run_id}/replace-agent` with the same payload. Both surfaces call the shared core helper `replace_agent.replace_agent_in_run`.
2. **Round resolution**: `resolve_round_start_message(events, round_start)` finds the last `MessageSent` whose `round_number < round_start`. Round 1 is rejected (no prior message to anchor to).
3. **Clone + checkout**: Same as fork — `find_commit_for_message` → SHA, `clone_to` + `checkout`.
4. **JSONL rewrite**: `run_jsonl_rewriter.rewrite_run_jsonl` walks the cloned log once with predicate `drop_single_agent_history(event_dict, agent_id=replaced_agent_id)` — only the chosen agent's LLM history events are dropped.
5. **Per-agent model overrides**: An explicit `model_overrides` dict is built that pins every source agent to its original `(model, provider)` pair (read from `AgentRegistered` events) and overwrites just the replaced agent's entry with the new model/provider. This guarantees non-replaced agents stay on their exact original models even if the top-level CLI defaults differ.
6. **Manifest + commit**: `replace_manifest.json` records `source_run_id`, `round_start`, `target_message_id` (the resolved anchor, kept for traceability), `replaced_agent_id`, `replacement_model`, `replacement_provider`, `channels_with_visible_history`, `replaced_at`. Committed as `replace: agent <id> → <model>/<provider>`.
7. **Resume**: Launches `schmidt run --resume <new_dir> --config replace_config.json` as a background subprocess.
8. **Supervisor resume**: When the resumed simulation rebuilds `RewindState`, the replaced agent's `agent_message_histories[agent_id]` comes back empty (no LLM history events left for it), while every other agent's history is fully reconstructed. The supervisor calls `ChannelRouter.apply_replacement_visibility(agent_id, channels_with_visible_history)` so `read_channel` returns prior messages only for whitelisted channels; all others have the agent's `member_join_index` bumped to the current message count, hiding pre-resume history without affecting any other agent's view.

### Per-Channel History Visibility (Platform Feature)

The replace-agent flow lets the caller choose, per channel, whether the replaced agent retains visibility of pre-resume messages on that channel. This is generic across scenarios.

- **Request field**: `ReplaceAgentRequest.channels_with_visible_history: list[str]` (CLI flag `--visible-history-channel CHANNEL`, repeatable; HTTP body field of the same name). Empty list = wipe history visibility on every channel the agent is in.
- **Default policy**: `BaseKnobs.replace_agent_default_channel_visibility: dict[str, bool]` (channel ID → visible). Channels absent from the map default to visible. The CLI consults this knob when no `--visible-history-channel` flag is passed; the FE consults it to pre-populate the modal checkboxes. New scenarios opt in by setting the map in their preset JSONs — no code change required.
- **Persistence**: stored on `replace_manifest.json`; the CLI's `--resume` path reads it and threads it onto `RewindState.replaced_agent_channels_with_visible_history` (a `dict[str, list[str]]` keyed by `agent_id`).

### Veyru-Specific Knob: Drop Postmortem After Replacement

Setting `postmortem_disabled_at_start: true` in the merged `knobs` payload makes `VeyruWorld.__init__` flip `_postmortem_globally_disabled = True` immediately. From resume onward `validate_outgoing_message`, `get_postmortem_injection`, and `get_max_postmortem_duration_seconds` all short-circuit, so the postmortem channel exists but is inert (no sends, no injections, no postmortem phase). The FE replace-agent modal exposes this as a Veyru-only "Drop #postmortem channel after replacement" checkbox; other scenarios use the generic `knobs` field directly.

### Key Modules

- `replace_agent.py` — `ReplaceAgentRequest`/`ReplaceAgentResult` named tuples, `resolve_round_start_message`, and `replace_agent_in_run` (shared core called by both CLI and HTTP layers)
- `run_jsonl_rewriter.py` — `rewrite_run_jsonl` plus the two drop predicates (`drop_all_agent_history` for fork, `drop_single_agent_history` for replace-agent)
- `server/runs/replace_agent_router.py` — `POST /api/runs/{scenario}/{run_dir_name}/replace-agent` thin HTTP wrapper
- `cli.py` `_run_replace_agent` — CLI subcommand implementation

### Provenance

Replace-agent runs store a `replace_manifest.json`. The run discovery and detail endpoints expose this as `replace_agent_source` on the response models alongside `fork_source`. The frontend shows a "Replaced X → model @ round N" badge in the run detail header.

## Cross-Run Replace-Agent System (Round-Level Rewind, Different Source for the Imported Agent)

The cross-run replace-agent system is a sibling of replace-agent that imports an agent from a *different* completed run (Sim B) into a target run (Sim A) at a chosen round boundary. Same scenario and same `agent_id` only. The imported agent retains its **full** pydantic-ai history from Sim B (text + thinking + tool calls); non-replaced agents continue with their full Sim A history.

This shares replace-agent's primitives (git clone of Sim A + checkout, JSONL rewrite, `--resume` subprocess, per-channel visibility, optional postmortem disable) but introduces a dual-event-stream architecture for history reconstruction: the imported agent's history is built from Sim B's JSONL while every other agent's history is built from Sim A's JSONL.

### Cross-Run Flow

1. **Entry**: `python -m schmidt cross-run-replace-agent <scenario> --source-a-run-dir <dir> --source-b-run-dir <dir> --round-start <N> --replaced-agent-id <id> --runs-dir <dir>` or `POST /api/runs/{scenario}/{run_dir_name}/cross-run-replace-agent` with `source_b_run_id` in the body. Both surfaces call the shared core helper `cross_run_replace_agent.cross_run_replace_agent_in_run`.
2. **Validate**: Sim A and Sim B exist, scenarios match, `replaced_agent_id` exists in both, `round_start > 1`, Sim B reached at least `source_b_round_end`. Default `source_b_round_end = min(round_start - 1, B_max_round)` so the imported agent gets the largest temporally-aligned slice of B's history without exceeding what B reached.
3. **Resolve model**: when `--model` / `--provider` are absent, read Sim B's `AgentRegistered` for `replaced_agent_id` and use those values. Both must be passed together to override.
4. **Clone Sim A** at the `RoundAdvanced(round_start)` commit (same as replace-agent), rewrite the JSONL run-id, copy Sim B's full JSONL to `<new_dir>/imported_history_source.jsonl`, build merged scenario_config (knobs + `model_overrides` pinning every Sim A agent to its Sim A model and the replaced agent to the imported model), write `replace_config.json`.
5. **Compute blocked tool-call channels**: scenario default (`get_replace_agent_blocked_tool_call_channels`) ∪ Sim-B-only channels (channel IDs the imported agent had in Sim B but doesn't exist in Sim A — necessary to avoid pydantic-ai schema validation rejecting reconstructed tool calls referencing dead channel IDs).
6. **Manifest**: write `cross_run_replace_manifest.json` with both `source_a_run_id` and `source_b_run_id`, the imported model/provider, `round_start`, `source_b_round_end`, `rounds_after_swap`, `replaced_agent_id`, `channels_with_visible_history`, `blocked_tool_call_channels`. Single git commit covers manifest + config + copied source-B JSONL.
7. **Resume**: launches `schmidt run --resume <new_dir> --config replace_config.json` as a background subprocess.
8. **Supervisor resume**: the CLI's resume path detects `cross_run_replace_manifest.json` (in addition to the existing `replace_manifest.json` detection) and builds an `AgentHistoryFilter` for the replaced agent with an `imported: ImportedHistory` slot containing Sim B's events, target_timestamp, and cutoff_round. The history reconstruction loop in `_build_rewind_state_at_timestamp` dispatches per-agent: when `filter.imported is not None`, that agent's history is built from Sim B's events and its system prompt is taken from Sim B's `AgentRegistered`; otherwise the agent's history is built from Sim A's events as usual. Channel visibility on Sim A's channels is applied identically to replace-agent.

### Dual-Event-Stream History Reconstruction

The single non-trivial architectural change vs replace-agent is the extension of `AgentHistoryFilter` (in `message_rewind.py`) with a sub-NamedTuple:

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

Grouping the three correlated fields into one Optional sub-tuple makes invalid combinations unrepresentable (you can't have two of three set). When `imported is None` (replace-agent, fork, plain `--resume`), the agent's history comes from the caller's primary event list. When set (cross-run flow), it overrides the events / target_timestamp / cutoff_round / system_prompt for that one agent. The state walk (channels, injections, current round) always uses the primary event list — only history reconstruction is per-agent redirected.

### Validation: `resume_context_{agent_id}.json`

Same as replace-agent, the supervisor calls `write_resume_context_files` at resume time. For cross-run runs this dumps the imported agent's reconstructed pydantic-ai history (built from Sim B) to disk, so the operator can verify by hand that the tail matches Sim B's last few `MessageSent` events for that agent — confirming the cross-run history was mounted correctly and not contaminated by Sim A.

### Key Modules

- `cross_run_replace_agent.py` — `CrossRunReplaceAgentRequest`/`CrossRunReplaceAgentResult` named tuples, `_resolve_source_b_cutoff_event_id`, `_compute_blocked_tool_call_channels`, and `cross_run_replace_agent_in_run` (shared core called by both CLI and HTTP layers)
- `cross_run_replace_manifest.py` — `CrossRunReplaceManifest` Pydantic model + `read_cross_run_replace_manifest` reader (kept separate from `replace_manifest.py` so evaluators / discovery can dispatch on file presence)
- `message_rewind.py` — `AgentHistoryFilter` extended with `imported: ImportedHistory | None`; `_find_imported_registration` looks up the imported agent's `AgentRegistered` in the imported event stream
- `server/runs/cross_run_replace_agent_router.py` — `POST /api/runs/{scenario}/{run_dir_name}/cross-run-replace-agent` thin HTTP wrapper; resolves `--source-b-round-end` and `--model`/`--provider` defaults at the edge
- `cli.py` `_run_cross_run_replace_agent` + `_resolve_source_b_max_round` + `_resolve_imported_model_from_source_b` — CLI subcommand implementation
- `scenarios/veyru/evaluation/metrics/round_success/round_success_after_resume_metric.py` — reads either `replace_manifest.json` or `cross_run_replace_manifest.json` and projects to a common `_ResumeAnchor` (so the same metric works for both flows)

### Provenance

Cross-run replace-agent runs store a `cross_run_replace_manifest.json` plus a `imported_history_source.jsonl` (verbatim copy of Sim B's JSONL). The run discovery and detail endpoints expose the manifest as `cross_run_replace_agent_source` on the response models alongside `fork_source` and `replace_agent_source`. The frontend shows a violet "Cross-run X: A=… · B=… → imported_model @ round N" badge in the run detail header with both sources as links, and a violet floating action button to scroll to the swap divider in the chat pane.

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

`channel_visibility` is itself a discriminated union (`Full` / `None` / `FromRound(round_floor)`) — the same shape used by replace-agent's per-channel visibility and by the history reconstruction filter.

### Swap Flow

1. **Round boundary fires** in `RoundBoundaryScheduler` (driven by the game clock's `signal_round_advanced`). The scheduler dispatches every event whose `at_round` matches.
2. **`SwapAgent` dispatch** calls `execute_agent_swap` in `runtime/agent_swap.py` with an `AgentSwapResources` bundle (runtime, runner factory, runner-task table, log path, run dir, MCP url, cost tracker).
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

`message_history_builder.py` derives a notification round floor from the `channel_visibility` config: `min(v.round_floor for v in channel_visibility.values() if isinstance(v, ChannelVisibilityFromRound))`, or `None` when no channel uses `FromRound`. `read_notifications` calls whose source `ToolCallInvoked.round_number` falls below the floor are dropped, in both the parented-cycle and orphan-cycle paths.

The filter applies to every caller that builds an agent history with a `FromRound` entry: replace-agent, fork, cross-run, and in-run swap.

### Per-Swap Resume Context Files

`write_swap_resume_context_file` writes one `resume_context_<agent_id>_round_<R>.json` per swap into the run directory. The filename includes the round number so multiple swaps in the same run keep separate files. The payload mirrors the replace-agent `resume_context_<agent_id>.json` shape and captures the swapped-in agent's pydantic-ai message history at swap time for audit.

### Key Modules

- `runtime/scheduled_events.py` — `ChannelVisibility` discriminated union (`Full` / `None` / `FromRound`), `SwapAgent`, `SetPostmortem`, `ScheduledEvent` discriminated union
- `runtime/scheduler.py` — `RoundBoundaryScheduler` and the `SchedulerOps` Protocol
- `runtime/agent_swap.py` — `AgentSwapResources` named tuple + `execute_agent_swap`
- `runtime/scenario_world.py` — `get_globally_disabled_channels()` and `on_agent_swapped_mid_run()` ABC hooks
- `models/event.py` — `AgentSwappedMidRun`, `PostmortemDisabledMidRun` event types
- `message_history_builder.py` — notification round-floor derivation + filter
- `resume_context_writer.py` — `write_swap_resume_context_file`
- `scenarios/veyru/evaluation/metrics/round_success/round_success_after_resume_metric.py` — walks every `AgentSwappedMidRun` event and emits one Measurement per anchor (named `round_success_after_resume_round_<R>_<agent_id>`); the in-run baseline window is the previous phase in the same run

### FE Per-Agent-Instance Tabs

The run viewer derives one `AgentInstance` per `(agent_id, generation)` from `agents` + `agent_swap_events` on the run-detail response. Single-instance agents render a flat sidebar row. Multi-instance agents render a parent role row with indented `Gen k · rA-B` sub-rows; the latest generation pulses green on live runs. Per-instance drawer tabs filter messages by round range and show round-banner dividers. The chat pane renders a dashed indigo `agent-swap-divider` between adjacent rounds that straddle a swap event.

`server/runs/models.py` exposes `AgentSwapEventDTO` and a `agent_swap_events: list[AgentSwapEventDTO]` field on `RunDetailResponse`. `server/runs/detail_reader.py` populates it from the JSONL events.

### Provenance

In-run swap runs carry no manifest file — the `AgentSwappedMidRun` events in the JSONL are the source of truth. Run discovery and detail endpoints surface swaps via the `agent_swap_events` field on `RunDetailResponse`.

## Evaluation System

After a simulation completes, the evaluation system analyzes the JSONL log via a uniform `Metric` abstraction. Both deterministic metrics and LLM-as-judge metrics implement `Metric.compute(...)` and return one or more `Measurement` instances.

**CLI**: `python -m schmidt evaluate <scenario> --run-dir ./runs/<scenario>/<timestamp> --metrics language_strangeness,perplexity --model MODEL`

The user selects which metrics to run — they are not automatically applied.

**Generic metrics** (available to all scenarios). LLM judges scope each to a specific phenomenon; their prompts explicitly exclude what the other metrics cover, preventing overlap:

- `language_strangeness` — unusual grammar, sentence structure, formatting, telegraph-style (LLM judge)
- `slang_emergence` — informal register shifts, colloquial expressions, casual nicknames (LLM judge)
- `neologism` — genuinely invented words with new meanings (LLM judge)
- `shorthand_codes` — abbreviation systems, symbol-to-meaning mappings, systematic encoding (LLM judge)
- `round_ended_idle` / `round_ended_timeout` — count rounds whose main phase ended via the `all_agents_idle` or `round_timeout` trigger (deterministic, reads `RoundEnded.trigger`)
- `content_filter_refusal` — counts LLM content-filter refusals across the run with per-round + per-agent breakdowns (deterministic, scans `AgentRunCycleFailed` events)
- `perplexity` — mean per-token surprisal (in nats) of primary-channel messages under a fixed `gpt2` language model loaded via `minicons.IncrementalLMScorer`. Scoping uses `scenario.get_primary_channel_id()` so the metric stays scenario-agnostic (Veyru returns `#link`; scenarios without a primary channel get a no-op result). The score is the overall mean nats; `per_round` carries mean+std+message_count per round. No LLM judge.
- `mean_chars_per_round` — total characters of all primary-channel messages summed per round, then averaged across rounds with at least one message. Same scoping rule as `perplexity`. The score is the mean of per-round totals; `per_round` lists each round's total chars + message count. The headline channel-utilization number; in Veyru this is exactly the unit that ``time_budget_seconds`` is denominated in. No LLM judge.
- `mean_chars_per_message` — characters per individual primary-channel message, averaged across all messages in the run (flattened, not mean of round means). Same scoping rule as `perplexity`. The score is the overall mean chars/message; `per_round` carries per-round mean+std+message_count. Normalizes MCR by message count, isolating per-message verbosity from message density — MCR is biased upward by rounds that simply need more back-and-forth. No LLM judge.

The LLM-judge metrics (`language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes`, `language_emergence`, `protocol_learned_after_swap`) share a common flow: build per-round transcripts from `MessageSent` events, render a Jinja2 prompt, call the LLM judge with a structured output schema (returning `per_round_notes: list[RoundNote]`), and turn each `RoundNote` into a `RoundObservation`. The deterministic metrics skip the prompt+LLM step entirely.

**Scenario-specific metrics:**
- **veyru**: `language_emergence` (novel language in the Veyru domain), `protocol_learned_after_swap` (whether a newcomer adopted the pre-established protocol after a personnel change), `round_success` (per-round stabilization success — emits one `Measurement` per team in two-team mode), `round_success_after_resume` (same accounting restricted to post-replace-agent rounds, with source-run comparison in `summary`), `protocol_probe` (probes each agent against a fixed test bank under its original model; writes `protocol_probe_responses.jsonl`), `protocol_probe_replica_self_similarity` / `protocol_probe_agent_pair_similarity` / `protocol_probe_cutoff_trajectory` (deterministic Levenshtein-based similarity metrics that read the probe JSONL, write per-matrix JSON artifacts for the Streamlit "Probe similarity" tab, and emit zero-score Measurements when their prerequisites — ≥2 replicas, two-team agents in the same role, or ≥2 distinct cutoff_round values — are not met)

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

- The server reads from the `runs/` directory at request time (no database).
- `SCHMIDT_RUNS_DIR` environment variable configures the runs root directory.
- CORS origins are read from the `ALLOWED_ORIGINS` environment variable (comma-separated). Defaults to `http://localhost:3000`.
- Optional shared-password authentication via `APP_PASSWORD` environment variable. A pure ASGI middleware (`password_auth_middleware.py`) checks `Authorization: Bearer` headers and `?token=` query parameters (for SSE EventSource connections). All REST endpoints except `GET /api/health` are protected when enabled. The `/mcp` path and OAuth well-known endpoints are excluded from password auth — the MCP server uses its own OAuth-based authentication.
- Every endpoint declares a `response_model` and returns a Pydantic model instance. No dicts or strings are returned.
- Status-like fields use enums (`HealthStatus`, `RunStatus`, `Verdict`) instead of bare strings. `RunStatus` includes `IN_PROGRESS` for runs that have not yet completed.
- The run detail endpoint returns separate `messages` (ChannelMessage) and `reasoning` (ReasoningEntry) arrays, plus `debug_logs` (DebugLogEntry) parsed from the debug JSONL file.

### MCP Runs Browser

An MCP server is mounted at `/mcp` on the FastAPI backend, providing programmatic access to simulation data and run launch flows for LLM clients (Claude Code, Cursor). Uses `FastMCP` with Streamable HTTP transport, mounted via `app.mount("/mcp", mcp.streamable_http_app())`. Requires `OAUTH_ISSUER_URL` to be set; the MCP endpoint is disabled if unset.

The MCP server exposes eight tools:

| Tool                   | Description                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------ |
| `list_scenarios`       | Lists available scenarios with knobs files, evaluators, and supported models/providers           |
| `list_runs`            | Paginated run listing with filtering by scenario, model, fork status, and run status             |
| `get_run_metadata`     | Lightweight metadata for a single run: agents, channels, configuration, evaluation summary       |
| `get_run`              | Full run content with messages; opt-in sections for reasoning, tool use, debug logs, system prompts; filtering by agent or channel |
| `get_knobs_schema`     | Returns a scenario knobs JSON Schema (field types, enums, descriptions) and available presets    |
| `get_knobs_preset`     | Loads a knobs preset JSON payload for a scenario                                                  |
| `start_run`            | Launches a simulation subprocess with scenario, model, provider, and optional knobs               |
| `export_run_artifacts` | Returns a download URL for a zip archive of the run's artifacts                                   |

All tools return structured JSON via Pydantic response models. `list_runs` and `get_run` support pagination. `get_run` uses flags (`with_reasoning`, `with_tool_use`, `with_debug_logs`, `with_system_prompts`) to control which sections are included.

For run launch from MCP clients, a typical flow is:
1. `get_knobs_schema` to inspect available fields and preset names.
2. `get_knobs_preset` to load a baseline knobs payload.
3. `start_run` with model/provider and any knob overrides.

The MCP server reuses the same data layer as the REST API (`discover_runs()`, `load_run_detail()`) and shares simulation launch helpers with the REST start endpoint (`run_launcher.py`). Run ID parameters accept unique prefixes (e.g., first 8 characters) for convenience.

#### MCP OAuth Authentication

The MCP endpoint uses OAuth 2.0 with PKCE for authentication, handled by the MCP library's built-in authorization server support. The `/mcp` path is excluded from the shared-password middleware — authentication is handled by the MCP library's `RequireAuthMiddleware`.

The OAuth flow:

1. **Discovery**: Clients fetch `/.well-known/oauth-protected-resource` (RFC 9728) to find the authorization server, then `/.well-known/oauth-authorization-server` (RFC 8414) for endpoint URLs. These are served at the host root as proxy routes since the MCP sub-app is mounted at `/mcp`.
2. **Client registration**: `POST /mcp/register` (RFC 7591 dynamic client registration). The server generates a `client_id` and `client_secret`, stored in SQLite.
3. **Authorization**: `GET /mcp/authorize` with PKCE `code_challenge`. If `APP_PASSWORD` is set, redirects to a login form at `/mcp/oauth/login` for password verification. If unset, auto-approves and redirects with an authorization code.
4. **Token exchange**: `POST /mcp/token` exchanges the authorization code for an access token (1 hour) and refresh token (30 days).
5. **Authenticated requests**: Bearer token in the `Authorization` header, validated by the MCP library's `BearerAuthBackend`.

Implementation:
- `server/mcp/oauth_provider.py` — `SchmidtOAuthProvider` implementing the `OAuthAuthorizationServerProvider` protocol
- `server/mcp/oauth_storage.py` — `OAuthStorage` with SQLite tables for clients, authorization codes, access tokens, and refresh tokens
- `server/mcp/oauth_login_page.py` — Minimal HTML login form for the authorization flow

The frontend includes an MCP integration modal (accessible via the **MCP** button on the runs page) that shows connection instructions for Claude Code and Cursor.

### Frontend

- **Stack**: Next.js 16 (App Router), React 19, TypeScript (strict mode), Tailwind CSS v4
- **Data fetching**: TanStack React Query with openapi-fetch for type-safe API calls. In-progress runs auto-refresh every 5 seconds (configurable via a Stop/Resume button).
- **Type generation**: `openapi-typescript` generates TypeScript types from the backend's OpenAPI schema. CI enforces that generated types stay in sync with the backend.
- **Lint enforcement**: ESLint forbids raw `fetch()` — all API calls must go through the typed client at `@/shared/lib/api-client`. This ensures compile-time validation of request paths, parameters, and response types.
- **Fork UI**: Completed runs show per-message edit buttons (on hover). Editing a message and clicking play opens a modal to select model/provider, then calls the fork API and navigates to the new run. Forked runs display a lineage badge linking to the source. Fork state is managed by the `useFork` hook (`use-fork.ts`).

## Results Viewer (Streamlit)

A separate Streamlit app at [analysis/results_viewer/](analysis/results_viewer/) overlays per-round evaluator scores across multiple evaluated runs. It is a read-only consumer of the standard run output (`runs/{scenario}/{ts}/{scenario}_report.json` plus the JSONL event log) — no API or backend coupling.

- `run_catalog.py` — discovers runs that have an evaluator report.
- `event_extractor.py` — derives a per-round timeline from the JSONL events.
- `timeline_plot.py` — builds a Plotly figure overlaying multiple runs' evaluator scores per round.
- `multi_swap_data.py` / `multi_swap_tab.py` — per-phase round-success visualisation for runs with one or more `AgentSwappedMidRun` events. Renders one bar per phase plus Δ pp annotations between adjacent phases. Loads runs concurrently via `asyncio.gather` + `asyncio.to_thread`, skips non-multi-swap runs through a byte-level pre-scan for the swap-event marker, and persists per-run results to `multi_swap_cache.json` keyed on JSONL size + mtime.
- `probe_similarity_data.py` / `probe_similarity_tab.py` — Levenshtein-based comparisons over the per-run `protocol_probe_*.json` artifacts and the raw `protocol_probe_responses.jsonl`. A single multi-select at the top of the tab drives four sub-views: replica self-similarity (per-run consistency across replicas), agent-pair similarity (cross-agent agreement in two-team runs), cross-run model-vs-model (live pairwise matrix on a user-chosen `(question_id, role)` slice — the only place this tab does live Levenshtein), and cutoff trajectory (adjacent-cutoff drift). The data layer is cache-free — the per-run metric classes already cached the heavy work to disk.
- `app.py` — Streamlit entrypoint; reads `SCHMIDT_RUNS_DIR`, lets the user multiselect runs.

Streamlit and Plotly live behind the optional `analysis` uv dependency group so a server-only install (`uv sync`) does not pull them in. Launched with `make results-viewer`.
