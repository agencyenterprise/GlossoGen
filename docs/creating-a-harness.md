# Creating a harness

A harness is what drives one seat's model loop. The platform ships the ones
below, and any installed distribution can add another.

| Harness | Drives a seat with | Seats it accepts | Needs |
|---|---|---|---|
| `pydantic-ai` | a pydantic-ai agent, the default | every provider | nothing |
| `claude-code` | the Claude Code CLI, connected to the run over MCP | `anthropic` | `claude` on `PATH` |
| `codex` | the Codex CLI, connected to the run over MCP | `openai` | `codex` on `PATH` |

Select one per run with `--harness`, or per seat with an override:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs --config knobs_default \
  agents.field_observer.harness=claude-code \
  agents.stabilization_engineer.model=gpt-5.4 \
  agents.stabilization_engineer.provider=openai \
  agents.stabilization_engineer.harness=codex
```

The seat's harness is recorded on its `agent_registered` event. Exports carry it
as `agent_harness.<agent_id>`. A seat in a CLI also logs
`harness_session_bound` when the CLI reports its session id, and
`cli_turn_completed` for each turn the CLI ran, with the turn's usage. The run
detail API lists a seat's session ids as `harness_session_ids`, and the run
viewer shows them on the seat's harness badge.

## Running a seat in an agent CLI

**The CLI must be on `PATH`.** The launch check refuses a seat when it is not,
when the seat's provider is not the one the CLI drives, or when that provider's
key is unset. Each CLI bills the key: `ANTHROPIC_API_KEY` for Claude Code,
`OPENAI_API_KEY` for Codex. Each CLI runs with a configuration directory
private to the seat, so no account the user signed in with is read.

**The run serves the seat's tools.** For each such seat the run starts an MCP
server on a loopback port of its own, behind a bearer token generated for the
seat, offering the tools a pydantic-ai seat would get through the same
executors. The CLI is started as a subprocess with that server as its only MCP
server. A tool call is logged as `tool_call_invoked` and `tool_result_received`
when it arrives; `read_notifications` parks the way it does for any seat, and
the HTTP request stays open until the wake.

**The CLI drives its own loop.** Each cycle is one CLI process: `claude --print`
or `codex exec`, given the platform's initial prompt first, and its continuation
prompt whenever the CLI ends a turn before the run has ended for the seat. A
later process resumes the CLI's session, so the conversation carries across
processes. A seat that parks in `read_notifications` round after round stays in
one process for the whole run.

**Environment.** Claude Code is started without the inherited `CLAUDE*`
variables and `ANTHROPIC_IDENTITY_TOKEN`, so a run started from inside a Claude
Code session does not hand that session's variables, or another credential, to
its seats; `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` pass through. Codex is
started without the inherited `CODEX*` variables and uses `OPENAI_BASE_URL` when
it is set, through a model provider the harness defines.

| | Claude Code | Codex |
|---|---|---|
| Command | `claude --print --output-format json`, `--resume` after the first turn | `codex exec --json`, `codex exec resume` after the first turn |
| Prompt replaces | Claude Code's system prompt (`--system-prompt`) | Codex's model instructions (`model_instructions_file`) |
| Tools of its own | off (`--tools ""`, no settings files, `--strict-mcp-config`) | off (the features in `codex.py`); `AGENTS.md` is not read |
| Sandbox | not applicable | `danger-full-access`: under any other mode, `codex exec` with `approval_policy="never"` denies every MCP call and reports it as cancelled by the user (Codex 0.147.0) |
| Reasoning | off (`MAX_THINKING_TOKENS=0`) | effort `high`, summary `concise`, as for a pydantic-ai OpenAI seat |
| `agent_max_tokens` | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | not applied: Codex has no per-response cap |
| Private state | `harness_state/claude_config/` | `harness_state/codex_home/` |
| Transcripts | `claude_config/projects/`, copied to `transcripts/` | `codex_home/sessions/`, copied to `transcripts/` |

The seat's directory is `harness/<agent_id>/` inside the run. `harness_state/`
holds the CLI's private state and, under `turns/`, each turn's stdout and
stderr; the archive filter excludes it. The CLI's transcripts are copied to
`transcripts/` when the seat ends.

## How a seat in a CLI differs

A seat in a CLI sees the same system prompt and the same tools, as the CLI
presents them (Claude Code prefixes their names with `mcp__glossogen__`). Its
log records its tool calls, so messages, round verdicts, exports and the run
viewer read it the way they read any seat. What the platform does not see is
the model's responses, and that is where the differences come from.

### Refused

These apply to every harness but `pydantic-ai`: the shipped CLI harnesses and
any installed from a package alike.

| Flow | Result |
|---|---|
| `--resume`, `fork-at-round`, `replace-agent` keeping the seat | refused: its conversation is the CLI's, and its log holds no model responses to rebuild a history from |
| `replace-agent` replacing the seat | allowed, onto `pydantic-ai` |
| `cross-run-replace-agent` importing the seat from source B | refused, for the same reason |
| `replace-agent` or `cross-run-replace-agent` onto another harness | refused: a replacement is seeded with a rebuilt history |
| `scheduled_events` swap onto another harness | refused at launch, for the same reason |
| A scenario whose `requires_gated_model_responses` is True | refused for a harness whose `gates_model_responses()` is False, as the shipped CLI harnesses are. `textcraft_shared_workspace` answers True under `virtual_clock`; a scenario that overrides `gate_model_response` and not this hook answers True |

### Behaves differently

| | `pydantic-ai` | `claude-code` and `codex` |
|---|---|---|
| What is logged per model response | `llm_response_received` with text, thinking, tool calls, stop reason and usage | nothing: the response never passes through the platform |
| Usage and cost | per response | per CLI turn, from what the CLI reports when its process exits (`cli_turn_completed`); the run's cost sums these |
| A `read_notifications` call issued beside other calls | refused, from the response's other calls | not detected: the server sees one call at a time, so the call parks |
| `gate_model_response` | awaited before the response's tools run | never called |
| `--max-agent-turns` | counts cycles; a cycle ends when the agent ends its turn | counts CLI processes; a seat that keeps parking stays in one |
| A failed model request | 3 attempts with exponential backoff | the CLI's own retry policy; a turn that exits non-zero or reports an error is logged as `agent_run_cycle_failed`, the next cycle resumes the session, and after `MAX_CONSECUTIVE_TURN_FAILURES` failed turns in a row the seat stops. Before each cycle that follows a failed one the runner pauses 30 s, doubled for each earlier failure in the row |
| The `compaction` knob | compacts at the knob's threshold | ignored, with a warning at start: the CLI compacts on its own schedule, and nothing of it is logged |
| The run ending while a turn is open | not applicable | the wake tells the model the run is over; a process still running 60 s later is terminated |
| Langfuse traces | recorded | none |

## Writing a harness

A harness can live in its own package, with no change to this repository. The
package declares one entry point, under a group naming the contract version:

```toml
[project.entry-points."glossogen.agent_harnesses.v1"]
my_harness = "my_harnesses.harness:MyHarness"
```

Installed beside glossogen, the harness is selectable everywhere the shipped
ones are: `--harness` and `agents.<id>.harness=` on `run`, `--harness` on
`replace-agent` and `cross-run-replace-agent` (accepted, then refused as for
any harness but `pydantic-ai`), MCP `start_run`, and the launch check, which
calls its `preflight` before a run directory is claimed. The entry-point name
must equal the class's `name()`. It implements `AgentHarness`
([src/glossogen/runners/harness_protocol.py](../src/glossogen/runners/harness_protocol.py)):

| Member | Answers |
|---|---|
| `name()` | what a seat selects and records |
| `preflight(seats)` | what the environment lacks for these seats, as remedies; empty when ready |
| `gates_model_responses()` | whether its runner awaits `gate_model_response` before a response's tools run |
| `build_runner(context)` | an `AgentRunner` for one seat |

**A harness over another agent CLI needs only a CLI definition.** Implement
`AgentCli` ([cli_protocol.py](../src/glossogen/runners/external_cli/cli_protocol.py)),
which says how to start the CLI for one turn pointed at the seat's tool
endpoint, what environment to give it, how to read the turn's session id,
usage and failure from its output, and where it keeps its transcripts, and
return an `ExternalCliRunner` from `build_runner`. The runner serves the tools,
runs the processes, logs the turns, prices the usage and copies the transcripts.
The shipped CLI harnesses are built this way.

A harness that drives the model loop itself writes its own `AgentRunner`. Its
`start` runs the seat until a `read_notifications` wake ends the run for it,
and it must log what the rest of the platform reads: `tool_call_invoked` and
`tool_result_received` per call, `agent_run_cycle_failed` when a cycle fails
and the runner moves on, and `llm_response_received` per model response when
it sees them, or `cli_turn_completed` with the usage when it does not. It must
call `runtime.scenario.on_agent_retired(agent_id)` as `start` returns, and keep
`cost_tracker[agent_id]` current, which `AgentCostAccumulator` does.

**Refuse a reconstructed history.** A runner given `initial_message_history` it
cannot use must raise. The launch check already keeps swaps and replacements off
any harness but `pydantic-ai`.

## What a harness package cannot change

| Limit | Why |
|---|---|
| A seat's provider is one the platform already has | Pricing, the credential check, `model_class` and the token counter all key on the `Provider` enum in [model_catalog.py](../src/glossogen/model_catalog.py) |
| A name glossogen ships cannot be taken | `pydantic-ai`, `claude-code` and `codex` resolve to the shipped harnesses; a package declaring one of those names is ignored, and the collision is logged |
| The contract version must match | A package declared under another `glossogen.agent_harnesses.v<N>` group is not read. The CLI's `--harness` and `agents.<id>.harness=` reject its name as unknown, and so does a `model_overrides` entry given to MCP's `start_run`; its top-level `harness` reports the group it used and the one the platform reads |
| A harness that fails to load fails the launch | An import error, a class that is not an `AgentHarness`, or a `name()` that disagrees with the entry point is reported when a launch names it |
| A hosted backend needs the CLI | The backend image carries no agent CLI, so the shipped CLI harnesses are refused there by `preflight` |
| Langfuse traces cover pydantic-ai seats | A runner of your own can emit its own OpenTelemetry spans; the platform's tracing does not record them |

## Testing a harness

`run_mixed_harness_simulation` in `glossogen.testing.simulation_harness` runs a
scenario with some seats on runners the test builds and the rest on
pydantic-ai. Each `RunnerSeat` names its harness and builds its runner from
the run's `RunnerBuildContext`. The shipped CLI harnesses are tested with
`ExternalCliRunner` over a stand-in CLI in `tests/fakes/fake_mcp_cli.py`, a
script that connects to the seat's endpoint over MCP and plays a script, so
the tool server, the runner and the log run for real with no CLI installed.

## Next

- [Running simulations](running-simulations.md) for the run command and costs.
- [Agent swaps](agent-swaps.md) for the flows a CLI seat is refused from.
- [Testing a scenario](testing-a-scenario.md) for the scripted-agent harness.
