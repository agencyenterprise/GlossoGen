# Creating a new scenario

This guide walks through adding a new scenario to glossogen end-to-end. By the end you'll have a registered scenario, a working smoke run, and (optionally) bespoke run-detail data on the API and bespoke UI on the frontend: every extension surface that exists today, all opt-in.

If you just want to copy an existing scenario as a starting point, [container_yard_stacking](../src/glossogen/scenarios/container_yard_stacking/) is the freshest 3-agent reference, and its file list and shape is what this guide aims at.

## What a scenario is

A scenario is one self-contained 3-agent (or 2-agent, or N-agent) coordination task. Each scenario owns:

- **A team declaration** — the roles, the comm topology, who can read/send what, stated as data the engine derives the run from.
- **Tools** — the MCP tools each agent has access to beyond the platform-default `read_notifications` / `read_channel` / `send_message`.
- **A world** — the live simulated environment that emits notifications, validates tool results, tracks state, and decides round success/failure. `RoundWorld` when it meters a per-round budget, plain `ScenarioWorld` when it meters nothing.
- **Knobs + a default preset** — the Pydantic-validated configuration the CLI and frontend expose.
- **Per-round injections** — the round-start text each agent receives, rendered from Jinja templates.
- **Optional metrics** — scenario-specific `Metric` subclasses on top of the generic ones (`perplexity`, `mean_chars_per_round`, etc.).
- **Optional run-detail extension** — surfaces scenario-specific data (per-round ground truth, judge metadata, custom SSE events) on the run-detail API.
- **Optional frontend plug-in** — a per-round detail panel, tool-verdict rendering, live-judge wiring, or timeline markers. In-repo scenarios only; these are compiled into the bundle.
- **Optional per-scenario scripts** — one-off runners and ontology builders that import the scenario directly.

The platform discovers events, run-detail extensions, and frontend plug-ins automatically. The only file you have to *register* in is [scenario_registry.py](../src/glossogen/scenario_registry.py).

## Package layout

```
src/glossogen/scenarios/<your_scenario>/
├── __init__.py                  # MUST stay empty (see "Why empty inits" below)
├── README.md                    # scenario-specific docs
├── ids.py                       # agent IDs, channel IDs, tool names, world markers
├── knobs.py                     # ScenarioKnobs Pydantic model extending BaseKnobs
├── knobs_default.json           # canonical preset (referenced by the CLI's --config)
├── events.py                    # scenario-specific EventBase subclasses (auto-discovered)
├── team_declaration.py          # the teams, roles and channels the run is derived from
├── world.py                     # RoundWorld subclass: state + on_message / on_message_async
├── scenario.py                  # SimulationScenario subclass: tools, injections, scoring
├── prompts/
│   ├── description.jinja
│   ├── <role>_system.jinja      # one per agent role
│   ├── <role>_injection.jinja   # one per agent role, rendered round-start
│   ├── postmortem_injection.jinja
│   └── <judge>.jinja            # one per LLM judge
├── evaluation/                  # optional
│   ├── __init__.py
│   └── <metric>_metric.py       # Metric subclasses scoring the scenario's primary signal
├── run_detail_extension.py      # optional; auto-discovered by the API
├── scripts/                     # optional; per-scenario one-offs
```

Frontend plug-in (optional) lives separately at `frontend/src/features/runs/<your_scenario>/plugin.tsx`.

### What each file is responsible for

Nothing enforces this split; it is convention.

| file | owns | does not belong here |
|---|---|---|
| `ids.py` | Every literal string the scenario uses more than once: agent and channel ids, role names, tool names, and the marker strings the world writes into notifications. | Anything with behaviour. If it needs an `if`, it belongs elsewhere. |
| `knobs.py` | The fields a run can vary that are specific to this scenario, plus the validators that reject impossible combinations. A `seed` belongs here: `BaseKnobs` has none, and every scenario in the tree declares its own. | Anything `BaseKnobs` already declares: round count, phase durations, postmortem switches, channel noise, per-agent model overrides. Redeclaring one shadows the platform's. |
| `knobs_default.json` | The canonical preset, and the values a reader should assume when a doc says "by default". | Experiment-specific presets. Those are separate `knobs_*.json` files. |
| `events.py` | The scenario's own event types, which the platform discovers and the FE and metrics read. | Imports from `glossogen.models.event`. Import `event_base` only, or discovery deadlocks (see below). |
| `team_declaration.py` | The teams this configuration runs, and for each one its task channel, its debrief policy, and the roles that staff it. See "Declaring the structure" below. | Prompt text, and anything that varies within a round. A declaration is read once at construction. |
| `world.py` | State that changes *during* a round, and the reactions to it: what a case currently looks like, whether the round has been resolved, and the notifications agents receive as it progresses. | Anything the scenario only reads at round boundaries. Prompts are `scenario.py`'s, structure is `team_declaration.py`'s. |
| `scenario.py` | The contract with the platform: what each role is told at round start, which tools they may call, and how a finished round is scored. Structure it derives from `team_declaration.py` rather than restating. | Mutable per-round state, which belongs in `world.py`, and prose, which belongs in `prompts/`. Also which agents and channels exist, which the declaration states. |
| `prompts/` | Every word an agent or a judge reads. | Nothing. No prompt text is written inline in Python. |
| `evaluation/` | Metrics that score something the generic ones cannot express. | A metric the platform already has. Check the generic list first; most scenarios need nothing here. |
| `run_detail_extension.py` | Scenario-specific data surfaced on the run-detail API, for the FE to render. | Anything the FE does not read. |
| `scripts/` | One-offs that import this scenario directly. | Anything cross-scenario, which lives in the repo-root `scripts/`. |

### Declaring the structure

A scenario states its shape as data and lets the engine derive the runtime from
it. [`team_declaration.py`](../src/glossogen/engine/team_declaration.py) defines
the types; [`team_structure.py`](../src/glossogen/engine/team_structure.py) turns
them into what the platform asks for.

Your scenario's own `team_declaration.py` exports one function taking knobs and
returning `tuple[TeamSpec, ...]`, one entry per isolated group of agents. A
single-team scenario returns one. Two competing teams return two, and the engine
meters, judges and reports each independently.

Each `TeamSpec` carries:

- **`task`** — a `TaskChannel`, the channel the team works on. Being the task
  channel is what makes it metered against the round budget, corrupted when
  channel noise is on, and shut while the debrief phase is open. Those follow
  from the declaration, so a scenario cannot wire one to the wrong channel or
  forget one of them.
- **`debrief`** — either `Debrief(...)` or `NoDebrief()`. A team that holds no
  post-round discussion says so, rather than leaving a field unset.
- **`roles`** — a `RoleSpec` per agent: its id, role name, system-prompt
  template, tool names, and two booleans covered below.

No field has a default, so omitting one is a type error rather than a silent
behaviour.

`tool_names` is the per-agent authorization list the MCP guard enforces, and it is
not additive on top of a default. A role that needs to talk lists `send_message`;
one that needs to read the backlog lists `read_channel`. Leave it empty and the
agent connects, receives its injection, and can do nothing with it. The names
available are the platform's (`read_notifications`, `read_channel`, `send_message`,
`list_channels`, `get_channel_members`) plus whatever `get_mcp_tools()` returns; a
conformance test rejects a name no tool answers to.

#### `starts_as_member` is not `joins_debrief`

These look interchangeable and are not, and conflating them causes a bug that
does not crash.

`joins_debrief` says whether a role reaches the team's debrief channel at all. A
team can hold a discussion that not every member attends.

`starts_as_member` says whether the role is in a channel's roster on round one.
Which channels a role *reaches* is fixed at construction and shapes its system
prompt; whether it is *in the room yet* is separate. A role that arrives mid-run
is configured for its channel from the start and added to the roster later by an
intervention. Collapse the two and a not-yet-arrived agent sits in the channel
from round one, reading the traffic it was meant to arrive after. It still runs
and still logs, and the only symptom is an experiment that answered a different
question.

Both readings are legitimate, so pick deliberately.
[veyru](../src/glossogen/scenarios/veyru/team_declaration.py) keeps its intern
out of the roster until its join round fires, because the newcomer is the
subject of the measurement.
[container_yard_stacking](../src/glossogen/scenarios/container_yard_stacking/team_declaration.py)
puts its intern on the link from round one, and says so in a comment where a
reader would otherwise assume it followed veyru.

#### When a declaration does not fit

The engine's vocabulary is teams. A scenario with no teams should not invent one:
[prisoners_dilemma](../src/glossogen/scenarios/prisoners_dilemma/scenario.py) is
two opponents sharing one channel with no per-team budget, so it builds its two
agents directly in `scenario.py` and has no `team_declaration.py`. Every other
scenario declares.

### What the engine provides

A scenario that meters a per-round budget subclasses `RoundWorld` rather than
`ScenarioWorld`, which provides:

- **Per-team character metering.** `RoundWorld.on_message` charges each message
  to the team owning the channel it landed on, counting task channels only. When
  several teams share one task channel no single team owns it, and the sender's
  team pays for its own words instead. Override `on_message`, call up, and read
  `characters_used` to apply your own budget rule. Forgetting the call up
  accumulates nothing, so it fails loudly.
- **Round-budget announcements.** `claim_round_budget_threshold` answers whether
  an announcement is still owed this round and records that it was made.
  Declaring the thresholds most severe first is what makes the terminal one
  suppress the milder ones beneath it.
- **Round history.** `RoundOutcomeLog` stores whatever record you build for a
  finished round, once per round per team, so a debrief injection and the next
  round's boundary can both ask for it and agree.

`begin_round` clears the counters and the announcements together, and is called
at the round boundary.

### Why empty inits

The scenario package's `__init__.py` MUST stay empty. The platform's event-discovery walker (`glossogen.models.event._discover_scenario_event_types`) imports `glossogen.scenarios.<name>.events` directly via `pkgutil`. If `__init__.py` re-exported anything from `scenario.py`, importing the events module would cascade into `scenario.py`, which imports back from `glossogen.models.event` — and that module is mid-import when discovery runs. Empty inits break that cycle.

For the same reason, `events.py` must import only from [`glossogen.models.event_base`](../src/glossogen/models/event_base.py) (which defines `EventBase` and `TokenUsage`), never from `glossogen.models.event`.

## Step-by-step

### 1. Create the package skeleton

```bash
mkdir -p src/glossogen/scenarios/<your_scenario>/prompts
touch src/glossogen/scenarios/<your_scenario>/__init__.py
```

Leave `__init__.py` empty.

### 2. Write `ids.py`

Centralize every literal string the scenario uses: agent IDs, channel IDs, tool names, world-event marker strings, and per-agent tool lists. Keeps the rest of the package free of magic strings.

See [container_yard_stacking/ids.py](../src/glossogen/scenarios/container_yard_stacking/ids.py) for a worked example. Typical contents:

```python
YARD_OPERATOR_ID = "yard_operator"
LOGISTICS_PLANNER_ID = "logistics_planner"
CRANE_OPERATOR_ID = "crane_operator"

COORDINATION_CHANNEL_ID = "coordination"
POSTMORTEM_CHANNEL_ID = "postmortem"

MOVE_TRUCK_TOOL = "move_truck_to_crane_spot"
CRANE_MOVE_TOOL = "crane_move"
SEND_MESSAGE_TOOL = "send_message"

# World marker strings. A fixed prefix on tool result strings and on
# WorldEventDelivered.text, so an agent reading one can tell the outcome
# classes apart. Round scoring does not read them: round_success reads the
# RoundResultRecorded events the game clock writes from judge_round_result.
TRUCK_ARRIVED_MARKER = "[truck_arrived]"
ROUND_SUCCESS_MARKER = "[round_success]"
ROUND_FAILED_MARKER = "[round_failed]"
```

### 3. Write `knobs.py`

Define a `ScenarioKnobs` Pydantic model that extends `BaseKnobs`. Every field MUST be required (no defaults, per the project's "no default parameter values" rule); presets supply values via `knobs_default.json`. `BaseKnobs` already provides `round_count`, `max_round_duration_seconds`, `model_overrides`, `scheduled_events`, and the other shared fields, so declare only your scenario-specific knobs here.

```python
from glossogen.scenarios.base_knobs import BaseKnobs
from pydantic import Field, model_validator

class ContainerYardStackingKnobs(BaseKnobs):
    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    time_budget_seconds: int
    seed: int
    hard_case_fraction: float = Field(ge=0.0, le=1.0)
    channel_noise_level: float = Field(ge=0.0, le=1.0)
```

### 4. Write `knobs_default.json`

The canonical preset. Every field `BaseKnobs` declares without a default has to be
present or validation rejects the preset: `round_count`, `max_round_duration_seconds`,
and `model_overrides` (`{}` when there are none). Then always use:
- `seed=42` (the canonical seed; cross-run comparability)
- `judge_model="claude-haiku-4-5-20251001"` + `judge_provider="anthropic"` (the canonical
  judge), for a scenario that has one. Those are scenario knobs rather than platform
  ones, so a scenario scoring its rounds deterministically declares neither.

```json
{
  "judge_model": "claude-haiku-4-5-20251001",
  "judge_provider": "anthropic",
  "round_count": 15,
  "time_budget_seconds": 200,
  "seed": 42,
  "...": "..."
}
```

### 5. Write `events.py`

Declare each scenario-specific event class as an `EventBase` subclass with a unique `event_type` discriminator. The platform's discovered-union JSONL parser picks them up automatically; you don't edit `glossogen/models/event.py`.

```python
from typing import Literal
from pydantic import BaseModel
from glossogen.models.event_base import EventBase


class YardCaseStarted(EventBase):
    event_type: Literal["yard_case_started"] = "yard_case_started"
    case_number: int
    incoming_container: str
    target_position: str
    # ...
```

**Critical**: import only from `glossogen.models.event_base`, never from `glossogen.models.event`.

### 6. Write `team_declaration.py`

Export one function taking your knobs and returning `tuple[TeamSpec, ...]`. See "Declaring the structure" above for what goes in a spec and for the `starts_as_member` trap.
[drive_module_repair](../src/glossogen/scenarios/drive_module_repair/team_declaration.py) is a minimal worked example (one team, no layout branching); [veyru](../src/glossogen/scenarios/veyru/team_declaration.py) is the largest (two layouts, an optional late-arriving role, a debrief that a knob can switch off).

Single-team scenarios conventionally define `TEAM_ID = "solo"` here and import it wherever the world needs to name its one team, so the id is stated once.

Write this before the world, which takes the specs as a constructor argument, and before `scenario.py`, which derives its agents and channels from them.

### 7. Write `world.py`

Subclass `RoundWorld` (defined in [round_world.py](../src/glossogen/engine/round_world.py)) if the scenario meters a per-round communication budget, which almost all do; subclass `ScenarioWorld` (defined in [scenario_world.py](../src/glossogen/runtime/scenario_world.py)) directly only if it meters nothing. See "What the engine provides" above for what `RoundWorld` hands you. The world is the live simulated environment. It mutates internal state synchronously in `on_message`, reacts asynchronously (pushing notifications to agents via `context.send_update_to_channel(...)`) in `on_message_async`, and tracks the state the scenario reads to decide when a round succeeds or fails. The base class provides the `run` event loop; you override the message hooks, not `run`.

The shape to mimic is [`WarehouseWorld`](../src/glossogen/scenarios/warehouse_robot_recovery/world.py) (single-tool scenarios) or [`ContainerYardWorld`](../src/glossogen/scenarios/container_yard_stacking/world.py) (multi-tool scenarios with sequenced action state).

`RoundWorld` takes the declared specs plus the names of the budget announcements this scenario makes, most severe first:

```python
class SpillwayWorld(RoundWorld):
    def __init__(
        self,
        cases: list[SpillwayCase],
        team_specs: tuple[TeamSpec, ...],
        postmortem_channel_ids: frozenset[str],
        postmortem_globally_disabled: bool,
    ) -> None:
        super().__init__(
            team_specs=team_specs,
            round_budget_thresholds=(THRESHOLD_BUDGET_EXCEEDED, THRESHOLD_CRITICAL),
            postmortem_channel_ids=postmortem_channel_ids,
            postmortem_globally_disabled=postmortem_globally_disabled,
        )
```

The order of `round_budget_thresholds` is load-bearing: claiming one claims every milder threshold after it, which is what stops a team being told its budget is running low just after being told it is gone. Take the specs and the channel ids as arguments rather than importing the ids directly, so the world and the declaration cannot disagree about which channels exist.

The world is also the place where:
- **The budget rule** lives: what the budget means, and what happens when it is crossed. The counting itself is not yours. Override `on_message`, call up so the engine accumulates, then read `characters_used(team_id=...)` and decide. Emit the `BUDGET_EXCEEDED_MARKER` notification through `claim_round_budget_threshold` so it fires once per round.
- **Postmortem channel logic** lives (postmortem messages do NOT cost budget; postmortem can be globally disabled mid-run).
- **Markers** are emitted at the end of each round — `ROUND_SUCCESS_MARKER` or `ROUND_FAILED_MARKER` — so the `round_success` metric can detect outcomes deterministically from the event log.

### 8. Write `scenario.py`

The `SimulationScenario` subclass is the entry point the registry hands to the CLI, the MCP `start_run` tool, and the run-detail UI. Required classmethods and methods are spelled out in [scenario_protocol.py](../src/glossogen/scenario_protocol.py). The key ones:

- `name()` → the registry key (string).
- `scenario_description()` → a short human-readable description.
- `postmortem_channel_ids` → a `ClassVar[frozenset[str]]` naming every channel that carries postmortem traffic. Declare it if the scenario has a debrief at all. It is what the replaced-agent history filter blocks, and what the world reports as globally disabled once a `set_postmortem` event closes the debrief. Both outlive the current configuration, so it must list every mode the scenario can run in, not just the debriefs the current knobs declare. A two-layout scenario names the solo channel *and* both per-team ones. Pass it to the world as `type(self).postmortem_channel_ids` rather than re-importing the ids.
- `knobs_model()` → classmethod returning your `<YourKnobs>` class. The base derives `knobs_json_schema()` from it — you no longer write the schema accessor.
- `get_knobs()` → return `self._knobs`. The base derives `get_round_count()`, `get_max_round_duration_seconds()`, and `get_scenario_config()` from it — you no longer write those getters.
- `create_from_config(config)` → classmethod factory that validates the dict against `<YourKnobs>` and constructs the scenario.
- `get_agent_roles(knobs)` → classmethod returning `(agent_id, role_name)` pairs used for agent-model override validation in CLI run-config preflight. Receives a possibly-partial `dict | None`; read role-determining flags with `self.resolve_bool_knob(knobs=knobs, field_name=...)`.
- `get_agents()`, `get_channels()` → derive both from your declared specs: `team_structure.build_agent_configs(teams=..., render_system_prompt=..., ...)` and `team_structure.channels(teams=...)`. Each is a delegation, not a hand-written list. You supply a `render_system_prompt(role, channels)` callback, because what a role is told is the scenario's subject matter while the wiring around it is the engine's. `team_structure.agent_display_names(...)` and `channel_display_names(...)` cover the display-name maps.
- `get_world()`, `get_mcp_tools()` → construct the world (passing it the same specs) and return one `ScenarioMcpTool` per scenario tool.
- `get_injection(round_number, agent_id)` → renders the per-round Jinja injection for an agent, or returns `None` for an agent with nothing to say this round. The round's case and the previous outcome come from your own world, not from arguments.
- `get_postmortem_injection(round_number, agent_id)` → optional postmortem-phase injection, same shape.
- `on_round_advanced(round_number)` → resolve the previous round and load the next case. Emit your `<Scenario>CaseStarted` event here so metrics can read per-round ground truth. The event logger is reached through the runtime handle, not passed in: `await self.runtime.event_logger.log(event=...)`.
- `on_round_ended(round_number, trigger)` → settle round-end state. `trigger` is why the round ended, including your own `get_early_round_end_trigger()` string.
- `validate_outgoing_message(...)`, `transform_outgoing_message(...)` → enforce / mutate messages (budget enforcement, noise injection).
- `get_primary_channels()` → **required** — return the `PrimaryChannel` list telling generic metrics (perplexity, mean-chars-per-round, mean-chars-per-message, language judges) which channel(s) to score. One entry per independently metered channel, which is not the same as one per team: two teams on their own links give two entries carrying their `team_id`, and the metrics report `perplexity_team_a` / `_team_b`. Two teams sharing one link give a single entry with `team_id=None`, pooling both under the base metric names, because there is one conversation to score. [spot_the_difference](../src/glossogen/scenarios/spot_the_difference/scenario.py) does both, switched on its `shared_link` knob. Return `[]` only if the scenario has no channel worth scoring.
- `get_early_round_end_trigger()` → optional; returns a trigger string when the round should end early (e.g. once a `target_placed` flag and `executed_moves` count match the expected sequence).
- `judge_round_result(round_number, trigger)` → **required** — return a list of `RoundResult(success, team_id, reason)`. The game clock writes one `RoundResultRecorded` event per element; the platform `round_success` metric reads these directly and emits one Measurement per `team_id` (single-team scenarios pass `team_id=None` and get one Measurement named `round_success`). Return `[]` only if the scenario genuinely has no per-round success criterion. Despite the name this does not imply an LLM judge — [prisoners_dilemma](../src/glossogen/scenarios/prisoners_dilemma/scenario.py) resolves rounds deterministically from its payoff matrix with no LLM anywhere, while veyru calls one. Judge however the task demands.
- `restore_state_from_events(events)` → optional. Called after a fork/resume rewind has been built and before the runtime starts. Walk the event list and seed any per-round outcomes you need so the first post-resume injection renders accurate "previous result" context (most scenarios need this only if their injection templates surface prior-round state).

For scenarios with custom tools (anything beyond `send_message`), `get_mcp_tools()` returns one [`ScenarioMcpTool`](../src/glossogen/runtime/scenario_mcp_tool.py) per tool. That is where you wire up freetext-argument LLM judges, world state mutations, and the marker strings the tool result returns.

### Optional platform hooks (post-simulation analysis)

These are opt-in: implement them only if you want the corresponding platform metric to run on your scenario. Returning `None` / `[]` (the default) makes the metric skip with no Measurement.

- `build_communication_rounds(events) -> list[CommunicationRoundView]` → opt the scenario into the `communication_open_coding` + `communication_feature_presence` pipeline. Each view joins one round's primary-channel messages with a scenario-rendered ground-truth block. Returning `[]` (default) skips both metrics.
- `detect_protocol_boundary_window(events, agent_configs) -> ProtocolBoundaryWindow | None` → drives `protocol_learned_after_swap`. The default returns the first `AgentSwappedMidRun` boundary (scheduled in-run swaps). Override to detect scenario-specific boundaries first (intern takeover, two-team observer swap) and fall back to `super().detect_protocol_boundary_window(...)` for scheduled swaps.
- `get_protocol_probe_config() -> ProtocolProbeConfig | None` → opts into the four-metric `protocol_probe` family. Returns a NamedTuple of (`questions_path`, `prompts_dir`, `role_groups`, `role_templates`). Ship the question bank as `<scenario>/protocol_probe_questions.json` and probe-prompt templates under `<scenario>/prompts/`. See [veyru/scenario.py](../src/glossogen/scenarios/veyru/scenario.py) for the canonical wiring and [veyru/scripts/build_probe_questions.py](../src/glossogen/scenarios/veyru/scripts/build_probe_questions.py) for a generator pattern.
- `get_judge_models(knobs) -> tuple[ModelConsumer, ...]` → the models the scenario
  calls itself, beyond what its agents call. A launch refuses to start when the
  environment cannot reach one of them, which is worth having because a judge is
  built on first use: a run whose agents authenticate starts, spends a round, and
  fails inside the call that scores it. The default reports the
  `judge_model` / `judge_provider` pair, the convention every scenario here
  follows, so a scenario naming those knobs declares nothing. Override it when
  your judge is conditional, so a configuration that calls no judge is not asked
  for a credential it will not spend, or when you call more than one model of
  your own, or name the knobs something else. A scenario that scores its rounds
  without an LLM declares neither knob and inherits the empty answer.
- `get_replace_agent_blocked_tool_call_channels() -> frozenset[str]` → channel IDs whose `send_message` / `read_channel` calls should be stripped from a replaced agent's reconstructed history, so a newcomer cannot read protocol-defining content out of its predecessor's tool returns. Defaults to `postmortem_channel_ids`, so declaring that ClassVar is usually all you need; override only to block something else as well.

### 9. Write `prompts/`

Every prompt is a Jinja2 template, never a hardcoded string in Python. Required:

- `description.jinja` — `scenario.description()` reads it.
- `<role>_system.jinja` — one per agent. Receives `channels`, `postmortem_enabled`, scenario knobs.
- `<role>_injection.jinja` — one per agent. Rendered at each round start. Receives `round_number`, `current_case`, `previous_outcome`, `knobs`.
- `postmortem_injection.jinja` — if `postmortem_enabled` can be true, render the postmortem-phase injection here.

For scenarios with LLM judges, one `<judge_name>.jinja` per judge. These are the system prompts handed to the judge's `generate_structured(...)` call. Judges live in a separate `<scenario>_judge.py` module and pull their templates via `TemplateRenderer`.

Rendering is strict. A name the template uses but the Python never passes raises `UndefinedError` rather than resolving to the empty string, so a misspelling fails at render instead of producing a prompt that reads fine but is missing a number or a whole `{% if %}` block. Pass every name the template mentions, including the ones you only use inside a condition. `None` is fine: it is a value you chose, so `{% if previous_outcome %}` still works on round one.

The conformance suite renders every scenario's description, system prompts, round-one injections, and postmortem injections against every preset in the tree, so a template that references a name nobody passes fails in CI rather than partway into a paid run.

### 10. (Optional) Write `evaluation/`

Most scoring is now scenario-agnostic. Because `get_primary_channels()` is required, you get every generic primary-channel metric for free:

| Metric | Hook the scenario must implement |
|---|---|
| `perplexity`, `mean_chars_per_round`, `mean_chars_per_message`, `language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes` | `get_primary_channels()` |
| `round_ended_idle`, `round_ended_timeout`, `content_filter_refusal` | (nothing — read straight from `RoundEnded` / `AgentRunCycleFailed`) |
| `round_success` | `judge_round_result(round_number, trigger)` |
| `round_success_after_resume` | `judge_round_result(...)` + the run was launched via replace-agent / cross-run / scheduled swap / resume-at-round |
| `protocol_learned_after_swap` | `build_communication_rounds(events)` + `detect_protocol_boundary_window(...)` |
| `communication_open_coding`, `communication_feature_presence` | `build_communication_rounds(events)` |
| `protocol_probe` family | `get_protocol_probe_config()` |

Add a scenario-specific metric under `evaluation/` only when the platform doesn't already cover what you want to measure (a domain-specific signal that doesn't reduce to round-success or to language phenomena on the primary channel). If you do, `evaluation/__init__.py` should export the metric class so the scenario can register it in its metric registry.

### 11. (Optional) Add a run-detail extension

If you want per-round case ground truth, judge metadata keyed by tool `call_id`, or custom SSE events to appear on the run-detail API (and thence on the frontend), add `src/glossogen/scenarios/<your_scenario>/run_detail_extension.py`. The platform auto-discovers it at startup.

The full contract is in [scenario_extension.py](../src/glossogen/server/runs/scenario_extension.py); the canonical example is [veyru/run_detail_extension.py](../src/glossogen/scenarios/veyru/run_detail_extension.py).

Minimal shape:

```python
from typing import ClassVar, Literal
from pydantic import BaseModel
from glossogen.models.event import SimulationEvent
from glossogen.server.runs.run_detail_types import AgentDetail, ChannelMessage
from glossogen.server.runs.scenario_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)


class YourRunExtras(ScenarioRunExtrasBase):
    scenario_name: Literal["your_scenario"] = "your_scenario"
    cases: list[YourCaseSummary]              # define this DTO in the same file


class YourSSEJudgedEvent(BaseModel):
    event_type: Literal["your_judged_event"]
    # ...


class YourRunDetailExtension(ScenarioRunDetailExtension):
    scenario_name: ClassVar[str] = "your_scenario"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = YourRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = (YourSSEJudgedEvent,)

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> YourRunExtras:
        # Walk events, materialize the per-round summaries.
        ...
```

After adding the file, regenerate the frontend types so the discriminated union picks up your variant:

```bash
make gen-api-types
```

`RunDetailResponse.scenario_extras` will now include `YourRunExtras` as one of the union arms, fully typed end-to-end.

### 12. (Optional) Add a frontend plug-in

If you want a custom panel inside the round-timeline modal, bespoke rendering for a tool call's verdict, live-judge SSE wiring, or round-anchored timeline markers, ship a `ScenarioPlugin` at `frontend/src/features/runs/<your_scenario>/plugin.tsx` and register it in [scenario-registry.ts](../frontend/src/features/runs/scenario-registry.ts):

```ts
import { yourPlugin } from "./your_scenario/plugin";

const SCENARIO_PLUGINS: Record<string, ScenarioPlugin> = {
  [veyruPlugin.scenarioName]: veyruPlugin,
  [yourPlugin.scenarioName]: yourPlugin,
};
```

The plug-in contract is in [scenario-plugin.ts](../frontend/src/features/runs/scenario-plugin.ts). The Veyru plug-in at [veyru/plugin.tsx](../frontend/src/features/runs/veyru/plugin.tsx) is the canonical example. Each slot is optional: return `null` / `{}` to fall through to the platform defaults.

Frontend plug-ins are compiled into the bundle, so this step is available only to a scenario living in this repo. A scenario installed from elsewhere renders with the platform's own UI, which is why the registry resolves an unknown name to `DEFAULT_SCENARIO_PLUGIN` rather than failing.

### 13. Register the scenario

A scenario in this repo adds one line to [src/glossogen/scenario_registry.py](../src/glossogen/scenario_registry.py):

```python
from glossogen.scenarios.your_scenario.scenario import YourScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    ...,
    "your_scenario": YourScenario,
}
```

This is the only file outside your scenario package you have to touch. (Event types, run-detail extras, SSE events, and frontend plug-ins are all auto-discovered.)

A scenario in its own distribution declares an entry point instead; see "Shipping a scenario in your own package" below.

## Shipping a scenario in your own package

A scenario does not have to live in this repo. Install glossogen as a dependency
(see [As a dependency](installation.md#as-a-dependency) for the install line, since
glossogen is not on PyPI) and generate the package:

```bash
glossogen new-scenario reactor_purge --target-dir .
cd reactor-purge
pip install -e ".[testing]"
```

What you get is a scenario that already runs: two agents relay a code word over a
metered link, `glossogen validate reactor_purge` passes, `pytest` passes,
and `glossogen run` completes. Editing one thing at a time and watching what
breaks is a faster way through this contract than assembling it from the sections
below. The generated README lists what to change in which order.

Two details in the generated `pyproject.toml` are worth knowing about, because
both fail long after the mistake:

- `[tool.setuptools.package-data]`. Without it only `.py` files are packaged. An
  editable install still works, so the omission survives until someone else
  installs the wheel and it fails at the first template render.
- The entry-point key equals what `name()` returns. Declare them differently and
  runs land in `runs/<name()>/` while `glossogen run`, `evaluate` and the resume
  flows address the run by the name it was launched with, so none of them find
  it. `tests/test_reactor_purge.py` checks this with
  `assert_scenario_is_registered`, which is the one thing validating by name cannot
  report on.

The rest of this page is what the generator wrote, and why. To lay a package out
by hand instead, declare it in your own `pyproject.toml`:

```toml
[project]
name = "my-scenarios"
dependencies = ["glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"]

[project.entry-points."glossogen.scenarios.v1"]
reactor_purge = "my_scenarios.reactor_purge.scenario:ReactorPurgeScenario"

[tool.setuptools.package-data]
my_scenarios = ["**/*.jinja", "**/*.json"]
```

Then `pip install -e .` (or `uv pip install -e .`) in your package.

The key is the scenario name callers pass to `--config`, `glossogen run`, and the
API; the value names the module and class. With the package installed,
`glossogen run reactor_purge ...` works, and the scenario appears in
`GET /api/g/<slug>/scenarios` and the MCP `list_scenarios` tool alongside the
built-in ones.

What differs from an in-repo scenario:

- **Registration** is the entry point rather than a line in `SCENARIO_REGISTRY`.
  A name already taken by a built-in stays with the built-in, and the collision
  is logged: a run's config records only the scenario name, so allowing a
  redefinition would make old runs irreproducible.
- **The entry-point name must equal what `name()` returns.** By default `name()`
  is your package directory, so declaring
  `reactor_purge = "my_scenarios.reactor_purge.scenario:..."` already agrees.
  Declare it under a different name and the lookup fails with both names, rather
  than running: run directories are `runs/{name()}/`, while `glossogen run`,
  `evaluate` and the resume flows all address a run by the name it was launched
  with. A disagreement puts the run where none of them will find it, and nothing
  looks wrong at the time. Override `name()` if you want an identifier that
  differs from the folder, and make the entry point match it.
- **Presets and prompts** are read from your own package, so ship the
  `knobs_*.json` files and `prompts/*.jinja` inside it and make sure your build
  includes them. That is what the `package-data` entry above is for: a package
  that omits it installs the `.py` files only, then fails at the first render
  with a missing-template error. Every knob `BaseKnobs` declares is required, so
  a preset needs `round_count`, `max_round_duration_seconds`, and
  `model_overrides` at minimum.
- **Discovery still applies.** Your `events.py` and `run_detail_extension.py` are
  imported the same way, so the "Why empty inits" rule holds for your package
  too: `events.py` imports only `glossogen.models.event_base`, and your package
  `__init__.py` stays empty. A broken `events` module in an installed package is
  logged and skipped rather than taking the platform down, so check the log if
  your event types do not show up.
- **The contract version is the `v1` in the group name.** Write the group that
  matches the glossogen you developed against. A platform speaking a different
  version does not read your group, and says so by name rather than reporting your
  scenario as absent. [scenario_api.py](../src/glossogen/scenario_api.py) explains
  why the version lives in the group rather than on the class.
- **No frontend plug-in.** Those are compiled in, so your scenario gets the
  platform UI. Everything the platform derives from your knobs model and your
  event log still works.
- **Configuration is read from your project.** The `.env` carrying
  `ANTHROPIC_API_KEY` belongs beside your `pyproject.toml`; commands read the
  nearest one at or above the directory they run in. See
  [Configuring it](installation.md#configuring-it).

Launching is the same either way: `glossogen run`, or the MCP `start_run` tool.
The REST API lists scenarios and serves their presets but does not start runs.

### Viewing your runs in the web UI

One command, from the environment your package is installed in:

```bash
glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000
```

That serves the API on 8000 and opens the web UI on <http://localhost:3000>,
with your scenario in the run list. No checkout of this repository is involved.

The environment decides which scenarios resolve, which is why the server runs
from yours. A server started from a glossogen checkout knows only the scenarios
that checkout ships, so your run is listed under a name it cannot build and the
run-detail page fails on it.

`--ui-port` needs Docker, because the UI is a Node application rather than part
of the Python package: the flag runs the published frontend image, wires
`API_URL` to the port the server is on, adds the UI's origin to the backend's
CORS list, and removes the container when the server stops. It runs the latest
published UI, which is a viewer of the API rather than a version-locked half of
it; `--ui-image` with a version tag pins one, which an older server needs, since
a current UI calls endpoints it may not serve. The images cover amd64 and arm64,
and for one published before that was true the flag retries under emulation
rather than failing.

Omit `--ui-port` for the API alone. To run the UI yourself instead, from a
checkout:

```bash
cd frontend && npm ci
API_URL=http://localhost:8000 npm run dev
```

Doing it that way makes two settings yours to keep in step. `API_URL` is the URL
your browser reaches the backend on, read at request time rather than compiled
in. And `ALLOWED_ORIGINS` defaults to `http://localhost:3000`: serve the UI from
another port without adding it and the pages still render while the browser's
API calls are refused by CORS, which shows up as an empty run list rather than
as an error.

## Check it before you run it

```bash
glossogen validate ./your-scenario   # a directory: no install needed
glossogen validate your_scenario     # an installed scenario, by name
```

Pass the directory while you are writing. It reads the scenario's declaration out
of your own `pyproject.toml`, so it needs no install and your loop is edit then
check rather than edit, reinstall, check. That form also checks the package itself,
where the failures stop meaning anything once it is installed: `package-data` that
omits your prompts, an entry-point group naming another contract version, a
non-empty package `__init__`, and a name a built-in already holds. See
[Testing a scenario](testing-a-scenario.md#the-contract-comes-first-and-it-is-a-command).

Pass a name once the package is installed, which is what CI does anyway.

Either way it builds the scenario from every preset it ships and checks what the
ABC cannot:
that agents only claim channels that exist, that `tool_names` name tools
something answers to, that `get_agent_roles` agrees with the agents `get_agents`
builds, that round-one and postmortem templates render, that the config
round-trips through its own dump, and that the channels your metrics read are
channels the run has. Each of those otherwise surfaces minutes into a paid run,
or as a metric that quietly scores an empty transcript.

It reports every failure rather than the first, and exits non-zero, so it works
as a CI step in whichever package ships the scenario:

```
FAIL your_scenario [knobs_default]: agents claim channels that exist — talker lists channels that do not exist: ['ghost']
FAIL your_scenario [knobs_default]: declared tools exist — talker is authorized for unknown tools: ['no_such_tool']
2 of 30 checks failed for your_scenario.
```

It needs no API key: provider credentials are hidden while each preset is built,
so a scenario that reaches for one at construction fails here rather than in
everyone else's environment.

## Smoke test

`validate` proves the scenario builds. It never starts the game clock, so
nothing there notices if the world's state machine, the postmortem phase or the
round verdict breaks. `glossogen.testing` runs the real loop with the LLM
replaced by a script, which costs no API call and no waiting:

```python
from pathlib import Path

import pytest

from glossogen.testing import assert_no_agent_crashed, assert_round_loop_completed, run_rounds


async def test_the_round_loop_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = await run_rounds(
        scenario_name="your_scenario",
        preset_name="knobs_default",
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert_round_loop_completed(result=result, round_count=2)
    assert_no_agent_crashed(result=result)
```

See [Testing a scenario](testing-a-scenario.md) for driving your own tools
through a script, and for the metric-side harness.

Then run a short simulation end-to-end:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run your_scenario \
  --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  round_count=3 \
  > ./runs/your_scenario_smoke.log 2>&1 &
```

Monitor per the CLAUDE.md sleep-30-tail pattern. Pass criteria:

1. The log finishes with `Simulation complete. Run directory: runs/your_scenario/<timestamp>`.
2. The JSONL contains your `<Scenario>CaseStarted` event once per round and one `RoundResultRecorded` event per round (or per team per round in multi-team scenarios).
3. If you added a run-detail extension, loading the run in `make dev` + `make dev-frontend` shows your scenario-specific data in the round-timeline modal.

Then evaluate:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate your_scenario \
  --run-dir ./runs/your_scenario/<timestamp> \
  --metrics round_success,mean_chars_per_round,mean_chars_per_message \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

The report should contain one Measurement per metric with sensible `score` and `per_round` values.

## Pre-flight checklist

Before opening a PR:

- [ ] `glossogen validate <dir>` passes (or `glossogen validate <name>`, once installed).
- [ ] `__init__.py` files (namespace + scenario) are empty. *(`validate` checks this.)*
- [ ] `events.py` imports only from `glossogen.models.event_base`. *(Checked.)*
- [ ] Each of your event types declares its own `event_type` literal, not one the platform or another of yours already uses. *(Checked.)*
- [ ] `team_declaration.py` is the only place agents, channels and rosters are named. `get_agents()` / `get_channels()` delegate to `team_structure`; neither builds a list by hand.
- [ ] Every role's `starts_as_member` says whether it is in the roster on round one, decided rather than defaulted. A role that arrives mid-run is `False`.
- [ ] The world subclasses `RoundWorld` if the scenario meters a per-round budget, and its `on_message` override calls up.
- [ ] `round_budget_thresholds` is ordered most severe first.
- [ ] `postmortem_channel_ids` lists the debrief channels of *every* mode the scenario can run in, not just the default preset's.
- [ ] Every knobs field is required (no defaults); preset values live in `knobs_default.json`.
- [ ] `judge_model = "claude-haiku-4-5-20251001"`, `judge_provider = "anthropic"`, `seed = 42` in the preset.
- [ ] Prompts live in `prompts/*.jinja`, not in Python string literals.
- [ ] `judge_round_result(round_number, trigger)` returns at least one `RoundResult` per round (single-team scenarios: one with `team_id=None`; multi-team: one per team). The game clock writes `RoundResultRecorded` events from these; the platform `round_success` metric reads them directly.
- [ ] `get_primary_channels()` (required) returns a non-empty `PrimaryChannel` list: one entry per independently metered channel, carrying a `team_id` only where a team meters that channel alone. Teams sharing a link get one pooled entry, not one each.
- [ ] If you added a run-detail extension, re-run `make gen-api-types` so `frontend/src/types/api.gen.ts` includes your `XxxRunExtras` variant.
- [ ] `make lint` is clean. Regenerate the vulture whitelist (`VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 60 --make-whitelist > vulture_whitelist.py`) if Pydantic fields or auto-discovered classes get flagged.
- [ ] At least one end-to-end smoke run completes and the `round_success` metric returns a non-empty per-round list.

## Common pitfalls

**Circular import on event discovery.** If you see `ImportError` mentioning your scenario at platform startup, check that (a) `__init__.py` is empty and (b) `events.py` doesn't import from `glossogen.models.event`.

**A late-arriving agent saw the traffic it was meant to arrive after.** The run completes, the logs look right, and the measurement answered a different question than the one you asked. Check `starts_as_member` on that role: it governs the round-one roster, not which channels the role reaches, and the two are easy to conflate. See "`starts_as_member` is not `joins_debrief`" above.

**Vulture flags scenario classes as unused.** Pydantic fields, auto-discovered extension classes, and metric classes can look unused. Regenerate the whitelist as shown above.

**Pyright stale cache during incremental edits.** Pyright sometimes caches old module symbols across edits. Restart the language server or run `make lint-server` directly to confirm whether errors are real.

**Frontend types out of sync.** The OpenAPI types in `frontend/src/types/api.gen.ts` are generated. After any backend schema change (e.g. adding a `ScenarioRunExtrasBase` subclass), run `make gen-api-types`. CI fails if the file drifts from the backend schema.

**Per-scenario script paths.** One-off scripts that import your scenario directly belong under `src/glossogen/scenarios/<your_scenario>/scripts/`, not the repo-root `scripts/` folder. Cross-scenario tools (the OpenAPI exporter, generic diagnostic tools) stay in `scripts/`.

## Reference scenarios

When in doubt, mirror an existing scenario:

- [container_yard_stacking](../src/glossogen/scenarios/container_yard_stacking/) — most recent 3-agent build; freetext tool args with LLM judges, multi-call sequenced actions, per-round changing geometry. Cleanest "follow this layout" template.
- [warehouse_robot_recovery](../src/glossogen/scenarios/warehouse_robot_recovery/) — 3-agent, single-tool recovery with per-character budget. Simplest "single judged action" pattern.
- [satellite_contact_window](../src/glossogen/scenarios/satellite_contact_window/) — 3-agent, sequenced command submission judged in one call against an authorization envelope.
- [veyru](../src/glossogen/scenarios/veyru/) — 2-agent baseline scenario; the most heavily extended scenario, including a run-detail extension, a frontend plug-in, per-scenario scripts, and many bespoke metrics. The canonical example for every optional extension surface.
