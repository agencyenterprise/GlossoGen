# Creating a new scenario

This guide walks through adding a new scenario to glossogen end-to-end. By the end you'll have a registered scenario, a working smoke run, and (optionally) bespoke run-detail data on the API and bespoke UI on the frontend — every extension surface that exists today, all opt-in.

If you just want to copy an existing scenario as a starting point, [container_yard_stacking](../src/glossogen/scenarios/container_yard_stacking/) is the freshest 3-agent reference — its file list and shape is what this guide aims at.

## What a scenario is

A scenario is one self-contained 3-agent (or 2-agent, or N-agent) coordination task. Each scenario owns:

- **Agents and channels** — the roles, the comm topology, who can read/send what.
- **Tools** — the MCP tools each agent has access to beyond the platform-default `read_notifications` / `read_channel` / `send_message`.
- **A `ScenarioWorld`** — the live simulated environment that emits notifications, validates tool results, tracks state, and decides round success/failure.
- **Knobs + a default preset** — the Pydantic-validated configuration the CLI and frontend expose.
- **Per-round injections** — the round-start text each agent receives, rendered from Jinja templates.
- **Optional metrics** — scenario-specific `Metric` subclasses on top of the generic ones (`perplexity`, `mean_chars_per_round`, etc.).
- **Optional run-detail extension** — surfaces scenario-specific data (per-round ground truth, judge metadata, custom SSE events) on the run-detail API.
- **Optional frontend plug-in** — a bespoke knobs form, per-round detail panel, or replace-agent default knobs.
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
├── world.py                     # ScenarioWorld subclass: state + on_message / on_message_async
├── scenario.py                  # SimulationScenario subclass: tools, channels, injections
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
└── analysis/                    # optional; scenario-specific Streamlit/notebook helpers
```

Frontend plug-in (optional) lives separately at `frontend/src/features/runs/<your_scenario>/plugin.tsx`.

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

Centralize every literal string the scenario uses — agent IDs, channel IDs, tool names, world-event marker strings, and per-agent tool lists. Keeps the rest of the package free of magic strings.

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

# World marker strings (must appear literally in tool result strings or
# WorldEventDelivered.text — used by the round_success metric to detect
# success vs. failure).
TRUCK_ARRIVED_MARKER = "[truck_arrived]"
ROUND_SUCCESS_MARKER = "[round_success]"
ROUND_FAILED_MARKER = "[round_failed]"
```

### 3. Write `knobs.py`

Define a `ScenarioKnobs` Pydantic model that extends `BaseKnobs`. Every field MUST be required (no defaults — per the project's "no default parameter values" rule); presets supply values via `knobs_default.json`. `BaseKnobs` already provides `round_count`, `max_round_duration_seconds`, `model_overrides`, `scheduled_events`, and the other shared fields — declare only your scenario-specific knobs here.

```python
from glossogen.knobs_base import BaseKnobs
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

The canonical preset. Always use:
- `seed=42` (the canonical seed; cross-run comparability)
- `judge_model="claude-haiku-4-5-20251001"` + `judge_provider="anthropic"` (the canonical judge)

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

### 6. Write `world.py`

Subclass `ScenarioWorld` (defined in [scenario_world.py](../src/glossogen/runtime/scenario_world.py)). The world is the live simulated environment — it mutates internal state synchronously in `on_message`, reacts asynchronously (pushing notifications to agents via `context.send_update_to_channel(...)`) in `on_message_async`, and tracks the state the scenario reads to decide when a round succeeds or fails. The base class provides the `run` event loop; you override the message hooks, not `run`.

The shape to mimic is [`WarehouseWorld`](../src/glossogen/scenarios/warehouse_robot_recovery/world.py) (single-tool scenarios) or [`ContainerYardWorld`](../src/glossogen/scenarios/container_yard_stacking/world.py) (multi-tool scenarios with sequenced action state).

The world is also the place where:
- **Per-character budget mechanics** live (subtract message length from a budget; emit `BUDGET_EXCEEDED_MARKER` notification when exhausted).
- **Postmortem channel logic** lives (postmortem messages do NOT cost budget; postmortem can be globally disabled mid-run).
- **Markers** are emitted at the end of each round — `ROUND_SUCCESS_MARKER` or `ROUND_FAILED_MARKER` — so the `round_success` metric can detect outcomes deterministically from the event log.

### 7. Write `scenario.py`

The `SimulationScenario` subclass — the entry point the registry hands to the CLI, MCP `start_run` tool, and run-detail UI. Required classmethods and methods are spelled out in [scenario_protocol.py](../src/glossogen/scenario_protocol.py). The key ones:

- `name()` → the registry key (string).
- `scenario_description()` → a short human-readable description.
- `knobs_model()` → classmethod returning your `<YourKnobs>` class. The base derives `knobs_json_schema()` from it — you no longer write the schema accessor.
- `get_knobs()` → return `self._knobs`. The base derives `get_round_count()`, `get_max_round_duration_seconds()`, and `get_scenario_config()` from it — you no longer write those getters.
- `create_from_config(config)` → classmethod factory that validates the dict against `<YourKnobs>` and constructs the scenario.
- `get_agent_roles(knobs)` → classmethod returning `(agent_id, role_name)` pairs used for agent-model override validation in CLI run-config preflight. Receives a possibly-partial `dict | None`; read role-determining flags with `self.resolve_bool_knob(knobs=knobs, field_name=...)`.
- `get_agents()`, `get_channels()`, `get_world()`, `get_mcp_tools()` — wire up the world plus the per-agent role configs (system prompt path, channels, tools, MCP).
- `get_injection(round_number, agent_id, previous_outcome, current_case)` → renders the per-round Jinja injection for an agent.
- `get_postmortem_injection(round_number, agent_id, previous_outcome)` → optional postmortem-phase injection.
- `on_round_advanced(round_number, world_context, event_logger)` → emit your `<Scenario>CaseStarted` event so metrics can read per-round ground truth.
- `on_round_ended(round_number, world_context, event_logger)` → settle round-end state.
- `validate_outgoing_message(...)`, `transform_outgoing_message(...)` → enforce / mutate messages (budget enforcement, noise injection).
- `get_primary_channels()` → **required** — return the `PrimaryChannel` list telling generic metrics (perplexity, mean-chars-per-round, mean-chars-per-message, language judges) which channel(s) to score. Two-team scenarios return one entry per team's channel; return `[]` only if the scenario has no channel worth scoring.
- `get_early_round_end_trigger()` → optional; returns a trigger string when the round should end early (e.g. once a `target_placed` flag and `executed_moves` count match the expected sequence).
- `judge_round_result(round_number, trigger)` → **required** — return a list of `RoundResult(success, team_id, reason)`. The game clock writes one `RoundResultRecorded` event per element; the platform `round_success` metric reads these directly and emits one Measurement per `team_id` (single-team scenarios pass `team_id=None` and get one Measurement named `round_success`). Return `[]` only if the scenario genuinely has no per-round success criterion.
- `restore_state_from_events(events)` → optional. Called after a fork/resume rewind has been built and before the runtime starts. Walk the event list and seed any per-round outcomes you need so the first post-resume injection renders accurate "previous result" context (most scenarios need this only if their injection templates surface prior-round state).

For scenarios with custom tools (anything beyond `send_message`), `get_mcp_tools()` returns one [`ScenarioMcpTool`](../src/glossogen/runtime/scenario_mcp_tool.py) per tool — that's where you wire up freetext-argument LLM judges, world state mutations, and the marker strings the tool result returns.

### Optional platform hooks (post-simulation analysis)

These are opt-in: implement them only if you want the corresponding platform metric to run on your scenario. Returning `None` / `[]` (the default) makes the metric skip with no Measurement.

- `build_communication_rounds(events) -> list[CommunicationRoundView]` → opt the scenario into the `communication_open_coding` + `communication_feature_presence` pipeline. Each view joins one round's primary-channel messages with a scenario-rendered ground-truth block. Returning `[]` (default) skips both metrics.
- `detect_protocol_boundary_window(events, agent_configs) -> ProtocolBoundaryWindow | None` → drives `protocol_learned_after_swap`. The default returns the first `AgentSwappedMidRun` boundary (scheduled in-run swaps). Override to detect scenario-specific boundaries first (intern takeover, two-team observer swap) and fall back to `super().detect_protocol_boundary_window(...)` for scheduled swaps.
- `get_protocol_probe_config() -> ProtocolProbeConfig | None` → opts into the four-metric `protocol_probe` family. Returns a NamedTuple of (`questions_path`, `prompts_dir`, `role_groups`, `role_templates`). Ship the question bank as `<scenario>/protocol_probe_questions.json` and probe-prompt templates under `<scenario>/prompts/`. See [veyru/scenario.py](../src/glossogen/scenarios/veyru/scenario.py) for the canonical wiring and [veyru/scripts/build_probe_questions.py](../src/glossogen/scenarios/veyru/scripts/build_probe_questions.py) for a generator pattern.
- `get_replace_agent_blocked_tool_call_channels() -> frozenset[str]` → channel IDs whose `send_message` / `read_channel` calls should be stripped from a replaced agent's reconstructed history (typically your postmortem / discussion channel).

### 8. Write `prompts/`

Every prompt is a Jinja2 template, never a hardcoded string in Python. Required:

- `description.jinja` — `scenario.description()` reads it.
- `<role>_system.jinja` — one per agent. Receives `channels`, `postmortem_enabled`, scenario knobs.
- `<role>_injection.jinja` — one per agent. Rendered at each round start. Receives `round_number`, `current_case`, `previous_outcome`, `knobs`.
- `postmortem_injection.jinja` — if `postmortem_enabled` can be true, render the postmortem-phase injection here.

For scenarios with LLM judges, one `<judge_name>.jinja` per judge — these are the system prompts handed to the judge's `generate_structured(...)` call. Judges live in a separate `<scenario>_judge.py` module and pull their templates via `TemplateRenderer`.

### 9. (Optional) Write `evaluation/`

Most scoring is now scenario-agnostic. Because `get_primary_channels()` is required, you get every generic primary-channel metric for free:

| Metric | Hook the scenario must implement |
|---|---|
| `perplexity`, `mean_chars_per_round`, `mean_chars_per_message`, `language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes` | `get_primary_channels()` |
| `round_ended_idle`, `round_ended_timeout`, `content_filter_refusal` | (nothing — read straight from `RoundEnded` / `AgentRunCycleFailed`) |
| `round_success` | `judge_round_result(round_number, trigger)` |
| `round_success_after_resume` | `judge_round_result(...)` + the run was launched via replace-agent / cross-run / scheduled swap / resume-at-round |
| `protocol_learned_after_swap` | `build_communication_rounds(events)` + `detect_protocol_boundary_window(...)` |
| `communication_open_coding`, `communication_feature_presence` | `build_communication_rounds(events)` |
| `protocol_probe` family (4 metrics) | `get_protocol_probe_config()` |

Add a scenario-specific metric under `evaluation/` only when the platform doesn't already cover what you want to measure (a domain-specific signal that doesn't reduce to round-success or to language phenomena on the primary channel). If you do, `evaluation/__init__.py` should export the metric class so the scenario can register it in its metric registry.

### 10. (Optional) Add a run-detail extension

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

### 11. (Optional) Add a frontend plug-in

If you want a bespoke knobs form (instead of the standard preset picker), a custom panel inside the round-timeline modal, or a default knobs payload for the cross-run replace-agent dialog, ship a `ScenarioPlugin` at `frontend/src/features/runs/<your_scenario>/plugin.tsx` and register it in [scenario-registry.ts](../frontend/src/features/runs/scenario-registry.ts):

```ts
import { yourPlugin } from "./your_scenario/plugin";

const SCENARIO_PLUGINS: Record<string, ScenarioPlugin> = {
  [veyruPlugin.scenarioName]: veyruPlugin,
  [yourPlugin.scenarioName]: yourPlugin,
};
```

The plug-in contract is in [scenario-plugin.ts](../frontend/src/features/runs/scenario-plugin.ts). The Veyru plug-in at [veyru/plugin.tsx](../frontend/src/features/runs/veyru/plugin.tsx) is the canonical example. Each slot is optional — return `null` / `{}` to fall through to the platform defaults.

### 12. Register the scenario

Add one line to [src/glossogen/scenario_registry.py](../src/glossogen/scenario_registry.py):

```python
from glossogen.scenarios.your_scenario.scenario import YourScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    ...,
    "your_scenario": YourScenario,
}
```

This is the only file outside your scenario package you have to touch for the scenario itself. (Event types, run-detail extras, SSE events, frontend plug-ins are all auto-discovered.)

## Smoke test

Run a short simulation end-to-end before claiming the scenario works:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run your_scenario \
  --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/your_scenario/knobs_default.json \
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

- [ ] `__init__.py` files (namespace + scenario) are empty.
- [ ] `events.py` imports only from `glossogen.models.event_base`.
- [ ] Every knobs field is required (no defaults); preset values live in `knobs_default.json`.
- [ ] `judge_model = "claude-haiku-4-5-20251001"`, `judge_provider = "anthropic"`, `seed = 42` in the preset.
- [ ] Prompts live in `prompts/*.jinja`, not in Python string literals.
- [ ] `judge_round_result(round_number, trigger)` returns at least one `RoundResult` per round (single-team scenarios: one with `team_id=None`; multi-team: one per team). The game clock writes `RoundResultRecorded` events from these; the platform `round_success` metric reads them directly.
- [ ] `get_primary_channels()` (required) returns a non-empty `PrimaryChannel` list — the comm-link channel for single-team, one entry per team's channel for two-team.
- [ ] If you added a run-detail extension, re-run `make gen-api-types` so `frontend/src/types/api.gen.ts` includes your `XxxRunExtras` variant.
- [ ] `make lint` is clean. Regenerate the vulture whitelist (`VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 60 --make-whitelist > vulture_whitelist.py`) if Pydantic fields or auto-discovered classes get flagged.
- [ ] At least one end-to-end smoke run completes and the `round_success` metric returns a non-empty per-round list.

## Common pitfalls

**Circular import on event discovery.** If you see `ImportError` mentioning your scenario at platform startup, check that (a) `__init__.py` is empty and (b) `events.py` doesn't import from `glossogen.models.event`.

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
