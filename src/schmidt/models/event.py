"""Pydantic models representing discrete events emitted during a simulation run.

Each event type captures a specific occurrence (e.g. an agent connecting, a message
being sent, an LLM response completing) and is tagged with a literal ``event_type``
discriminator. The ``SimulationEvent`` union at the bottom collects all concrete
event types for serialization and dispatch.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Discriminator, Field

from schmidt.models.message import SimulationMessage
from schmidt.models.tool_definition import ToolCallRequest


class TokenUsage(BaseModel):
    """Token counts returned by the LLM for a single request/response cycle."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class EventBase(BaseModel):
    """Base model for all simulation events, providing a unique ID and UTC timestamp."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class SimulationStarted(EventBase):
    """Emitted once when a simulation begins, recording the scenario, channels, and config."""

    event_type: Literal["simulation_started"] = "simulation_started"
    run_id: str
    scenario_name: str
    scenario_description: str
    channel_ids: list[str]
    scenario_config: dict[str, Any] = Field(default_factory=dict)
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
    round_number: int
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
    round_number: int


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
    round_number: int


class ToolResultReceived(EventBase):
    """Emitted when a tool call completes and the result is returned to the agent."""

    event_type: Literal["tool_result_received"] = "tool_result_received"
    agent_id: str
    tool_name: str
    call_id: str
    arguments: dict[str, Any]
    result: str
    round_number: int


class RoundAdvanced(EventBase):
    """Emitted when the game clock advances to a new round in autonomous mode."""

    event_type: Literal["round_advanced"] = "round_advanced"
    round_number: int
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
    round_number: int
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
    round_number: int
    trigger: str


class InjectionDelivered(EventBase):
    """Emitted when a scenario injection is delivered to an agent."""

    event_type: Literal["injection_delivered"] = "injection_delivered"
    agent_id: str
    round_number: int
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
    round_number: int
    text: str


class PostmortemStarted(EventBase):
    """Emitted when the game clock enters a postmortem discussion phase after a round."""

    event_type: Literal["postmortem_started"] = "postmortem_started"
    round_number: int


class ChannelHistoryCleared(EventBase):
    """Emitted when a channel's message history is wiped mid-run."""

    event_type: Literal["channel_history_cleared"] = "channel_history_cleared"
    channel_id: str
    round_number: int
    reason: str


class ChannelMembershipChanged(EventBase):
    """Emitted when a channel's member agent list is reassigned mid-run."""

    event_type: Literal["channel_membership_changed"] = "channel_membership_changed"
    channel_id: str
    round_number: int
    member_agent_ids: list[str]
    reason: str


class SimulationEnded(EventBase):
    """Emitted when the simulation finishes, with termination reason, message count, and cost."""

    event_type: Literal["simulation_ended"] = "simulation_ended"
    reason: RunStatus
    total_messages: int
    total_cost_usd: float


class VeyruStellarReading(BaseModel):
    """Per-round stellar parameters derived from the position of star SAGWE392."""

    offset: int
    hold_duration: int
    starting_face: str
    intensity_level: str = Field(validation_alias=AliasChoices("intensity_level", "pressure_level"))


class VeyruCaseStage(BaseModel):
    """One stage of a Veyru case, with ground-truth symptoms and procedure."""

    motif_name: str
    observable_symptoms: str
    treatment_motif_name: str
    judge_expected_actions: str


class VeyruCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data.

    Evaluators read per-stage `observable_symptoms` and `judge_expected_actions`
    directly from this event, decoupling them from the real observer's
    stabilize_veyru tool calls.
    """

    event_type: Literal["veyru_case_started"] = "veyru_case_started"
    round_number: int
    case_number: int
    failure_name: str
    time_budget_seconds: int
    stages: list[VeyruCaseStage]
    stellar_reading: VeyruStellarReading


class VeyruStabilizationJudged(EventBase):
    """Emitted by the veyru scenario after the stabilization judge rules on a stabilize_veyru call.

    Captures the expected procedure fed to the LLM judge and the judge's
    verdict + explanation, so the frontend can show ground-truth context
    alongside the corresponding ``ToolResultReceived``. Correlated to the
    tool result by (agent_id, FIFO order) because MCP does not expose the
    pydantic-ai tool_call_id inside the executor.
    """

    event_type: Literal["veyru_stabilization_judged"] = "veyru_stabilization_judged"
    agent_id: str
    round_number: int
    expected_actions: str
    judge_match: bool
    judge_explanation: str


SimulationEvent = Annotated[
    Union[
        SimulationStarted,
        AgentRegistered,
        AgentConnected,
        MessageSent,
        LLMResponseReceived,
        ToolCallInvoked,
        ToolResultReceived,
        RoundAdvanced,
        AgentRunCycleFailed,
        RoundEnded,
        InjectionDelivered,
        PostmortemStarted,
        ChannelHistoryCleared,
        ChannelMembershipChanged,
        WorldEventDelivered,
        SimulationEnded,
        VeyruStabilizationJudged,
        VeyruCaseStarted,
    ],
    Discriminator("event_type"),
]
