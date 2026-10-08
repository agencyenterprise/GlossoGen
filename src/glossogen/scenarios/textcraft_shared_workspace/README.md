# textcraft_shared_workspace

A team of crafters builds every target of a synthetic recipe grid from one finite,
shared depot. Nobody coordinates them. Each agent sees the whole task and the live
depot, decides for itself what to craft, and can talk to the others on a broadcast
channel or address chosen teammates directly. The depot is public state every agent
reads and changes. Messages are the only way to say anything about plans.

A run records whether a team solves a task that a single agent also faces, and what
it spent: messages, tokens, failed crafts, each action's depot change with the
provenance of the inputs it consumed, and simulated time. The verdict and every
count are computed from the event log, with no judge.

Messages reach agents inside tool results, and an agent waits for a teammate or
declares its round finished instead of polling. See [Tools](#tools).

## Task

A task is a grid of recipes `crafter_count` columns wide and `steps_per_agent`
layers deep. Each column ends in one target. The first layer consumes raw items
from the depot. Every later recipe consumes its own column's previous output and,
with probability `dag_cross_edge_density`, another column's previous output too (at
most `dag_max_fan_in` inputs from that layer). Work is
`crafter_count * steps_per_agent` crafts and the critical path is
`steps_per_agent` crafts long, whatever the density. Density zero gives independent
chains.

Recipe yields are exactly what the grid consumes, plus one of each target to keep.
Raw items are supplied for the exact need, plus `resource_slack_fraction` of it
rounded up. Item names are opaque IDs (`r123456`), so nothing an LLM remembers
about Minecraft helps. Recipes use TextCraft's command syntax:
`craft 2 r123456 using 1 r234567, 1 r345678`.

Every task carries a witness, one order of crafts that solves it, and is replayed
against it when the scenario is built. The witness shows the task is feasible; it
does not test whether a team finds that order.

Tasks are generated from `seed` plus the round index, or replayed from
`task_manifest`, a JSON list of tasks. Every arm of an experiment should replay the
same manifest so they play the same instances.
[scripts/write_task_manifest.py](scripts/write_task_manifest.py) writes one.

## Agents and briefing

`pool_agent_count` agents take part (`crafter_count` when unset). The grid width
and the team size are separate: three agents can share a four-column grid, and one
agent alone is the single-agent baseline for the same task.

Every agent is briefed with every target and the initial depot, and no target or
column is assigned to anyone. With `recipe_holders` unset every agent also holds
every recipe. With `recipe_holders = k`, each recipe is dealt to `k` agents, the
hands as even as possible and the same for the same task, `recipe_holders` and team
size, so a teammate holds recipes you were not dealt. An agent may run any recipe whose exact
command it has.

The team shares one pool of workspace actions:
`actions_per_witness_step` attempts per witness step, so a team of any size gets
the same total.

## Tools

| Tool | Cost | What it does |
|---|---|---|
| `act(command)` | one action | Runs one craft (or `uncraft <craft command>` when `uncraft_enabled`). Returns the result, the depot and unseen messages |
| `observe()` | free | Returns the depot, the changes since this agent last looked, and unseen messages |
| `send_message(text, to)` | characters | Broadcasts, or with `to` addresses those teammates on a direct channel. The receipt carries the depot and unseen messages |
| `read_notifications(wait_for, timeout_s)` | free | `read_notifications()` at startup returns the briefing. `wait_for="message"` parks the agent until a teammate's message, the next briefing, or the timeout. `wait_for="next_round"` declares the round finished and parks it until the next briefing |

A message reaches each recipient at most once, inside the next result that
recipient receives, under a `NEW PUBLIC MESSAGES` header. Nobody polls a channel.

`act`, `observe` and the send receipt are the scenario's. `send_message` is the
platform tool with the scenario's executor; its parameters are `text` and `to`. A
`to` naming a set of teammates posts on the direct channel for that set, created
the first time; a `to` naming every teammate posts on the broadcast. Direct messages
are charged to the same character budget and noised like the broadcast. `read_notifications` is the platform's runner-side
wait: no model request is made while an agent is parked, and the scenario renders
the result as a wake package holding the wake reasons, the depot and the messages
that arrived. A plain `read_notifications()` waits until something arrives, with no
default timeout. It must be the only call in its response.

With `comms_enabled = false` agents get `act` and `observe`, and no prompt or result
mentions messages. The channel browsing tools (`read_channel`, `list_channels`,
`get_channel_members`) are never offered, and `send_message` is withheld when
messaging is off.

TextCraft's `depot` and `wait` commands, and a `think:` line, are refused by `act`
at no cost, pointing the agent at `observe`.

## Round end and scoring

A round ends at the first of:

| Trigger | When |
|---|---|
| `all_targets_satisfied` | Every target is in the depot at once |
| `actions_exhausted` | The team's action pool is spent and no timed craft is still running |
| `team_tokens_exhausted` | The team's prompt plus completion tokens this round passed `team_token_limit` |
| `budget_exhausted` | Messages passed `round_time_budget_seconds` characters |
| `all_agents_finished` | Every agent is parked on `read_notifications(wait_for="next_round")` with no `timeout_s` |
| `all_agents_waiting` | Every agent is parked with no deadline, so nothing can change any more |
| `round_timeout` | `max_round_duration_seconds` of wall-clock time passed |

The round succeeds when every target coexists in the depot and the character
budget was not exceeded. Having made a target earlier does not count if it was
consumed since. `round_success` reads the verdict, and `workspace_round_resolved`
records it with the trigger, characters, actions per agent, accepted transitions,
failed crafts, targets satisfied, the final depot and, under the virtual clock, the
virtual makespan.

## Virtual clock

With one inference server shared by all agents, request latency and response order
depend on the other agents' concurrent requests. `virtual_clock = true` removes
that: each request costs
`virtual_base_latency_s + output_tokens / virtual_output_tokens_per_second`
simulated seconds from its own usage, and responses are released in that order
whatever the server did. Tool calls take no virtual time, except a craft under
`craft_duration_s`, which keeps its crafter busy for that long while teammates act.
`read_notifications` timeouts count virtual seconds. Wall-clock limits still apply.

The clock lives in this scenario ([virtual_clock.py](virtual_clock.py)) and runs on
the platform's clock hooks: the scenario starts a request's latency in
`on_model_request_started`, holds each response in `gate_model_response` until its
virtual turn, arms wait timeouts in `schedule_wait_timeout`, and tracks parked,
retired and swapped-in agents. Each release logs `workspace_request_released`.

## Knobs

| Knob | Meaning |
|---|---|
| `crafter_count`, `steps_per_agent` | Grid width and depth |
| `dag_cross_edge_density`, `dag_max_fan_in` | How often, and how much, a recipe draws on other columns |
| `quantity_scale`, `dag_raw_material_count`, `dag_max_raw_inputs`, `resource_slack_fraction` | Raw item quantities, variety and slack |
| `task_manifest` | Replay tasks from a file instead of generating them |
| `pool_agent_count` | Team size; 1 is the single-agent baseline |
| `recipe_holders` | Deal each recipe to this many agents instead of to all |
| `actions_per_witness_step` | Team action pool per witness step |
| `team_token_limit` | Team token budget per round |
| `comms_enabled`, `round_time_budget_seconds` | Whether the channel exists, and its character budget (-1 unlimited) |
| `uncraft_enabled` | Allow `uncraft` to reverse a craft |
| `virtual_clock`, `virtual_base_latency_s`, `virtual_output_tokens_per_second`, `craft_duration_s` | Simulated API latency and craft time |

## Presets

| Preset | Condition |
|---|---|
| `knobs_default` | Three agents, every recipe each, messaging on |
| `knobs_no_comms` | The same team with no channel |
| `knobs_recipe_split` | Each recipe dealt to one agent, messaging on |
| `knobs_single_agent` | One agent with the whole task |

The presets share the grid (`crafter_count` 4, `steps_per_agent` 2), the virtual
clock and the token budget, and differ in team size, `comms_enabled` and
`recipe_holders`.

## Events

| Event | Holds |
|---|---|
| `workspace_task_started` | The full task, including the witness, which agents are not shown |
| `workspace_recipes_dealt` | Each agent's hand, under `recipe_holders` |
| `workspace_action_executed` | Every `act` that costs an action: command, acceptance, depot delta, provenance of consumed inputs |
| `workspace_craft_completed` | A timed craft's output landing |
| `workspace_message_context_delivered` | Which messages a result carried to which agent |
| `workspace_round_resolved` | The verdict and the round's counts |

The scenario adds `workspace_request_released` under the virtual clock. The
platform adds `wait_registered`, `agent_resumed` and, for direct channels,
`channel_created`.

## Quickstart

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run textcraft_shared_workspace \
  --model Qwen/Qwen3.5-27B --provider self-hosted --runs-dir ./runs \
  --config knobs_default \
  > ./runs/textcraft_shared_workspace_stdout.log 2>&1 &
```

## Files

- `scenario.py`: briefing, tools, message delivery, the wake rendering, the clock hooks and the verdict
- `tool_results.py`: the send receipt and wake package agents read
- `virtual_clock.py`: simulated API latency and craft time
- `world.py`: action, token and character budgets, and the round's terminal rule
- `state.py`: depot transitions, observation cursors, uncraft and timed crafts
- `tasks.py`: the grid generator, certification and manifest loading
- `recipe_dealing.py`: the `recipe_holders` deal
- `knobs.py`, `knobs_*.json`: factors and presets
- `events.py`: the events above
- `prompts/`: system prompt, round briefing, description, and the runner prompts that teach the protocol (`protocol_*.jinja`)
- `scripts/write_task_manifest.py`: writes a manifest for `task_manifest`
