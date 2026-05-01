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
| Entrypoint          | CLI (`python -m schmidt run|evaluate|serve|replace-agent`)   |
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
4. **Game clock delivers round-1 injections** as `NewInfoNotification` messages pushed to agent session queues. Agents receive these via the `read_notifications` MCP tool and begin interacting.
5. **Agents act autonomously** by calling MCP tools: `read_notifications` (blocks until a notification arrives), `read_channel` (fetches recent messages), `send_message` (posts to a channel), `list_channels` (discovers available channels), and `get_channel_members` (sees who is in a channel). There is no central turn controller.
6. **Round advancement** uses a hybrid condition. The game clock polls at 500ms intervals and advances the round when either (a) all agents are idle (blocked on `read_notifications` with empty queues) *and* at least 5 seconds have passed since the last message, or (b) the round duration exceeds `max_round_duration_seconds` since the last message. When a round advances, the game clock delivers injections for the new round to the appropriate agents.
7. **Termination** occurs when the game clock reaches `max_rounds`. The runtime broadcasts a `DoneNotification` to all agents, waits up to 120 seconds for agent tasks to finish, and logs `SimulationEnded` with total message count.

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

The `GameClock` runs as an asyncio task and manages three responsibilities:

1. **Round progression**: Polls at 500ms intervals, checking two advancement conditions:
   - *All agents idle*: Every agent is blocked on `read_notifications` with an empty notification queue.
   - *Round timeout*: Time since the last message exceeds `max_round_duration_seconds`.
2. **Injection delivery**: When a round advances, the clock calls `scenario.get_injection(round_number, agent_id)` for each agent and pushes `NewInfoNotification` to agents that have injections scheduled. Logs an `InjectionDelivered` event for each.
3. **Termination**: When `current_round >= max_rounds` and an advancement trigger fires, the clock returns `RunStatus.SCENARIO_COMPLETE` to the supervisor.

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

The game clock uses the timing methods to manage round progression, injection delivery, and termination.

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
├── {scenario_name}.jsonl          # Event log (one JSON object per line)
├── {scenario_name}_debug.jsonl    # Debug log (JSON lines from Python logger, visible in FE)
├── {scenario_name}_report.json    # Evaluation report (written by evaluate command)
├── fork_manifest.json             # (forked runs only) provenance tracking
└── replace_manifest.json          # (replace-agent runs only) provenance tracking
```

The CLI `run` command computes the output path automatically from `--runs-dir`, the scenario name, and the current unix timestamp. The `evaluate` command takes `--run-dir` pointing to a specific run directory and writes the report as a sibling to the JSONL file.

The web server scans this directory tree to discover runs, reading the first and last lines of each JSONL file to extract metadata (scenario name, timestamp, total messages, end reason) without loading the full log. Forked and replace-agent runs are identified by the presence of `fork_manifest.json` or `replace_manifest.json`.

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
- `mean_word_length` — mean characters per whitespace-delimited word on the primary channel. Same scoping rule as `perplexity`. The score is the mean across all primary-channel words (flatten, not mean of round means); `per_round` lists per-round mean / std / word count. Pairs with `perplexity`: high perplexity + low MWL is a strong compressed-protocol signal (short codes replacing long words), both deterministic and cheap. No LLM judge.
- `mean_message_length` — mean whitespace-delimited words per primary-channel message. Same scoping rule as `perplexity`. The score is the mean across all primary-channel messages (flatten, not mean of round means); `per_round` lists per-round mean / std / message count. Pairs with `mean_word_length`: low MML = fewer words per message; low MWL = shorter words. Compression can show up on either axis independently. No LLM judge.

The LLM-judge metrics (`language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes`, `language_emergence`, `protocol_learned_after_swap`) share a common flow: build per-round transcripts from `MessageSent` events, render a Jinja2 prompt, call the LLM judge with a structured output schema (returning `per_round_notes: list[RoundNote]`), and turn each `RoundNote` into a `RoundObservation`. The deterministic metrics skip the prompt+LLM step entirely.

**Scenario-specific metrics:**
- **veyru**: `language_emergence` (novel language in the Veyru domain), `protocol_learned_after_swap` (whether a newcomer adopted the pre-established protocol after a personnel change), `round_success` (per-round stabilization success — emits one `Measurement` per team in two-team mode), `round_success_after_resume` (same accounting restricted to post-replace-agent rounds, with source-run comparison in `summary`)

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
- `app.py` — Streamlit entrypoint; reads `SCHMIDT_RUNS_DIR`, lets the user multiselect runs.

Streamlit and Plotly live behind the optional `analysis` uv dependency group so a server-only install (`uv sync`) does not pull them in. Launched with `make results-viewer`.
