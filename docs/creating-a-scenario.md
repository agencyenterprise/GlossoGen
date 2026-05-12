# Creating a new scenario

This guide walks through adding a new scenario to schmidt end-to-end. By the end you'll have a registered scenario, a working smoke run, and (optionally) bespoke run-detail data on the API and bespoke UI on the frontend — every extension surface that exists today, all opt-in.

If you just want to copy an existing scenario as a starting point, [container_yard_stacking](../src/schmidt/scenarios/container_yard_stacking/) is the freshest 3-agent reference — its file list and shape is what this guide aims at.

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

The platform discovers events, run-detail extensions, and frontend plug-ins automatically. The only file you have to *register* in is [scenario_registry.py](../src/schmidt/scenario_registry.py).

## Package layout

```
src/schmidt/scenarios/<your_scenario>/
├── __init__.py                  # MUST stay empty (see "Why empty inits" below)
├── README.md                    # scenario-specific docs
├── ids.py                       # agent IDs, channel IDs, tool names, world markers
├── knobs.py                     # ScenarioKnobs Pydantic model extending BaseKnobs
├── knobs_default.json           # canonical preset (referenced by the CLI's --config)
├── events.py                    # scenario-specific EventBase subclasses (auto-discovered)
├── world.py                     # ScenarioWorld subclass: state + on_message + run loop
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

The scenario package's `__init__.py` MUST stay empty. The platform's event-discovery walker (`schmidt.models.event._discover_scenario_event_types`) imports `schmidt.scenarios.<name>.events` directly via `pkgutil`. If `__init__.py` re-exported anything from `scenario.py`, importing the events module would cascade into `scenario.py`, which imports back from `schmidt.models.event` — and that module is mid-import when discovery runs. Empty inits break that cycle.

For the same reason, `events.py` must import only from [`schmidt.models.event_base`](../src/schmidt/models/event_base.py) (which defines `EventBase` and `TokenUsage`), never from `schmidt.models.event`.

## Step-by-step

### 1. Create the package skeleton

```bash
mkdir -p src/schmidt/scenarios/<your_scenario>/prompts
touch src/schmidt/scenarios/<your_scenario>/__init__.py
```

Leave `__init__.py` empty.

### 2. Write `ids.py`

Centralize every literal string the scenario uses — agent IDs, channel IDs, tool names, world-event marker strings, and per-agent tool lists. Keeps the rest of the package free of magic strings.

See [container_yard_stacking/ids.py](../src/schmidt/scenarios/container_yard_stacking/ids.py) for a worked example. Typical contents:

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

Define a `ScenarioKnobs` Pydantic model that extends `BaseKnobs`. Every field MUST be required (no defaults — per the project's "no default parameter values" rule); presets supply values via `knobs_default.json`.

```python
from schmidt.knobs_base import BaseKnobs
from pydantic import Field, model_validator

class ContainerYardStackingKnobs(BaseKnobs):
    judge_model: str
    judge_provider: str
    postmortem_enabled: bool
    postmortem_disabled_at_start: bool
    round_count: int
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

Declare each scenario-specific event class as an `EventBase` subclass with a unique `event_type` discriminator. The platform's discovered-union JSONL parser picks them up automatically; you don't edit `schmidt/models/event.py`.

```python
from typing import Literal
from pydantic import BaseModel
from schmidt.models.event_base import EventBase


class YardCaseStarted(EventBase):
    event_type: Literal["yard_case_started"] = "yard_case_started"
    case_number: int
    incoming_container: str
    target_position: str
    # ...
```

**Critical**: import only from `schmidt.models.event_base`, never from `schmidt.models.event`.

### 6. Write `world.py`

Subclass `ScenarioWorld` (defined in [scenario_world.py](../src/schmidt/runtime/scenario_world.py)). The world is the live simulated environment — it consumes inbound messages, mutates internal state, emits notifications to agents via `world_context.deliver_world_event(...)`, and decides when a round succeeds or fails.

The shape to mimic is [`WarehouseWorld`](../src/schmidt/scenarios/warehouse_robot_recovery/world.py) (single-tool scenarios) or [`ContainerYardWorld`](../src/schmidt/scenarios/container_yard_stacking/world.py) (multi-tool scenarios with sequenced action state).

The world is also the place where:
- **Per-character budget mechanics** live (subtract message length from a budget; emit `BUDGET_EXCEEDED_MARKER` notification when exhausted).
- **Postmortem channel logic** lives (postmortem messages do NOT cost budget; postmortem can be globally disabled mid-run).
- **Markers** are emitted at the end of each round — `ROUND_SUCCESS_MARKER` or `ROUND_FAILED_MARKER` — so the `round_success` metric can detect outcomes deterministically from the event log.

### 7. Write `scenario.py`

The `SimulationScenario` subclass — the entry point the registry hands to the CLI and frontend. Required classmethods and methods are spelled out in [scenario_protocol.py](../src/schmidt/scenario_protocol.py). The key ones:

- `name()` → the registry key (string).
- `description()` → a short human-readable description.
- `knobs_json_schema()` → returns `<YourKnobs>.model_json_schema()`.
- `create_from_config(config, model, provider, ...)` → factory that validates the dict against `<YourKnobs>` and constructs the scenario.
- `get_agent_roles(knobs)` → classmethod returning `(agent_id, role_name)` pairs used by the new-simulation form for agent-model overrides.
- `get_agents()`, `get_channels()`, `get_world()`, `get_mcp_tools()` — wire up the world plus the per-agent role configs (system prompt path, channels, tools, MCP).
- `get_injection(round_number, agent_id, previous_outcome, current_case)` → renders the per-round Jinja injection for an agent.
- `get_postmortem_injection(round_number, agent_id, previous_outcome)` → optional postmortem-phase injection.
- `on_round_advanced(round_number, world_context, event_logger)` → emit your `<Scenario>CaseStarted` event so metrics can read per-round ground truth.
- `on_round_ended(round_number, world_context, event_logger)` → settle round-end state.
- `validate_outgoing_message(...)`, `transform_outgoing_message(...)` → enforce / mutate messages (budget enforcement, noise injection).
- `get_primary_channel_id()` → tells generic metrics (perplexity, mean-chars-per-round, mean-chars-per-message) which channel to score.
- `get_early_round_end_trigger()` → optional; returns a trigger string when the round should end early (e.g. once a `target_placed` flag and `executed_moves` count match the expected sequence).

For scenarios with custom tools (anything beyond `send_message`), `get_mcp_tools()` returns one [`ScenarioMcpTool`](../src/schmidt/runtime/scenario_mcp_tool.py) per tool — that's where you wire up freetext-argument LLM judges, world state mutations, and the marker strings the tool result returns.

### 8. Write `prompts/`

Every prompt is a Jinja2 template, never a hardcoded string in Python. Required:

- `description.jinja` — `scenario.description()` reads it.
- `<role>_system.jinja` — one per agent. Receives `channels`, `postmortem_enabled`, scenario knobs.
- `<role>_injection.jinja` — one per agent. Rendered at each round start. Receives `round_number`, `current_case`, `previous_outcome`, `knobs`.
- `postmortem_injection.jinja` — if `postmortem_enabled` can be true, render the postmortem-phase injection here.

For scenarios with LLM judges, one `<judge_name>.jinja` per judge — these are the system prompts handed to the judge's `generate_structured(...)` call. Judges live in a separate `<scenario>_judge.py` module and pull their templates via `TemplateRenderer`.

### 9. (Optional) Write `evaluation/`

The generic metrics (`perplexity`, `mean_chars_per_round`, `mean_chars_per_message`, `round_ended_idle`, `round_ended_timeout`, `content_filter_refusal`, and the four LLM-judge ones — `language_strangeness`, `slang_emergence`, `neologism`, `shorthand_codes`) all run automatically without scenario-specific code as long as `get_primary_channel_id()` is set.

Add scenario-specific metrics — most importantly `round_success` — under `evaluation/`. The pattern is in [warehouse_robot_recovery/evaluation/round_success_metric.py](../src/schmidt/scenarios/warehouse_robot_recovery/evaluation/round_success_metric.py): grep the event log for `<Scenario>CaseStarted` and the `ROUND_SUCCESS_MARKER` / `ROUND_FAILED_MARKER` notifications the world emitted, count successes, return one `Measurement`.

`evaluation/__init__.py` should export your metric classes so the scenario can register them in its metric registry.

### 10. (Optional) Add a run-detail extension

If you want per-round case ground truth, judge metadata keyed by tool `call_id`, or custom SSE events to appear on the run-detail API (and thence on the frontend), add `src/schmidt/scenarios/<your_scenario>/run_detail_extension.py`. The platform auto-discovers it at startup.

The full contract is in [scenario_extension.py](../src/schmidt/server/runs/scenario_extension.py); the canonical example is [veyru/run_detail_extension.py](../src/schmidt/scenarios/veyru/run_detail_extension.py).

Minimal shape:

```python
from typing import ClassVar, Literal
from pydantic import BaseModel
from schmidt.models.event import SimulationEvent
from schmidt.server.runs.run_detail_types import AgentDetail, ChannelMessage
from schmidt.server.runs.scenario_extension import (
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

Add one line to [src/schmidt/scenario_registry.py](../src/schmidt/scenario_registry.py):

```python
from schmidt.scenarios.your_scenario.scenario import YourScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    ...,
    "your_scenario": YourScenario,
}
```

This is the only file outside your scenario package you have to touch for the scenario itself. (Event types, run-detail extras, SSE events, frontend plug-ins are all auto-discovered.)

## Smoke test

Run a short simulation end-to-end before claiming the scenario works:

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run your_scenario \
  --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/your_scenario/knobs_default.json \
  round_count=3 \
  > ./runs/your_scenario_smoke.log 2>&1 &
```

Monitor per the CLAUDE.md sleep-30-tail pattern. Pass criteria:

1. The log finishes with `Simulation complete. Run directory: runs/your_scenario/<timestamp>`.
2. The JSONL contains your `<Scenario>CaseStarted` event once per round and `ROUND_SUCCESS_MARKER` or `ROUND_FAILED_MARKER` markers exactly once per round.
3. If you added a run-detail extension, loading the run in `make dev` + `make dev-frontend` shows your scenario-specific data in the round-timeline modal.

Then evaluate:

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate your_scenario \
  --run-dir ./runs/your_scenario/<timestamp> \
  --metrics round_success,mean_chars_per_round,mean_chars_per_message \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

The report should contain one Measurement per metric with sensible `score` and `per_round` values.

## Pre-flight checklist

Before opening a PR:

- [ ] `__init__.py` files (namespace + scenario) are empty.
- [ ] `events.py` imports only from `schmidt.models.event_base`.
- [ ] Every knobs field is required (no defaults); preset values live in `knobs_default.json`.
- [ ] `judge_model = "claude-haiku-4-5-20251001"`, `judge_provider = "anthropic"`, `seed = 42` in the preset.
- [ ] Prompts live in `prompts/*.jinja`, not in Python string literals.
- [ ] World emits `ROUND_SUCCESS_MARKER` or `ROUND_FAILED_MARKER` exactly once per round.
- [ ] `get_primary_channel_id()` returns the comm-link channel (or `None` for two-team scenarios where the metric should no-op).
- [ ] If you added a run-detail extension, re-run `make gen-api-types` so `frontend/src/types/api.gen.ts` includes your `XxxRunExtras` variant.
- [ ] `make lint` is clean. Regenerate the vulture whitelist (`VIRTUAL_ENV= uv run --no-sync vulture src/ --min-confidence 60 --make-whitelist > vulture_whitelist.py`) if Pydantic fields or auto-discovered classes get flagged.
- [ ] At least one end-to-end smoke run completes and the `round_success` metric returns a non-empty per-round list.

## Common pitfalls

**Circular import on event discovery.** If you see `ImportError` mentioning your scenario at platform startup, check that (a) `__init__.py` is empty and (b) `events.py` doesn't import from `schmidt.models.event`.

**Vulture flags scenario classes as unused.** Pydantic fields, auto-discovered extension classes, and metric classes can look unused. Regenerate the whitelist as shown above.

**Pyright stale cache during incremental edits.** Pyright sometimes caches old module symbols across edits. Restart the language server or run `make lint-server` directly to confirm whether errors are real.

**Frontend types out of sync.** The OpenAPI types in `frontend/src/types/api.gen.ts` are generated. After any backend schema change (e.g. adding a `ScenarioRunExtrasBase` subclass), run `make gen-api-types`. CI fails if the file drifts from the backend schema.

**Per-scenario script paths.** One-off scripts that import your scenario directly belong under `src/schmidt/scenarios/<your_scenario>/scripts/`, not the repo-root `scripts/` folder. Cross-scenario tools (the OpenAPI exporter, generic diagnostic tools) stay in `scripts/`.

## Reference scenarios

When in doubt, mirror an existing scenario:

- [container_yard_stacking](../src/schmidt/scenarios/container_yard_stacking/) — most recent 3-agent build; freetext tool args with LLM judges, multi-call sequenced actions, per-round changing geometry. Cleanest "follow this layout" template.
- [warehouse_robot_recovery](../src/schmidt/scenarios/warehouse_robot_recovery/) — 3-agent, single-tool recovery with per-character budget. Simplest "single judged action" pattern.
- [satellite_contact_window](../src/schmidt/scenarios/satellite_contact_window/) — 3-agent, sequenced command submission judged in one call against an authorization envelope.
- [veyru](../src/schmidt/scenarios/veyru/) — 2-agent baseline scenario; the most heavily extended scenario, including a run-detail extension, a frontend plug-in, per-scenario scripts, and many bespoke metrics. The canonical example for every optional extension surface.
