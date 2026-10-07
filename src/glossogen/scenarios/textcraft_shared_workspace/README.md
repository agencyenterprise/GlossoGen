# textcraft_shared_workspace

A team of crafters builds every target of a synthetic recipe grid from one finite,
shared depot. Nobody coordinates them. Each agent sees the whole task and the live
depot, decides for itself what to craft, and can talk to the others on one public
channel. The depot is public state every agent reads and changes. The channel is
the only way to say anything about plans.

The scenario asks when a team beats a single agent on the same task, and what the
team spends on coordination to get there: duplicated crafts, inputs consumed by the
wrong teammate, messages, tokens and simulated time. Every quantity is
deterministic and the verdict needs no judge.

It is the first scenario on the `workspace_action` interaction protocol, which
delivers messages inside tool results and suspends an agent instead of having it
poll. See [Tools](#tools).

## Task

A task is a grid of recipes `crafter_count` columns wide and `steps_per_agent`
layers deep. Each column ends in one target. The first layer consumes raw items
from the depot. Every later recipe consumes its own column's previous output and,
with probability `dag_cross_edge_density`, a neighbouring column's previous output
too (at most `dag_max_fan_in` inputs from that layer). Work is
`crafter_count * steps_per_agent` crafts and the critical path is
`steps_per_agent` crafts long, whatever the density. Density zero gives independent
chains.

Recipe yields are exactly what the grid consumes, plus one of each target to keep.
Raw items are supplied for the exact need, plus `resource_slack_fraction` of it
rounded up. Item names are opaque IDs (`r123456`), so nothing an LLM remembers
about Minecraft helps. Recipes use TextCraft's command syntax:
`craft 2 r123456 using 1 r234567, 1 r345678`.

Every task carries a witness, one order of crafts that solves it, and is replayed
against it before the round starts. The witness proves the task feasible. It says
nothing about whether a team will find it.

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
hands as even as possible and the same for the same task in every arm, so a
teammate holds recipes you were not dealt. An agent may run any recipe whose exact
command it has.

The team shares one pool of workspace actions:
`actions_per_witness_step` attempts per witness step, so a team of any size gets
the same total.

## Tools

| Tool | From | Cost | What it does |
|---|---|---|---|
| `act(command)` | scenario | one action | Runs one craft (or `uncraft <craft command>` when `uncraft_enabled`). Returns the result, the depot and unseen messages |
| `observe()` | scenario | free | Returns the depot, the changes since this agent last looked, and unseen messages |
| `send(text, to, reply_to)` | runtime | characters | Broadcasts, or addresses teammate IDs in `to`. The receipt carries the depot and unseen messages |
| `wait_for_message(timeout_s)` | runtime | free | Suspends the agent until a message it can see arrives, a lifecycle event, or the timeout |
| `finish()` | runtime | free | Suspends the agent until the next round or the end of the run |

A message reaches each recipient exactly once, inside whichever result it receives
next, under a `NEW PUBLIC MESSAGES` header. Nobody polls a channel.

The runner intercepts `wait_for_message` and `finish` before any tool runs, parks
the agent without making model requests, and answers the call with a wake package
holding the wake reasons, the depot and the messages that arrived. Either call must
be the only call in its response. A turn that ends in text with no tool call counts
as `finish`.

With `comms_enabled = false` agents get `act`, `observe` and `finish` only, and no
prompt or result mentions messages. On this protocol the channel browsing tools
(`send_message`, `read_channel`, `list_channels`, `get_channel_members`) are never
listed.

TextCraft's `depot` and `wait` commands are refused by `act` at no cost, pointing
the agent at `observe`.

## Round end and scoring

A round ends at the first of:

| Trigger | When |
|---|---|
| `all_targets_satisfied` | Every target is in the depot at once |
| `actions_exhausted` | The team's action pool is spent and no timed craft is still running |
| `team_tokens_exhausted` | The team's prompt plus completion tokens this round passed `team_token_limit` |
| `budget_exhausted` | Messages passed `round_time_budget_seconds` characters |
| `all_agents_finished` | Every agent is parked on `finish` |
| `all_agents_waiting` | Every agent is parked with no deadline, so nothing can change any more |
| `round_timeout` | `max_round_duration_seconds` of wall-clock time passed |

The round succeeds when every target coexists in the depot and the character
budget was not exceeded. Having made a target earlier does not count if it was
consumed since. `round_success` reads the verdict, and `workspace_round_resolved`
records it with the trigger, characters, actions per agent, accepted transitions,
failed crafts, targets satisfied, the final depot and, under the virtual clock, the
virtual makespan.

## Virtual clock

A local inference server shares one GPU, so how long a request takes, and which
agent acts first, depends on what teammates are generating at the same moment.
`virtual_clock = true` removes that: each request costs
`virtual_base_latency_s + output_tokens / virtual_output_tokens_per_second`
simulated seconds from its own usage, and the runtime releases responses in that
order whatever the server did. Tool calls take no virtual time, except a craft
under `craft_duration_s`, which keeps its crafter busy for that long while
teammates act. `wait_for_message` timeouts count virtual seconds. Wall-clock limits
still apply as a safety net.

A `read_notifications` call that blocks holds the virtual clock's execution slot
until it returns, up to five seconds of wall-clock time. It costs no virtual time,
and the protocol tells agents to call it only at startup.

## Knobs

| Knob | Meaning |
|---|---|
| `crafter_count`, `steps_per_agent` | Grid width and depth |
| `dag_cross_edge_density`, `dag_max_fan_in` | How often, and how much, a recipe draws on neighbouring columns |
| `quantity_scale`, `dag_raw_material_count`, `dag_max_raw_inputs`, `resource_slack_fraction` | Raw item quantities, variety and slack |
| `task_manifest` | Replay tasks from a file instead of generating them |
| `pool_agent_count` | Team size; 1 is the single-agent baseline |
| `recipe_holders` | Deal each recipe to this many agents instead of to all |
| `actions_per_witness_step` | Team action pool per witness step |
| `team_token_limit` | Team token budget per round |
| `comms_enabled`, `round_time_budget_seconds` | Whether the channel exists, and its character budget (-1 unlimited) |
| `uncraft_enabled` | Allow `uncraft` to reverse a craft |
| `virtual_clock`, `virtual_base_latency_s`, `virtual_output_tokens_per_second`, `craft_duration_s` | Simulated API latency and craft time |

`send_back_thinking = false` keeps a self-hosted model's earlier reasoning out of
later requests, and `compaction` trims a self-hosted agent's history locally.

## Presets

| Preset | Condition |
|---|---|
| `knobs_default` | Three agents, every recipe each, messaging on |
| `knobs_no_comms` | The same team with no channel |
| `knobs_recipe_split` | Each recipe dealt to one agent, messaging on |
| `knobs_single_agent` | One agent with the whole task |

All four play the same 4 x 2 grid under the virtual clock with a token budget, so
they compare directly.

## Events

| Event | Holds |
|---|---|
| `workspace_task_started` | The full task, which no agent ever sees whole |
| `workspace_recipes_dealt` | Each agent's hand, under `recipe_holders` |
| `workspace_action_executed` | Every `act`: command, acceptance, depot delta, provenance of consumed inputs |
| `workspace_craft_completed` | A timed craft's output landing |
| `workspace_message_context_delivered` | Which messages a result carried to which agent |
| `workspace_round_resolved` | The verdict and the round's counts |

The runtime adds `wait_registered`, `agent_resumed`, `model_request_completed`
and, under the virtual clock, `virtual_request_released`.

## Quickstart

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run textcraft_shared_workspace \
  --model Qwen/Qwen3.5-27B --provider self-hosted --runs-dir ./runs \
  --config knobs_default \
  > ./runs/textcraft_shared_workspace_stdout.log 2>&1 &
```

## Files

- `scenario.py`: briefing, tools, message delivery and the verdict
- `world.py`: action, token and character budgets, and the round's terminal rule
- `state.py`: depot transitions, observation cursors, uncraft and timed crafts
- `tasks.py`: the grid generator, certification and manifest loading
- `recipe_dealing.py`: the `recipe_holders` deal
- `knobs.py`, `knobs_*.json`: factors and presets
- `events.py`: the events above
- `prompts/`: system prompt, round briefing and description
- `scripts/write_task_manifest.py`: writes a manifest for `task_manifest`
