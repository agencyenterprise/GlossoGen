# ATIF export

`glossogen export-atif` writes a run's agents as
[ATIF](https://docs.harborframework.com/agents/atif) (Agent Trajectory
Interchange Format) trajectories: one JSON document per agent, holding its
prompts, responses, tool calls and token usage in a schema other agent tooling
reads.

```bash
glossogen export-atif veyru \
  --run-dir ./runs/veyru/1782395813 \
  --out-dir ./atif
```

It logs one line per trajectory written, with its step count.

| Flag | Effect |
|---|---|
| `--run-dir DIR` | the run to export (required) |
| `--out-dir DIR` | where to write `<agent_id>.json`, created if missing (required) |
| `--agent-id ID` | only this agent; omit for every agent |
| `--round R` | exclusive cutoff, as for `export-thread`: keeps rounds `1..R-1` |

Trajectories are generated from the JSONL event log on each call. Nothing is
written to the run directory.

## Other ways to get it

| Surface | Call |
|---|---|
| REST | `GET /api/g/{slug}/runs/{scenario}/{run_dir_name}/agents/{agent_id}/atif?round=R` |
| MCP | `export_agent_atif` with `run_id`, `agent_id`, `cutoff_round` |
| Raw zip | the export modal's raw tab (on by default), `glossogen export --raw --include-atif`, or `include_atif` on `POST .../runs/export/raw` |
| Single-run zip | always included in a run's zip download |

REST and MCP return `{"trajectories": [...]}` for one agent. The raw zip writes
every agent of every selected run under `atif/` in that run's folder, as described
in [exporting runs](exporting-runs.md#what-the-raw-zip-holds).

## How events map to steps

| ATIF | Comes from |
|---|---|
| `session_id` | the run id, `<scenario>/<run_dir_name>` |
| `agent` | the agent's `agent_registered` event: role and model, [tool definitions](#tool-definitions); `agent_id`, provider, channels and the agent's `model_settings` (output cap, thinking level) under `extra` |
| `system` step | the registered system prompt, then each context compaction summary |
| `user` step | the prompt the runner opens each agent cycle with: the initial prompt on a fresh agent, the continue prompt after that |
| `agent` step | each LLM response: text, `reasoning_content`, `tool_calls` |
| `observation` | the tool results, matched to their call by `tool_call_id` |
| root `extra` | scenario name, `scenario_config`, cutoff round, generation |

Scenario injections, world events and the other agents' channel messages are not
steps of their own. The model receives them as the results of its
`read_notifications` and `read_channel` calls, and that is where a trajectory
holds them. Round verdicts and postmortem phases are not part of any trajectory;
read the event log or the [CSV tables](exporting-runs.md) for those.

An agent step from the run above, with the tool result cut short:

```json
{
  "step_id": 6,
  "timestamp": "2026-06-25T13:57:19.992503+00:00",
  "source": "agent",
  "message": "Let me check the comm link to see what happened, then engage the engineer in discussion.",
  "model_name": "claude-opus-4-7",
  "tool_calls": [
    {
      "tool_call_id": "toolu_01GwfhcK6SBU7CBmaENzoJG3",
      "function_name": "read_channel",
      "arguments": {"channel_id": "link", "last_n": 20}
    }
  ],
  "observation": {
    "results": [
      {
        "source_call_id": "toolu_01GwfhcK6SBU7CBmaENzoJG3",
        "content": "{\"current_round\": 1, \"messages\": [{\"round\": 1, \"sender\": \"Field Observer\", \"text\": \"Vri al"
      }
    ]
  },
  "extra": {"round_number": 1, "stop_reason": "tool_use"}
}
```

An agent step's `timestamp` is when its first tool call was invoked. The response
event itself is logged after the calls return, so for a slow tool that is after
events the agent had not yet seen. A runner-prompt step has no timestamp: the log
records when a cycle's turns happened, not when its prompt was sent.

A cycle that raised before producing a response is recorded on the next agent
step as `extra.failed_cycles`. Cycles that fail after the last response are
recorded on the trajectory's root `extra` as `failed_cycles_after_last_response`.

## Token usage is per cycle

The runner logs token usage once per agent cycle, on that cycle's last response.
Only those steps carry `metrics`, and their `llm_call_count` is the number of
responses in the cycle they close. A cycle can span many rounds: in the run
above, the stabilization engineer's 109 steps hold one with metrics, closing a
cycle of 107 responses:

```json
{
  "llm_call_count": 107,
  "metrics": {
    "prompt_tokens": 34352270,
    "completion_tokens": 92070,
    "cached_tokens": 34164983,
    "cost_usd": 20.5544015,
    "extra": {"cache_creation_input_tokens": 186980}
  }
}
```

`prompt_tokens` includes cached tokens, as ATIF defines it. `cost_usd` uses the
platform's [pricing table](running-simulations.md#understanding-cost), and it is
absent for a model that table does not price.

`final_metrics` sums the steps played in this run. A [copied step](#copied-context)
keeps its metrics, but its source run already counts that spend, so the totals
leave it out. When no played step carries metrics, the token and cost totals are
absent rather than zero: the same run's field observer never closed a cycle, so
its 176 steps carry no metrics and its `final_metrics` holds only `total_steps`.

## Tool definitions

`agent.tool_definitions` lists each tool the agent was offered, with its name,
description and JSON `input_schema`. `agent.extra.tool_definitions_source` says
where they came from:

| Source | Meaning |
|---|---|
| `recorded` | logged on the agent's `agent_registered` event when the run launched |
| `reconstructed` | the run predates that, so the scenario was rebuilt from its recorded config and its tools listed at export time |
| `names_only` | neither worked, for instance the scenario is no longer installed, so each entry has a `name` only |

A `reconstructed` schema describes the code installed at export time, not the
code the run used. Tool descriptions get edited, and some read knob values, which
is why the rebuild uses the run's recorded config rather than a preset.

## Swapped and replaced seats

A seat produces one trajectory per generation. A new generation starts at an
in-run swap, at the first launch of a replace-agent or cross-run run's replaced
seat, and at any re-registration under a different model. Files are named
`<agent_id>.gen1.json`, `<agent_id>.gen2.json` and so on, with matching
`trajectory_id`s. A resume under the same model continues the same trajectory,
with a continue-prompt step where the relaunched runner picked the agent up.

A swapped-in generation's system step is the prompt the swap seeded its agent
with: the swap's own when the scheduled event set one, otherwise the seat's
registered prompt. The event records which, so a swap logged before that was
recorded shows the registered prompt either way.

## Copied context

A step with `"is_copied_context": true` is history the agent received rather than
played in this run. Which steps carry it depends on how the run was made:

| Run | Copied steps |
|---|---|
| fork-at-round | every step up to the boundary event its manifest names |
| replace-agent | the same for the agents that kept their seats, and for the predecessor's generation of the replaced seat, which is all copied. The replaced seat's new generation opens with its seed: the predecessor's tool calls on the channels it was allowed to see |
| cross-run replace-agent | the same, except the imported seat's seed is its history from the run it came from |
| in-run swap | the swapped-in trajectory opens with its seed, built at the swap round |
| plain `--resume` | none, since it continues the same run |

A seed is rebuilt with the filter the run used when it launched, and its steps
have no `timestamp` or `metrics`, since the history they come from records
neither. In the replace-agent run `veyru/1780729770`, the replaced field observer
has two files: `gen1` holds the predecessor's 71 steps, all copied, and `gen2`
has 78 steps, 71 of them seed, followed by the continue prompt and the steps
played after the boundary.

## Checking a file against the spec

The spec's Pydantic models ship in the `harbor` package. This validates an
exported file against them without adding that package to the project:

```bash
uv run --no-project --python 3.12 --prerelease=allow --with harbor python -c '
import json, sys
from harbor.models.trajectories import Trajectory
Trajectory.model_validate(json.load(open(sys.argv[1])))
print("valid")' ./atif/field_observer.json
```

## Next

- [Exporting runs](exporting-runs.md) for CSV tables and raw run folders
- [Evaluation](evaluation.md#exporting-an-agents-thread) for an agent's thread as a provider request body
- [MCP integration](mcp-integration.md) for the other run-browsing tools
