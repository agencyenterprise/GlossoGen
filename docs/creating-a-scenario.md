# Creating a scenario

A scenario is one self-contained N-agent coordination task. This page is the
reference for every file in a scenario package and every extension surface, in
the order you meet them when editing a generated package into your own scenario.

A scenario owns:

- **A team declaration** — the roles, the comm topology, who can read and send
  what, stated as data the engine derives the run from.
- **Tools** — the MCP tools each agent can call beyond the platform's
  `read_notifications` / `read_channel` / `send_message`.
- **A world** — the live environment that emits notifications, validates tool
  results, tracks state, and decides round success. `RoundWorld` when it meters a
  per-round budget, plain `ScenarioWorld` when it meters nothing.
- **Knobs and presets** — the Pydantic-validated configuration the CLI and
  frontend expose.
- **Per-round injections** — the round-start text each agent receives, rendered
  from Jinja templates.
- **Optional surfaces** — scenario-specific metrics, run-detail data on the API,
  and a frontend plug-in, all opt-in.

Events, run-detail extensions and frontend plug-ins are discovered automatically.

## Start from the generator

Generate a package rather than assembling one:

```bash
glossogen new-scenario reactor_purge --target-dir .
cd reactor-purge
glossogen validate .
pip install -e ".[testing]"
pytest
```

What you get already runs: two agents relay a code word over a metered link,
`validate` passes, the tests pass, and `glossogen run` completes. Editing one
thing at a time and watching what breaks is a faster way through this contract
than writing it from scratch, and the generated README lists what to change in
which order. (Working inside a glossogen checkout, glossogen itself is already in
the environment: install the package with `uv pip install -e . --no-deps`, and
re-run that line after any `make install-*`, since `uv sync` removes anything the
lockfile does not name.)

Two details in the generated `pyproject.toml` fail long after a mistake, so know
they are there:

- `[tool.setuptools.package-data]`. Without it only `.py` files are packaged. An
  editable install still works, so the omission survives until someone installs
  the wheel and the first template render fails.
- The entry-point key equals what `name()` returns. Declared differently, runs
  land in `runs/<name()>/` while every command addresses them by the launch name,
  so none of them find the run and nothing looks wrong at the time. The generated
  test checks this with `assert_scenario_is_registered`.

The package:

```
reactor-purge/
├── pyproject.toml               # entry point + package-data
├── tests/                       # the scripted round loop; see Testing a scenario
└── reactor_purge/
    ├── __init__.py              # stays empty (below)
    ├── ids.py                   # agent ids, channel ids, tool names, markers
    ├── knobs.py                 # Pydantic knobs extending BaseKnobs
    ├── knobs_default.json       # the canonical preset
    ├── events.py                # EventBase subclasses, auto-discovered
    ├── team_declaration.py      # teams, roles, channels, as data
    ├── world.py                 # live state + reactions
    ├── scenario.py              # the SimulationScenario contract
    └── prompts/                 # every word an agent or judge reads
```

**The package `__init__.py` stays empty, and `events.py` imports only
[`glossogen.models.event_base`](../src/glossogen/models/event_base.py).** Event
discovery imports your `events` module while `glossogen.models.event` is itself
mid-import, so anything that pulls the wider module in closes that cycle and the
platform fails at startup. `validate` checks both.

## The files, and what to change in each

Nothing enforces this split; it is convention, and every scenario in the tree
follows it.

| File | Owns | Does not belong here |
|---|---|---|
| `ids.py` | Every literal string used more than once: agent and channel ids, role names, tool names, world marker strings | Anything with behaviour. If it needs an `if`, it belongs elsewhere |
| `knobs.py` | Scenario-specific fields, plus validators rejecting impossible combinations. `seed` belongs here: `BaseKnobs` has none | Anything `BaseKnobs` already declares; redeclaring one shadows the platform's |
| `knobs_default.json` | The canonical preset, the values "by default" means | Experiment presets, which are separate `knobs_*.json` files |
| `events.py` | The scenario's own event types | Imports from `glossogen.models.event` |
| `team_declaration.py` | The teams, and for each its task channel, debrief policy and roles | Prompt text, and anything that varies within a round |
| `world.py` | State that changes during a round, and the reactions to it | Anything read only at round boundaries |
| `scenario.py` | The platform contract: injections, tools, scoring. Structure it derives from the declaration | Mutable per-round state (world's), prose (prompts'), rosters (the declaration's) |
| `prompts/` | Every word an agent or a judge reads | Nothing. No prompt text in Python |

### `ids.py`

Centralize the strings, including the world's marker strings: a fixed prefix on
tool results and `WorldEventDelivered.text` so an agent reading one can tell the
outcome classes apart. Round scoring does not read markers; `round_success` reads
the `RoundResultRecorded` events the game clock writes from `judge_round_result`.
[container_yard_stacking/ids.py](../src/glossogen/scenarios/container_yard_stacking/ids.py)
is a worked example.

### `knobs.py` and the presets

Extend `BaseKnobs` with only your scenario's fields, all required, values in the
presets: a knob with a default is one a preset can omit, and then the run's
recorded config does not say what it ran with.

```python
class WarehouseRobotRecoveryKnobs(BaseKnobs):
    judge_model: str
    judge_provider: str
    round_time_budget_seconds: int
    seed: int
    fault_count_min: int
    fault_count_max: int

    @model_validator(mode="after")
    def _validate_fault_count_bounds(self) -> "WarehouseRobotRecoveryKnobs":
        if self.fault_count_min < 1:
            raise ValueError(f"fault_count_min must be >= 1 (got {self.fault_count_min})")
        if self.fault_count_max < self.fault_count_min:
            raise ValueError("fault_count_max must be >= fault_count_min")
        return self
```

That is
[the real one](../src/glossogen/scenarios/warehouse_robot_recovery/knobs.py).
`BaseKnobs` already carries `round_count`, `max_round_duration_seconds`,
`model_overrides`, `scheduled_events` and the other shared fields.

In `knobs_default.json`, every `BaseKnobs` field without a default has to be
present (`model_overrides` is `{}` when there are none), and the conventions are
`seed: 42` and `judge_model: "claude-haiku-4-5-20251001"` /
`judge_provider: "anthropic"` for a scenario that has a judge. A scenario scoring
its rounds deterministically declares neither judge knob.

### `events.py`

One `EventBase` subclass per scenario event, each with a unique `event_type`
literal. The discovered-union parser picks them up; you never edit
`glossogen/models/event.py`.

```python
from typing import Literal

from glossogen.models.event_base import EventBase


class YardCaseStarted(EventBase):
    event_type: Literal["yard_case_started"] = "yard_case_started"
    case_number: int
    incoming_container: str
```

### `team_declaration.py`

Export one function taking your knobs and returning `tuple[TeamSpec, ...]`, one
entry per isolated group of agents. The engine meters, judges and reports each
team independently.
[`team_declaration.py`](../src/glossogen/engine/team_declaration.py) defines the
types; [`team_structure.py`](../src/glossogen/engine/team_structure.py) turns
them into what the platform asks for.

| Field on `TeamSpec` | States |
|---|---|
| `task` | The `TaskChannel` the team works on. Being the task channel is what makes it metered, corrupted under channel noise, and shut during debrief |
| `debrief` | `Debrief(...)` or `NoDebrief()`. A team with no post-round discussion says so |
| `roles` | One `RoleSpec` per agent: id, role name, system-prompt template, `tool_names`, and the two booleans below |

No field has a default, so omitting one is a type error rather than a silent
behaviour. `tool_names` is the per-agent authorization list the MCP guard
enforces, and it is not additive: a role that talks lists `send_message`, and an
empty list connects an agent that can do nothing. Names are the platform's five
plus whatever `get_mcp_tools()` returns; `validate` rejects a name no tool
answers to.

**`starts_as_member` is not `joins_debrief`.** `joins_debrief` says whether a
role reaches the debrief channel at all. `starts_as_member` says whether the role
is in a channel's roster on round one; which channels it *reaches* is fixed at
construction. Conflate them and a not-yet-arrived agent reads the traffic it was
meant to arrive after. The run completes, the logs look right, and the experiment
answered a different question.
[veyru](../src/glossogen/scenarios/veyru/team_declaration.py) keeps its intern
out until the join round fires;
[container_yard_stacking](../src/glossogen/scenarios/container_yard_stacking/team_declaration.py)
seats its intern from round one, and says so in a comment.

The engine's vocabulary is teams, and a scenario with none should not invent one:
[prisoners_dilemma](../src/glossogen/scenarios/prisoners_dilemma/scenario.py) is
two opponents on one channel with no budget, so it builds its agents directly in
`scenario.py` and has no declaration. Every other scenario declares.

### `world.py`

Subclass `RoundWorld`
([round_world.py](../src/glossogen/engine/round_world.py)) when the scenario
meters a per-round budget, which almost all do; plain `ScenarioWorld`
([scenario_world.py](../src/glossogen/runtime/scenario_world.py)) only when it
meters nothing. The world mutates state synchronously in `on_message`, reacts
asynchronously in `on_message_async` (pushing notifications through
`context.send_update_to_channel`), and holds the state the round verdict reads.
The base class owns the `run` loop; override the hooks, never `run`.

`RoundWorld` provides:

| Provided | Contract |
|---|---|
| Per-team character metering | Override `on_message`, call up so the engine accumulates, read `characters_used(team_id=...)` and apply your budget rule. On a shared task channel the sender's team pays |
| Budget announcements | `claim_round_budget_threshold` answers whether an announcement is still owed this round. Declare `round_budget_thresholds` most severe first: claiming one claims every milder one, so a team is not told its budget is low just after being told it is gone |
| Round history | `RoundOutcomeLog` stores one record per finished round per team, so the debrief injection and the next boundary agree |

Take the specs and channel ids as constructor arguments rather than importing the
ids, so the world and the declaration cannot disagree about which channels exist.
Postmortem messages cost no budget, and the postmortem can be globally disabled
mid-run. The shapes to mimic:
[WarehouseWorld](../src/glossogen/scenarios/warehouse_robot_recovery/world.py)
for a single tool,
[ContainerYardWorld](../src/glossogen/scenarios/container_yard_stacking/world.py)
for sequenced multi-tool state.

### `scenario.py`

The `SimulationScenario` subclass is what the registry hands the CLI, the MCP
`start_run` tool and the run-detail UI. The full contract is
[scenario_protocol.py](../src/glossogen/scenario_protocol.py); the base class
derives the getters (`knobs_json_schema`, `get_round_count`,
`get_scenario_config`, ...) from `knobs_model()` and `get_knobs()`.

| Member | Does |
|---|---|
| `name()`, `scenario_description()` | The registry key; a one-line description read from `prompts/description.jinja` |
| `knobs_model()`, `get_knobs()`, `create_from_config(config)` | Your knobs class; the held instance; the validating factory |
| `get_agent_roles(knobs)` | The `(agent_id, role_name)` pairs preflight validates model overrides against. Takes a possibly-partial `dict \| None`; read role-determining flags with `cls.resolve_bool_knob(...)` |
| `get_agents()`, `get_channels()` | Delegations to `team_structure.build_agent_configs(...)` and `team_structure.channels(...)`, never hand-written lists. You supply the `render_system_prompt` callback |
| `get_world()`, `get_mcp_tools()` | Construct the world from the same specs; one [`ScenarioMcpTool`](../src/glossogen/runtime/scenario_mcp_tool.py) per scenario tool |
| `get_injection(round_number, agent_id)` | The round-start Jinja injection, or `None` for an agent with nothing to hear. Case and previous outcome come from your world |
| `get_postmortem_injection(...)` | Same shape, for the debrief phase |
| `on_round_advanced(round_number)` | Resolve the previous round, load the next case, and log your `<Scenario>CaseStarted` event via `self.runtime.event_logger` |
| `on_round_ended(round_number, trigger)` | Settle round-end state; `trigger` includes your own early-end string |
| `validate_outgoing_message(...)`, `transform_outgoing_message(...)` | Enforce and mutate messages: budget refusal, noise injection |
| `get_early_round_end_trigger()` | Optional: a trigger string when the round should end before the clock |
| `restore_state_from_events(events)` | Optional: seed per-round outcomes after a fork or resume, so the first post-resume injection renders accurate "previous result" context |

Three members deserve more than a row:

- **`judge_round_result(round_number, trigger)`** is required and returns
  `list[RoundResult(success, team_id, reason)]`. The game clock writes one
  `RoundResultRecorded` per element, and the `round_success` metric reads those.
  Despite the name, no LLM is implied: prisoners_dilemma resolves rounds from its
  payoff matrix, veyru calls a judge. Single-team scenarios pass `team_id=None`.
- **`get_primary_channels()`** is required and tells the language and throughput
  metrics what to score: one entry per independently metered channel, which is
  not one per team. Two teams on their own links give two entries carrying
  `team_id`, and metrics report `perplexity_team_a` / `_team_b`. Two teams
  sharing one link give a single pooled entry with `team_id=None`, because there
  is one conversation to score.
  [spot_the_difference](../src/glossogen/scenarios/spot_the_difference/scenario.py)
  does both, switched on a knob.
- **`postmortem_channel_ids`** is a `ClassVar[frozenset[str]]` naming every
  channel that carries postmortem traffic in *any* mode the scenario can run in,
  beyond the current preset's: it outlives the configuration, feeding the
  replaced-agent history filter and the mid-run `set_postmortem` shutdown. Pass
  it to the world as `type(self).postmortem_channel_ids` rather than re-importing
  the ids.

### `prompts/`

Every prompt is a Jinja2 template. `description.jinja`, one `<role>_system.jinja`
and one `<role>_injection.jinja` per role, `postmortem_injection.jinja` when the
scenario debriefs, and one template per LLM judge.

Rendering is strict: a name the template uses but the Python never passes raises
`UndefinedError` instead of resolving empty, so a misspelling fails at render
rather than producing a prompt missing a number or a whole `{% if %}` block. Pass
every name the template mentions, including the ones only a condition reads;
`None` is a value you chose, so `{% if previous_outcome %}` works on round one.
`validate` renders every round's injections against every preset.

## Optional surfaces

### Post-simulation hooks

Implement one to opt into the matching platform metric; the default answer makes
the metric skip with no Measurement.

| Hook | Opts into |
|---|---|
| `build_communication_rounds(events)` | `communication_open_coding`, `communication_feature_presence`; each view joins one round's messages with a scenario-rendered ground-truth block |
| `detect_protocol_boundary_window(events, agent_configs)` | `protocol_learned_after_swap`. Default: the first `AgentSwappedMidRun`. Override for scenario-specific boundaries and fall back to `super()` |
| `get_protocol_probe_config()` | The `protocol_probe` metric family. Ship the question bank and probe templates in your package; [veyru/scenario.py](../src/glossogen/scenarios/veyru/scenario.py) is the canonical wiring |
| `get_protocol_explanation_config()` | Per-role describe templates for `protocol_explanation`, which otherwise runs with a generic prompt |
| `get_judge_models(knobs)` | The launch check that refuses a run whose environment cannot reach your judge, before a round is spent. Default: the `judge_model` / `judge_provider` pair. Override when the judge is conditional or you call more models of your own |
| `get_replace_agent_blocked_tool_call_channels()` | Channels stripped from a replaced agent's reconstructed history. Defaults to `postmortem_channel_ids`, which is usually all you need |

### `evaluation/`

Most scoring is scenario-agnostic, and `get_primary_channels()` being required
means the language and throughput metrics come free. Add a metric here only for a
domain signal that reduces to neither round success nor language phenomena, and
see [Creating a metric](creating-a-metric.md) before you do: a generic metric
reading a hook is preferred, and every scoring concept the platform has ended up
expressible that way.

### `run_detail_extension.py`

For per-round ground truth, judge metadata keyed by tool `call_id`, or custom SSE
events on the run-detail API. The platform discovers the file at startup; the
contract is
[scenario_extension.py](../src/glossogen/server/runs/scenario_extension.py) and
the canonical example
[veyru/run_detail_extension.py](../src/glossogen/scenarios/veyru/run_detail_extension.py).
Declare an extras model with a `Literal` scenario name, a
`ScenarioRunDetailExtension` subclass naming it, and a `build_extras` that walks
the events. Then regenerate the frontend types so the discriminated union picks
up your variant:

```bash
make gen-api-types
```

### Frontend plug-in

For a custom round-detail panel, tool-verdict rendering, live-judge wiring or
timeline markers, ship a `ScenarioPlugin` at
`frontend/src/features/runs/<your_scenario>/plugin.tsx` and register it in
[scenario-registry.ts](../frontend/src/features/runs/scenario-registry.ts). The
contract is
[scenario-plugin.ts](../frontend/src/features/runs/scenario-plugin.ts), the
canonical example
[veyru/plugin.tsx](../frontend/src/features/runs/veyru/plugin.tsx), and every
slot is optional. Plug-ins are compiled into the bundle, so this surface exists
only for a scenario living in this repo; an unknown name resolves to the default
plug-in rather than failing.

## In this repo, or in your own package

**In this repo**: the package lives at `src/glossogen/scenarios/<name>/` and
registration is one line in
[scenario_registry.py](../src/glossogen/scenario_registry.py). That is the only
file outside your package you touch.

**In your own package**: registration is the entry point the generator already
declared. The key is the name callers pass to `glossogen run` and the API, the
value the module and class:

```toml
[project.entry-points."glossogen.scenarios.v1"]
reactor_purge = "my_scenarios.reactor_purge.scenario:ReactorPurgeScenario"
```

What differs from an in-repo scenario:

- **A name a built-in already holds stays with the built-in**, and the collision
  is logged: a run's config records only the scenario name, so a redefinition
  would make old runs irreproducible.
- **The `v1` in the group is the contract version.** A platform speaking a
  different version does not read your group, and says so by name.
  [scenario_api.py](../src/glossogen/scenario_api.py) explains why the version
  lives in the group.
- **Presets and prompts ship in your package**, which is what the `package-data`
  entry covers.
- **Discovery still applies**: empty `__init__.py`, `events.py` on `event_base`
  only. A broken events module in an installed package is logged and skipped
  rather than taking the platform down.
- **No frontend plug-in**; the platform UI renders everything it derives from
  your knobs schema and event log.
- **Configuration is read from your project**: the `.env` sits beside your
  `pyproject.toml`. See [Configuring it](installation.md#configuring-it).

Launching is the same either way: `glossogen run`, or the MCP `start_run` tool.

### Viewing your runs in the web UI

One command, from the environment your package is installed in:

```bash
glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000
```

API on 8000, UI on <http://localhost:3000>, your scenario in the run list, no
checkout involved. The environment decides which scenarios resolve, which is why
the server runs from yours: a server started from a glossogen checkout knows only
the scenarios that checkout ships, so your run would list under a name it cannot
build.

`--ui-port` needs Docker, because the UI is a Node application rather than part
of the Python package: the flag runs the published frontend image, wires
`API_URL` to your server, adds the UI's origin to CORS, and removes the container
when the server stops. It runs the latest published UI; `--ui-image` with a
version tag pins one, which an older server needs, since a current UI calls
endpoints it may not serve.

Omit `--ui-port` for the API alone. Running the UI from a checkout instead
(`API_URL=http://localhost:8000 npm run dev` in `frontend/`) makes two settings
yours to keep in step: `API_URL` is read at request time, and `ALLOWED_ORIGINS`
defaults to `http://localhost:3000`, so serving the UI from another port without
adding it renders pages whose API calls are refused by CORS, which shows up as an
empty run list rather than as an error.

## Check it, then smoke it

`glossogen validate <dir>` while editing, `glossogen validate <name>` once
installed. It builds every preset, checks the contract and the package, reports
every failure rather than the first, and needs no API key, so it belongs in your
CI. [Testing a scenario](testing-a-scenario.md) has the full check table, and the
scripted round loop (`run_rounds`) that exercises what `validate` cannot: the
world's state machine, the postmortem phase, and the round verdict, with no LLM
and no waiting.

Then one short real run, end to end:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run your_scenario \
  --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  round_count=3 \
  > ./runs/your_scenario_smoke.log 2>&1 &
```

Pass criteria:

1. The log ends with `Simulation complete. Run directory: runs/your_scenario/<timestamp>`.
2. The JSONL holds your `<Scenario>CaseStarted` event once per round and one
   `RoundResultRecorded` per round (per team per round when multi-team).
3. With a run-detail extension, the round-timeline modal shows your data under
   `make dev` + `make dev-frontend`.

Then evaluate it:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate your_scenario \
  --run-dir ./runs/your_scenario/<timestamp> \
  --metrics round_success,mean_chars_per_round,mean_chars_per_message \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

The report should hold one Measurement per metric with sensible `score` and
`per_round` values.

## Pre-flight checklist

- [ ] `glossogen validate <dir>` passes (or `<name>`, once installed).
- [ ] `team_declaration.py` is the only place agents, channels and rosters are
      named; `get_agents()` / `get_channels()` delegate to `team_structure`.
- [ ] Every role's `starts_as_member` is decided, not defaulted. A role that
      arrives mid-run is `False`.
- [ ] The world's `on_message` override calls up, and
      `round_budget_thresholds` is ordered most severe first.
- [ ] `postmortem_channel_ids` lists the debrief channels of every mode the
      scenario can run in, the default preset's and the rest.
- [ ] Every knobs field is required; preset values live in `knobs_default.json`,
      with `seed = 42` and the canonical judge.
- [ ] Prompts live in `prompts/*.jinja`, not in Python strings.
- [ ] `judge_round_result` returns at least one `RoundResult` per round, and
      `get_primary_channels()` returns one entry per independently metered
      channel (teams sharing a link get one pooled entry, not one each).
- [ ] With a run-detail extension: `make gen-api-types` re-run.
- [ ] `make lint` is clean; regenerate the vulture whitelist if Pydantic fields
      or auto-discovered classes get flagged.
- [ ] One end-to-end smoke run completes and `round_success` returns a non-empty
      per-round list.

## Common pitfalls

- **`ImportError` naming your scenario at platform startup.** Check that
  `__init__.py` is empty and `events.py` does not import
  `glossogen.models.event`.
- **A late-arriving agent saw the traffic it was meant to arrive after.** Check
  `starts_as_member` on that role; the run completes and only the experiment's
  meaning changed.
- **Vulture flags scenario classes as unused.** Pydantic fields and
  auto-discovered classes look unused; regenerate the whitelist.
- **Frontend types out of sync.** `frontend/src/types/api.gen.ts` is generated;
  CI fails on drift. Run `make gen-api-types` after any schema change.
- **Script placement.** One-offs importing your scenario live under the
  scenario's own `scripts/`; only cross-scenario tools live in the repo-root
  `scripts/`.

## Reference scenarios

| Scenario | Read it for |
|---|---|
| [container_yard_stacking](../src/glossogen/scenarios/container_yard_stacking/) | The cleanest layout to mirror: deterministic scoring with no judge anywhere, sequenced multi-call actions validated by the world |
| [warehouse_robot_recovery](../src/glossogen/scenarios/warehouse_robot_recovery/) | The simplest single-judged-action pattern, with a per-character budget |
| [satellite_contact_window](../src/glossogen/scenarios/satellite_contact_window/) | Sequenced command submission judged in one call against an authorization envelope |
| [veyru](../src/glossogen/scenarios/veyru/) | Every optional extension surface at once: run-detail extension, frontend plug-in, per-scenario scripts, probe wiring |
