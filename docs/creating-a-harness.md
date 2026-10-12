# Creating a harness

A harness is what drives one seat's model loop. The platform ships the ones
below, and any installed distribution can add another.

| Harness | Drives a seat with | Seats it accepts | Extra |
|---|---|---|---|
| `pydantic-ai` | a pydantic-ai agent, the default | every provider | none |
| `claude-agent-sdk` | the Claude Code CLI, through the Claude Agent SDK | `anthropic` | `harness-claude-agent-sdk` |
| `codex` | the Codex CLI's app server | `openai` | `harness-codex` |

Select one per run with `--harness`, or per seat with an override:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs --config knobs_default \
  agents.field_observer.harness=claude-agent-sdk \
  agents.stabilization_engineer.model=gpt-5.4 \
  agents.stabilization_engineer.provider=openai \
  agents.stabilization_engineer.harness=codex
```

The seat's harness is recorded on its `agent_registered` event. Exports carry it
as `agent_harness.<agent_id>`. A seat inside a CLI also logs
`harness_session_bound` whenever it starts or changes session, with the CLI's
own session id, which names its transcript under `transcripts/`.

## Running a seat inside an agent CLI

**Install the harness's extra first.** Each extra bundles its CLI's binary. In a
checkout, `make install-server` installs both, alongside the other extras it
installs; a bare `uv sync --extra ...` would remove whichever extras it doesn't
name. In a project that depends on glossogen, name them on the dependency:

```bash
make install-server                                          # in this checkout
uv add 'glossogen[harness-claude-agent-sdk,harness-codex]'   # in your own project
```

The launch check refuses a seat when its harness's extra is missing, when the
seat's provider is not the one the CLI drives, or when that provider's key is
unset. Each CLI bills the key: `ANTHROPIC_API_KEY` for Claude Code,
`OPENAI_API_KEY` for Codex. Each CLI's configuration directory is private to the
seat, so no account the user signed in with is read.

Claude Code also reads
many `CLAUDE*` variables that a pydantic-ai seat does not read: ones that send it to
another backend or credential (`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_OAUTH_TOKEN`),
and, when the run was started from a Claude Code session, that session's own.
The SDK passes the CLI the whole environment, so each seat starts it through a
launcher that removes every inherited `CLAUDE*` variable and
`ANTHROPIC_IDENTITY_TOKEN` first. `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`
pass through, as they do to a pydantic-ai seat, and so do the CLI's other
settings variables, such as `DISABLE_PROMPT_CACHING`.

Codex's app server is started without any inherited `CODEX*` variable, `CODEX_API_KEY` among them, and
uses `OPENAI_BASE_URL` when it is set, as a pydantic-ai OpenAI seat does.

Each CLI starts with the switches that would give the model a tool or
instructions of its own turned off. For Claude Code that is every built-in tool,
every settings file, and every MCP server but the seat's. For Codex it is a
list of features and config keys in
[codex_seat_session.py](../src/glossogen/runners/codex_app_server/codex_seat_session.py),
including `AGENTS.md`, which Codex would otherwise read from the seat's
workspace and every directory above it up to the repository root.

The model sees the platform's system prompt, the user turns, and the seat's own
tools. Every tool call runs in the simulation process, through the same executors a
pydantic-ai seat uses. Each Codex release can add a feature, which is why the
binary is pinned.

| | Claude Code | Codex |
|---|---|---|
| Tools reach the CLI as | an in-process MCP server | the thread's client-defined tools |
| Prompt replaces | Claude Code's system prompt | Codex's base instructions |
| Reasoning | off, as for a pydantic-ai Anthropic seat | effort `high`, summary `concise`, as for a pydantic-ai OpenAI seat |
| Private state | `harness_state/claude_config/` | `harness_state/codex_home/` |

The seat's directory is `harness/<agent_id>/` inside the run. The CLI's private
state lives under `harness_state/`, which the archive filter excludes. When the
session closes, its transcript is copied to `transcripts/`.

**The Codex harness relies on the app server's experimental API.** The binary is
pinned to the minor version the harness was written against. Moving the pin
means rerunning the Codex tests and a live run.

## How a seat outside pydantic-ai differs

A seat under another harness sees the same system prompt and the same tools, as
each CLI presents them: Claude Code prefixes their names with `mcp__glossogen__`,
and Codex drops some JSON Schema keywords (`default`, `title`, `minimum`). Its
event log records the same events, so exports, metrics and the run viewer
read it the way they read any seat. The differences are in what the platform can
do with the seat and in how its model loop behaves.

### Refused

These apply to every harness but `pydantic-ai`: the shipped CLI harnesses and
any installed from a package alike.

| Flow | Result |
|---|---|
| `--resume`, `fork-at-round`, `replace-agent` keeping the seat | refused: its conversation is in the harness's own state, and the history the platform rebuilds from the log cannot be handed back to it |
| `replace-agent` replacing the seat | allowed, onto `pydantic-ai` |
| `replace-agent` or `cross-run-replace-agent` onto another harness | refused: a replacement is seeded with a rebuilt history |
| `scheduled_events` swap onto another harness | refused at launch, for the same reason |
| A scenario whose `requires_gated_model_responses` is True | refused for a harness whose `gates_model_responses()` is False, as the shipped CLI harnesses are. `textcraft_shared_workspace` answers True under `virtual_clock`; a scenario that overrides `gate_model_response` and not this hook answers True |

### Behaves differently

| | `pydantic-ai` | `claude-agent-sdk` | `codex` |
|---|---|---|---|
| A response's tool calls | run concurrently, once the response is complete | each starts as soon as its call has streamed | run one after another, the first starting before the response has finished streaming |
| `gate_model_response` | awaited before the response's tools run | called once the response is complete, when its tools may already have run | same as `claude-agent-sdk` |
| `agent_max_tokens` | caps each request | caps each response, through `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | not applied, with a warning at start: Codex has no per-response cap |
| History sent with each request | `read_channel` messages already read once and empty `read_notifications` polls are dropped | everything the session holds | everything the thread holds |
| The `compaction` knob | compacts at the knob's threshold, under `anthropic` and `openai` | ignored, with a warning at start: Claude Code compacts on its own schedule, logged as `context_compacted` | ignored, with a warning at start: Codex compacts on its own schedule, logged as `context_compacted` |
| `--max-agent-turns` | counts cycles; a cycle ends when the agent ends its turn | counts cycles too, but a seat can stay in one cycle for many rounds | same as `claude-agent-sdk` |
| A failed model request | 3 attempts with exponential backoff, then the cycle restarts from the last completed one | the CLI's own retry policy; a failed turn is logged as `agent_run_cycle_failed` and the next cycle continues the session. The API's error text is not logged as a response | same as `claude-agent-sdk`. A request whose stream drops and is retried is logged as its own response, with no usage |
| A crashed CLI process | not applicable: the loop runs in the simulation process | reopened on the same session after logging `agent_run_cycle_failed` | the seat stops after logging `agent_run_cycle_failed`: a thread continued in a new app server sends no raw response events, so its responses could not be logged |
| Failures in a row | not applicable | the seat stops after `MAX_CONSECUTIVE_SESSION_FAILURES` failed cycles in a row, crashes and failed turns alike, so a bad key or model does not run every cycle. Before each cycle that follows a failed one it pauses `FAILURE_PAUSE_BASE_SECONDS`, doubled for each earlier failure in the row; a crashed session is reopened first | same as `claude-agent-sdk`, except that a crash stops the seat without a pause, since its session cannot reopen |
| A session that fails to open | not applicable | logged as `agent_run_cycle_failed`; the seat stops and the rest of the run goes on | same as `claude-agent-sdk` |
| Cost | priced from the logged usage | priced from the logged usage. Claude Code also reports its own figure, which counts calls it makes for itself; that figure is logged at `INFO` and left out of the run's cost | priced from the logged usage |
| Model metadata | not applicable | Claude Code's own | Codex has none for the model under the provider it is given, warns, and uses its defaults, including for when to compact |
| Langfuse traces | recorded | none | none |

These change what an experiment measures rather than how it runs:

- **`gate_model_response` runs late.** Textcraft's `virtual_clock` is refused for
  that reason. Its `team_token_limit` still runs, and under a CLI seat a
  response's tokens are charged to the pool after its tools have acted.
- **`--max-agent-turns` bounds less.** In a 3-round veyru run, the
  `claude-agent-sdk` seat used one cycle for the whole run, so the ceiling is a
  guard against a looping seat. It does not budget the seat's work.
- **Compaction is the CLI's.** Two seats under one `compaction` setting do not
  compact alike when one is a CLI seat. Compare context use from the logged
  `context_compacted` events, not from the knob.
- **The context is larger.** A CLI seat's requests carry every channel read and
  poll it made, so its input tokens, cost and compaction timing differ from a
  pydantic-ai seat's on the same transcript.
- **A crashed Codex seat leaves the run.** The rest of the run goes on without
  it, so check a Codex seat's `agent_run_cycle_failed` events before reading its
  rounds.

## Writing a harness

A harness can live in its own package, with no change to this repository. The
package declares one entry point, under a group naming the contract version:

```toml
[project.entry-points."glossogen.agent_harnesses.v1"]
my_harness = "my_harnesses.harness:MyHarness"
```

Installed beside glossogen, the harness is selectable everywhere the shipped
ones are:

| Surface | What it does with the harness |
|---|---|
| `--harness` and `agents.<id>.harness=` on `run` | accept its name |
| `--harness` on `replace-agent` and `cross-run-replace-agent` | accept its name, then refuse it, as for any harness but `pydantic-ai` |
| MCP `start_run` | accepts its name in `harness` |
| The launch check | calls its `preflight` with the seats it will drive, before a run directory is claimed |
| `agent_registered`, the run detail API, exports | record its name as the seat's harness |
| Forks and resumes | apply the refusals above to its seats |

The entry-point name must equal the class's `name()`. It implements `AgentHarness`
([src/glossogen/runners/harness_protocol.py](../src/glossogen/runners/harness_protocol.py)):

| Member | Answers |
|---|---|
| `name()` | what a seat selects and records |
| `preflight(seats)` | what the environment lacks for these seats, as remedies; empty when ready |
| `gates_model_responses()` | whether its runner awaits `gate_model_response` before a response's tools run |
| `build_runner(context)` | an `AgentRunner` for one seat |

**A harness over another agent CLI needs only a session.** Implement `SeatSession`
([seat_session.py](../src/glossogen/runners/session_harness/seat_session.py))
over the CLI and return a `SessionSeatRunner` from `build_runner`, passing
`pause_after_failures` as its pause between failed cycles. The session
reports each response's start, its text, thinking and tool calls, its end with
its usage, and each tool result. The runner logs the events, prices the usage,
serves the seat's tools, refuses a `read_notifications` issued beside other
calls, and reopens a session that raised with `resume_session_id` set. The
shipped CLI harnesses are built this way.

A session that cannot continue a conversation raises from `connect` when given
a `resume_session_id`, as the Codex session does, and the seat stops there.

A harness that drives the model loop itself writes its own `AgentRunner`. Its
`start` runs the seat until a `read_notifications` wake ends the run for it,
and it must log what the rest of the platform reads:

| Event | When |
|---|---|
| `llm_response_received` | once per model response, with its tool calls and usage. The run's cost is the sum over these events; the pydantic-ai runner puts a cycle's whole usage on its last response, and the session runner gives each response its own |
| `tool_call_invoked` | once per call, with the id the response used |
| `tool_result_received` | once per result, under the same id |
| `agent_run_cycle_failed` | when a cycle fails and the runner moves on |

It must also call the scenario where a scenario expects to be told, and keep
the seat's cost where the supervisor reads it:

| Call | When |
|---|---|
| `runtime.scenario.on_model_request_started(agent_id)` | as each model request starts |
| `runtime.scenario.gate_model_response(...)` | once per response, with its tokens. Awaited before the response's tools run if `gates_model_responses()` is True |
| `runtime.scenario.on_agent_retired(agent_id)` | once, as `start` returns, however it returns |
| `cost_tracker[agent_id]` | updated after each response; `AgentCostAccumulator` does this and publishes `agent_cost_updated` |

Reuse the platform's pieces rather than restating them.
`offered_tool_specs` and `execute_tool_spec` in
[agent_tools.py](../src/glossogen/runners/agent_tools.py)
give the seat's tools and run a call with the platform's error handling.
`park_and_render` and `reject_parallel_call` in
[read_notifications_tool.py](../src/glossogen/runners/read_notifications_tool.py)
implement the wait. `AgentCostAccumulator` keeps the seat's cost current.

**Refuse a reconstructed history.** A runner given `initial_message_history` it
cannot use must raise. The launch check already keeps swaps and replacements off
any harness but `pydantic-ai`.

## What a harness package cannot change

| Limit | Why |
|---|---|
| A seat's provider is one the platform already has | Pricing, the credential check, `model_class` and the token counter all key on the `Provider` enum in [model_catalog.py](../src/glossogen/model_catalog.py). Driving a model vendor the enum lacks needs that vendor added here first |
| A name glossogen ships cannot be taken | `pydantic-ai`, `claude-agent-sdk` and `codex` resolve to the shipped harnesses; a package declaring one of those names is ignored, and the collision is logged |
| The contract version must match | A package declared under another `glossogen.agent_harnesses.v<N>` group is not read. The CLI's `--harness` and `agents.<id>.harness=` then reject its name as unknown; MCP's `start_run` reports the group it used and the one the platform reads |
| A harness that fails to load fails the launch | An import error, a class that is not an `AgentHarness`, or a `name()` that disagrees with the entry point is reported when a launch names it, not when glossogen starts |
| A hosted backend needs the package installed | The backend image installs glossogen's own extras only, so a package harness reaches a hosted deployment by being added to that image, like an external scenario |
| Langfuse traces cover pydantic-ai seats | A runner of your own can emit its own OpenTelemetry spans; the platform's tracing does not record them |

## Testing a harness

`run_mixed_harness_simulation` in `glossogen.testing.simulation_harness` runs a
scenario with some seats on a `SessionSeatRunner` and the rest on pydantic-ai.
Each `SessionSeat` names its harness, builds its session, and gives the pause
taken after a failed cycle: `no_failure_pause`, or one that records the calls.
`scripted_session_seat` builds one that plays a script, which can also issue
parallel calls (`ParallelToolTurn`) or crash its session (`SessionCrash`). The
Codex tests pass a `CodexSeatSession` launched on a fake app server instead, a
script in `tests/fakes/` that speaks the protocol in the order a live session
does. A session over another CLI can be tested the same way.

## Next

- [Running simulations](running-simulations.md) for the run command and costs.
- [Agent swaps](agent-swaps.md) for the flows a CLI seat is refused from.
- [Testing a scenario](testing-a-scenario.md) for the scripted-agent harness.
