"""Pydantic models representing discrete events emitted during a simulation run.

Each event type captures a specific occurrence (e.g. a turn being assigned, a message
being sent, an LLM call completing) and is tagged with a literal ``event_type``
discriminator. The ``SimulationEvent`` union at the bottom collects all concrete
event types for serialization and dispatch.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, Discriminator, Field

from schmidt.models.message import SimulationMessage
from schmidt.models.tool_definition import ToolCallRequest, ToolCallResult


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
    scenario_name: str
    scenario_description: str
    channel_ids: list[str]
    scenario_config: dict[str, Any] = Field(default_factory=dict)


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


class TurnAssigned(EventBase):
    """Emitted when a turn is assigned to an agent."""

    event_type: Literal["turn_assigned"] = "turn_assigned"
    agent_id: str
    turn_number: int
    round_number: int


class MessageSent(EventBase):
    """Emitted when an agent sends a message to a channel."""

    event_type: Literal["message_sent"] = "message_sent"
    message: SimulationMessage


class ToolCalled(EventBase):
    """Emitted when an agent invokes a tool, containing the full tool call request."""

    event_type: Literal["tool_called"] = "tool_called"
    agent_id: str
    request: ToolCallRequest


class ToolResultReturned(EventBase):
    """Emitted when a tool execution completes and the result is returned to the agent."""

    event_type: Literal["tool_result_returned"] = "tool_result_returned"
    agent_id: str
    result: ToolCallResult


class LLMRequestSent(EventBase):
    """Emitted when a request is sent to the LLM, capturing the
    prompt, message history, and available tools.
    """

    event_type: Literal["llm_request_sent"] = "llm_request_sent"
    agent_id: str
    system_prompt: str
    messages: list[dict[str, Any]]
    tool_names: list[str]


class LLMResponseReceived(EventBase):
    """Emitted when the LLM returns a response, including generated
    text, tool calls, stop reason, and token usage.
    """

    event_type: Literal["llm_response_received"] = "llm_response_received"
    agent_id: str
    text: str | None
    tool_calls: list[ToolCallRequest]
    stop_reason: str
    usage: TokenUsage


class TurnPassed(EventBase):
    """Emitted when an agent calls pass_turn to decline speaking on their turn."""

    event_type: Literal["turn_passed"] = "turn_passed"
    agent_id: str
    reason: str


class RunStatus(str, Enum):
    """Why the simulation ended."""

    SCENARIO_COMPLETE = "scenario_complete"
    IN_PROGRESS = "in_progress"
    ERROR = "error"


class SimulationEnded(EventBase):
    """Emitted once when the simulation finishes, recording the
    termination reason and turn count.
    """

    event_type: Literal["simulation_ended"] = "simulation_ended"
    reason: RunStatus
    total_turns: int


SimulationEvent = Annotated[
    Union[
        SimulationStarted,
        AgentRegistered,
        TurnAssigned,
        MessageSent,
        ToolCalled,
        ToolResultReturned,
        LLMRequestSent,
        LLMResponseReceived,
        TurnPassed,
        SimulationEnded,
    ],
    Discriminator("event_type"),
]
