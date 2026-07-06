"""Pydantic models representing discrete events emitted during a simulation run.

Core platform event subclasses live here. Scenario-specific event subclasses
live in ``schmidt/scenarios/<scenario>/events.py``. At module load time
:func:`_discover_scenario_event_types` walks the ``schmidt.scenarios``
namespace package, imports every ``events`` submodule, and assembles them
together with the core events into :data:`SIMULATION_EVENT_ADAPTER` — a
discriminated-union :class:`pydantic.TypeAdapter` used by the JSONL
parser. Scenario authors register new event types by adding them to
their scenario's ``events.py``; no edit to this module is required.

``EventBase`` and ``TokenUsage`` live in :mod:`schmidt.models.event_base`
so scenario event modules can subclass ``EventBase`` without a circular
dependency on this module.
"""

import importlib
import pkgutil
from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import Discriminator, TypeAdapter

import schmidt.scenarios
from schmidt.models.event_base import EventBase, TokenUsage
from schmidt.models.message import SimulationMessage
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runtime.scheduled_events import ChannelVisibility


class SimulationStarted(EventBase):
    """Emitted once when a simulation begins, recording the scenario, channels, and config."""

    event_type: Literal["simulation_started"] = "simulation_started"
    run_id: str
    scenario_name: str
    scenario_description: str
    channel_ids: list[str]
    scenario_config: dict[str, Any] = {}
    provider: str


class AgentRegistered(EventBase):
    """Emitted when an agent joins the simulation, capturing its
    role, prompt, channels, and tools.
    """

    event_type: Literal["agent_registered"] = "agent_registered"
    agent_id: str
    role_name: str
    system_prompt: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    provider: str
    max_tokens: int


class AgentConnected(EventBase):
    """Emitted when an autonomous agent connects to the simulation runtime."""

    event_type: Literal["agent_connected"] = "agent_connected"
    agent_id: str
    role_name: str
    model: str


class MessageSent(EventBase):
    """Emitted when an agent sends a message to a channel."""

    event_type: Literal["message_sent"] = "message_sent"
    message: SimulationMessage
    token_count: int


class LLMResponseReceived(EventBase):
    """Emitted when the LLM returns a response, including generated
    text, tool calls, stop reason, and token usage.
    """

    event_type: Literal["llm_response_received"] = "llm_response_received"
    agent_id: str
    thinking: str | None = None
    text: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: str
    usage: TokenUsage


class ToolCallInvoked(EventBase):
    """Emitted when an agent invokes a tool, before it executes. Provides the
    authoritative timestamp for the ToolUseEntry rendered in the UI, since the
    enclosing LLMResponseReceived is only logged after the full turn completes.
    """

    event_type: Literal["tool_call_invoked"] = "tool_call_invoked"
    agent_id: str
    call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolResultReceived(EventBase):
    """Emitted when a tool call completes and the result is returned to the agent."""

    event_type: Literal["tool_result_received"] = "tool_result_received"
    agent_id: str
    tool_name: str
    call_id: str
    arguments: dict[str, Any]
    result: str


class ContextCompacted(EventBase):
    """Emitted when the provider compacts an agent's message history into a summary.

    Surfaced from a ``CompactionPart`` in the model response when the
    ``compaction`` knob is enabled. Anthropic returns a readable text summary
    (captured in full in ``summary_text``); OpenAI stores an encrypted summary
    server-side and returns no text, so ``summary_char_count`` is 0 and
    ``summary_text`` is empty.
    """

    event_type: Literal["context_compacted"] = "context_compacted"
    agent_id: str
    provider_name: str
    summary_char_count: int
    summary_text: str


class RoundAdvanced(EventBase):
    """Emitted when the game clock advances to a new round in autonomous mode."""

    event_type: Literal["round_advanced"] = "round_advanced"
    trigger: str


class AgentRunCycleFailed(EventBase):
    """Emitted when agent.run() raised an exception in the runner's retry loop.

    Covers every pydantic_ai exception class (ContentFilterError, ModelHTTPError,
    UsageLimitExceeded, UnexpectedModelBehavior, etc.) and any other exception
    raised by the underlying agent.run() call. The runner retries after emission,
    so each event represents one wasted cycle, not a fatal simulation error.
    """

    event_type: Literal["agent_run_cycle_failed"] = "agent_run_cycle_failed"
    agent_id: str
    cycle: int
    error_type: str
    message: str


class RoundEnded(EventBase):
    """Emitted when a round's main phase ends, before any postmortem phase begins.

    Captures why the round's main phase terminated (``all_agents_idle`` or
    ``round_timeout``). Distinct from ``RoundAdvanced.trigger``, which describes
    why the most recent phase (round OR postmortem) ended immediately before
    the clock advances to the next round.
    """

    event_type: Literal["round_ended"] = "round_ended"
    trigger: str


class RoundResultRecorded(EventBase):
    """Structured per-round result emitted by the scenario.

    Emitted by the game clock immediately after ``on_round_ended`` runs,
    one event per result returned by
    :meth:`SimulationScenario.judge_round_result`. Single-team
    scenarios emit one event per round with ``team_id=None``;
    multi-team scenarios emit one event per team with ``team_id`` set.
    Scenarios that do not override the hook emit nothing.
    """

    event_type: Literal["round_result_recorded"] = "round_result_recorded"
    round_number: int
    success: bool
    team_id: str | None
    reason: str


class InjectionDelivered(EventBase):
    """Emitted when a scenario injection is delivered to an agent."""

    event_type: Literal["injection_delivered"] = "injection_delivered"
    agent_id: str
    text: str


class RunStatus(str, Enum):
    """Status of a simulation run."""

    SCENARIO_COMPLETE = "scenario_complete"
    IN_PROGRESS = "in_progress"
    STARTING = "starting"
    ERROR = "error"
    KILLED = "killed"


class WorldEventDelivered(EventBase):
    """Emitted when a world simulation pushes a notification to an agent."""

    event_type: Literal["world_event_delivered"] = "world_event_delivered"
    agent_id: str
    text: str


class PostmortemStarted(EventBase):
    """Emitted when the game clock enters a postmortem discussion phase after a round."""

    event_type: Literal["postmortem_started"] = "postmortem_started"


class PostmortemEnded(EventBase):
    """Emitted when a round's postmortem discussion phase ends.

    The postmortem-phase counterpart of :class:`RoundEnded`. ``trigger`` records
    why the postmortem terminated (``all_agents_idle`` or ``postmortem_timeout``).
    Emitted for every postmortem phase, including the final round's — which is not
    followed by a ``RoundAdvanced`` and would otherwise have no event capturing why
    it ended.
    """

    event_type: Literal["postmortem_ended"] = "postmortem_ended"
    trigger: str


class ChannelHistoryCleared(EventBase):
    """Emitted when a channel's message history is wiped mid-run."""

    event_type: Literal["channel_history_cleared"] = "channel_history_cleared"
    channel_id: str
    reason: str


class ChannelMembershipChanged(EventBase):
    """Emitted when a channel's member agent list is reassigned mid-run."""

    event_type: Literal["channel_membership_changed"] = "channel_membership_changed"
    channel_id: str
    member_agent_ids: list[str]
    reason: str


class SimulationEnded(EventBase):
    """Emitted when the simulation finishes, with termination reason, message count, and cost."""

    event_type: Literal["simulation_ended"] = "simulation_ended"
    reason: RunStatus
    total_messages: int
    total_cost_usd: float


class AgentSwappedMidRun(EventBase):
    """Emitted when the in-run scheduler swaps one agent for a fresh instance.

    Captures the swap-time round, the agent_id whose seat changed, the
    new model/provider, and the per-channel history visibility config
    used when reconstructing the new agent's pydantic-ai history. Used
    by resume-aware metrics to compute per-swap performance windows
    (replaces ``replace_manifest.json`` for in-run swaps).
    """

    event_type: Literal["agent_swapped_mid_run"] = "agent_swapped_mid_run"
    agent_id: str
    new_model: str
    new_provider: str
    channel_visibility: dict[str, ChannelVisibility]


class PostmortemDisabledMidRun(EventBase):
    """Emitted when the in-run scheduler disables postmortem at a round boundary.

    The world's ``disable_postmortem_globally()`` flag is flipped at
    this point; subsequent postmortem injections and phase entries are
    skipped for the rest of the run.
    """

    event_type: Literal["postmortem_disabled_mid_run"] = "postmortem_disabled_mid_run"


class CaseInjectedMidRun(EventBase):
    """Emitted when the in-run scheduler fires an ``InjectCase`` event.

    The scenario decodes ``scenario_payload`` into its own case-data shape
    and arranges for the round-``round_number`` injection to render that
    case instead of the natural-cycle pick. Mirrors ``AgentSwappedMidRun``
    and ``PostmortemDisabledMidRun`` so the resume-anchored metrics +
    ``RewindState.rounds_with_fired_scheduler_events`` tracker treat this
    boundary the same way (skip re-firing on resume past it).
    """

    event_type: Literal["case_injected_mid_run"] = "case_injected_mid_run"
    scenario_payload: dict[str, Any]


_CORE_EVENT_TYPES: tuple[type[EventBase], ...] = (
    SimulationStarted,
    AgentRegistered,
    AgentConnected,
    MessageSent,
    LLMResponseReceived,
    ToolCallInvoked,
    ToolResultReceived,
    ContextCompacted,
    RoundAdvanced,
    AgentRunCycleFailed,
    RoundEnded,
    RoundResultRecorded,
    InjectionDelivered,
    PostmortemStarted,
    PostmortemEnded,
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    WorldEventDelivered,
    SimulationEnded,
    AgentSwappedMidRun,
    PostmortemDisabledMidRun,
    CaseInjectedMidRun,
)


def _discover_scenario_event_types() -> tuple[type[EventBase], ...]:
    """Discover every ``EventBase`` subclass exported by a scenario ``events`` module.

    Walks the ``schmidt.scenarios`` namespace package, imports each
    ``<scenario_pkg>.events`` submodule when present, and collects every
    module member that subclasses ``EventBase``. Scenario authors register
    new event types by adding them to their scenario's ``events.py`` —
    no edit to this module is required.
    """
    collected: list[type[EventBase]] = []
    for module_info in pkgutil.iter_modules(schmidt.scenarios.__path__):
        if not module_info.ispkg:
            continue
        events_module_name = f"schmidt.scenarios.{module_info.name}.events"
        try:
            events_module = importlib.import_module(events_module_name)
        except ModuleNotFoundError:
            continue
        for attr_name in dir(events_module):
            attr = getattr(events_module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, EventBase)
                and attr is not EventBase
                and attr not in collected
            ):
                collected.append(attr)
    return tuple(collected)


_SCENARIO_EVENT_TYPES: tuple[type[EventBase], ...] = _discover_scenario_event_types()

_ALL_EVENT_TYPES: tuple[type[EventBase], ...] = (*_CORE_EVENT_TYPES, *_SCENARIO_EVENT_TYPES)

# Statically-typed alias used by consumers. ``EventBase`` declares the
# ``event_type`` discriminator, so type-checked code can read it on a generic
# event without narrowing to a concrete subclass via ``isinstance`` first.
# Concrete-subclass-specific fields still require ``isinstance`` narrowing.
SimulationEvent: TypeAlias = EventBase

# Runtime parsing uses the full discriminated union built from the discovered
# scenario event types. ``Union`` accepts a tuple of types at runtime; the
# ``Any`` cast hides this from the static type checker since the tuple is
# only known at runtime.
_simulation_event_union: Any = Union[_ALL_EVENT_TYPES]
SIMULATION_EVENT_ADAPTER: TypeAdapter[EventBase] = TypeAdapter(
    Annotated[_simulation_event_union, Discriminator("event_type")]
)
