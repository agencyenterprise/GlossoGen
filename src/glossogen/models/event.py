"""Pydantic models representing discrete events emitted during a simulation run.

Core platform event subclasses live here. Scenario-specific event subclasses
live in ``glossogen/scenarios/<scenario>/events.py``. At module load time
:func:`_discover_scenario_event_types` walks the ``glossogen.scenarios``
namespace package, imports every ``events`` submodule, and assembles them
together with the core events into :data:`SIMULATION_EVENT_ADAPTER` — a
discriminated-union :class:`pydantic.TypeAdapter` used by the JSONL
parser. Scenario authors register new event types by adding them to
their scenario's ``events.py``; no edit to this module is required.

``EventBase`` and ``TokenUsage`` live in :mod:`glossogen.models.event_base`
so scenario event modules can subclass ``EventBase`` without a circular
dependency on this module.
"""

from enum import Enum, StrEnum
from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import Discriminator, Field, TypeAdapter

from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.message import SimulationMessage
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.models.thinking_part_record import ThinkingPartRecord
from glossogen.models.tool_definition import RecordedToolDefinition, ToolCallRequest
from glossogen.runtime.scheduled_events import ChannelVisibility
from glossogen.runtime.wait_for import WaitFor
from glossogen.scenario_submodule_discovery import concrete_subclasses, import_scenario_submodules


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

    ``tool_definitions`` holds the schema of every tool in ``tool_names``. It
    defaults to empty so that logs recorded before schemas were logged still parse.

    ``runner_prompts`` holds the scenario's replacement for the runner prompts,
    or None when the agent ran with the platform's. It is left out of the JSON
    when None.
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
    tool_definitions: list[RecordedToolDefinition] = []
    runner_prompts: RunnerPrompts | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


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


class StopReason(StrEnum):
    """Why one LLM response block ended: more tool calls follow, or the turn is over."""

    END_TURN = "end_turn"
    TOOL_USE = "tool_use"


class LLMResponseReceived(EventBase):
    """Emitted when the LLM returns a response, including generated
    text, tool calls, stop reason, and token usage.

    ``thinking`` is the response's reasoning as one text, for display.
    ``thinking_parts`` holds the same reasoning part by part with each part's
    provider identifiers, which is what a reconstructed history sends back.
    It defaults to empty so logs recorded before parts were logged still parse.
    """

    event_type: Literal["llm_response_received"] = "llm_response_received"
    agent_id: str
    thinking: str | None = None
    thinking_parts: list[ThinkingPartRecord] = []
    text: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: StopReason
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

    Emitted once per compaction, in the round where it fired (flushed when the
    model request that compacted finishes streaming, not at agent-cycle end,
    cycles span many rounds). ``summary_text`` is reconstructed from the streamed
    ``CompactionPart`` deltas; it may be empty even when a compaction fired (e.g.
    OpenAI stores an encrypted summary server-side and returns no text).
    ``part_id`` and ``provider_details`` preserve the provider payload needed to
    use this compaction as a boundary after a run is resumed. ``replayable`` is
    false for older logs whose text was recorded for display, not provider replay.
    """

    event_type: Literal["context_compacted"] = "context_compacted"
    agent_id: str
    provider_name: str
    summary_char_count: int
    summary_text: str
    part_id: str | None = None
    provider_details: dict[str, Any] | None = None
    replayable: bool = False


class RoundAdvanced(EventBase):
    """Emitted when the game clock advances to a new round in autonomous mode.

    ``trigger`` is a ``RoundEndTrigger`` value.
    """

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
    """A ``RoundEndTrigger`` value, or the scenario's own early round-end trigger."""


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
    Emitted for every postmortem phase, including the final round's, which is not
    followed by a ``RoundAdvanced`` and would otherwise have no event capturing why
    it ended.
    """

    event_type: Literal["postmortem_ended"] = "postmortem_ended"
    trigger: str
    """A ``RoundEndTrigger`` value."""


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


class ChannelCreated(EventBase):
    """Emitted when a channel is created during the run, such as a direct channel.

    A direct channel is created the first time an agent addresses a set of
    teammates no existing channel has as its exact membership.
    """

    event_type: Literal["channel_created"] = "channel_created"
    channel_id: str
    name: str
    member_agent_ids: list[str]


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

    ``system_prompt`` is the base prompt the swapped-in agent was seeded with:
    the swap's own when it set one, otherwise the seat's registered prompt. It
    defaults to ``None`` so that logs recorded before it was logged still parse.
    """

    event_type: Literal["agent_swapped_mid_run"] = "agent_swapped_mid_run"
    agent_id: str
    new_model: str
    new_provider: str
    channel_visibility: dict[str, ChannelVisibility]
    system_prompt: str | None = None


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
    ``RewindState.completed_scheduler_event_count_by_round`` tracker treats this
    boundary the same way (skip re-firing on resume past it).
    """

    event_type: Literal["case_injected_mid_run"] = "case_injected_mid_run"
    scenario_payload: dict[str, Any]


class WaitRegistered(EventBase):
    """Emitted when an agent's ``read_notifications`` call parks it.

    ``deadline_s`` is the timeout in seconds, or None for a wait with none.
    """

    event_type: Literal["wait_registered"] = "wait_registered"
    agent_id: str
    wait_id: str
    wait_for: WaitFor
    deadline_s: float | None


class AgentResumed(EventBase):
    """Emitted when a parked agent resumes, with why and how long it waited."""

    event_type: Literal["agent_resumed"] = "agent_resumed"
    agent_id: str
    wait_id: str
    wake_reasons: list[str]
    waited_seconds: float
    terminated: bool


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
    ChannelCreated,
    WorldEventDelivered,
    SimulationEnded,
    AgentSwappedMidRun,
    PostmortemDisabledMidRun,
    CaseInjectedMidRun,
    WaitRegistered,
    AgentResumed,
)


def _discover_scenario_event_types() -> tuple[type[EventBase], ...]:
    """Discover every ``EventBase`` subclass exported by a scenario ``events`` module.

    Imports each scenario's ``events`` submodule (registering its classes in
    ``EventBase.__subclasses__``), then returns every concrete ``EventBase``
    subclass that is not one of the core types. Scenario authors register new
    event types by adding them to their scenario's ``events.py``, with no edit to
    this module is required.
    """
    import_scenario_submodules(submodule_name="events")
    core = frozenset(_CORE_EVENT_TYPES)
    return tuple(cls for cls in concrete_subclasses(base=EventBase) if cls not in core)


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


def core_event_types() -> tuple[type[EventBase], ...]:
    """Return the event types the platform itself declares.

    A scenario's own types are checked against these: a discriminator that
    repeats one of them shadows the platform's event in the parser, and the run
    that wrote it reads back as something else afterwards. The conformance checks
    need this list, and building a union of their own is how they avoid depending
    on whether the scenario under test was discovered at import time.
    """
    return _CORE_EVENT_TYPES


def parser_for(event_types: tuple[type[EventBase], ...]) -> TypeAdapter[EventBase]:
    """Build a parser over exactly these event types.

    Constructing one is itself a check: pydantic refuses a discriminated union whose
    members repeat a discriminator or whose ``event_type`` is not a literal. Separate
    from :data:`SIMULATION_EVENT_ADAPTER` because that one was built while this
    module was importing, so it cannot see a scenario loaded from a path
    afterwards, and reading it would pass a built-in and fail an identical
    plug-in.
    """
    union: Any = Union[event_types]
    return TypeAdapter(Annotated[union, Discriminator("event_type")])
