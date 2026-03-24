"""Pydantic response models for all server API endpoints and SSE event schemas."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator

from schmidt.evaluation.evaluation_report import Verdict
from schmidt.models.event import RunStatus


class HealthStatus(str, Enum):
    """Health check status values."""

    OK = "ok"


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: HealthStatus


class RunSummary(BaseModel):
    """Summary of a single simulation run for the runs list endpoint."""

    run_id: str
    scenario_name: str
    scenario_description: str
    scenario_config: dict[str, Any]
    timestamp: datetime
    total_turns: int
    status: RunStatus
    has_evaluation: bool
    run_dir: str


class RunListResponse(BaseModel):
    """Response model for the list-all-runs endpoint."""

    runs: list[RunSummary]


class AgentDetail(BaseModel):
    """Full agent information for the run detail endpoint."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    system_prompt: str


class ChannelMessage(BaseModel):
    """A message sent by an agent to a channel."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    turn_number: int
    round_number: int


class ReasoningEntry(BaseModel):
    """An LLM reasoning/thinking entry from an agent's turn."""

    message_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    turn_number: int
    round_number: int


class DebugLogEntry(BaseModel):
    """A single debug log entry from the simulation run."""

    timestamp: str
    logger_name: str
    level: str
    message: str


class EvalMetricResponse(BaseModel):
    """Result of a single evaluator for the run detail endpoint."""

    evaluator_name: str
    verdict: Verdict
    score: float
    evidence: list[str]
    per_agent: dict[str, Verdict]


class EvalReportResponse(BaseModel):
    """Evaluation report for the run detail endpoint."""

    metrics: list[EvalMetricResponse]


class RunDetailResponse(BaseModel):
    """Full detail of a simulation run including agents, messages, and evaluation."""

    run_id: str
    scenario_name: str
    scenario_description: str
    scenario_config: dict[str, Any]
    timestamp: datetime
    total_turns: int
    status: RunStatus
    channel_ids: list[str]
    agents: list[AgentDetail]
    messages: list[ChannelMessage]
    reasoning: list[ReasoningEntry]
    debug_logs: list[DebugLogEntry]
    evaluation: EvalReportResponse | None


# ---------------------------------------------------------------------------
# SSE event schemas — typed models for the events streamed via
# GET /api/runs/{run_id}/events. These mirror the backend SimulationEvent
# models but are tailored for frontend consumption.
# ---------------------------------------------------------------------------


class SSESimulationMessagePayload(BaseModel):
    """Nested message payload inside an SSE message_sent event."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime


class SSESimulationStarted(BaseModel):
    """SSE event emitted once when a simulation begins."""

    event_type: Literal["simulation_started"]
    event_id: str
    timestamp: datetime
    scenario_name: str
    scenario_description: str
    channel_ids: list[str]
    scenario_config: dict[str, Any]


class SSEAgentRegistered(BaseModel):
    """SSE event emitted when an agent joins the simulation."""

    event_type: Literal["agent_registered"]
    event_id: str
    timestamp: datetime
    agent_id: str
    role_name: str
    system_prompt: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str


class SSETurnAssigned(BaseModel):
    """SSE event emitted when a turn is assigned to an agent."""

    event_type: Literal["turn_assigned"]
    event_id: str
    timestamp: datetime
    agent_id: str
    turn_number: int
    round_number: int


class SSEMessageSent(BaseModel):
    """SSE event emitted when an agent sends a message to a channel."""

    event_type: Literal["message_sent"]
    event_id: str
    timestamp: datetime
    message: SSESimulationMessagePayload


class SSELLMResponseReceived(BaseModel):
    """SSE event emitted when the LLM returns a response (reasoning text)."""

    event_type: Literal["llm_response_received"]
    event_id: str
    timestamp: datetime
    agent_id: str
    text: str | None


class SSESimulationEnded(BaseModel):
    """SSE event emitted once when the simulation finishes."""

    event_type: Literal["simulation_ended"]
    event_id: str
    timestamp: datetime
    reason: RunStatus
    total_turns: int


class SSETokenDelta(BaseModel):
    """SSE event emitted token-by-token during LLM response streaming.

    Transient — not persisted to JSONL. The complete text arrives in a
    subsequent SSELLMResponseReceived event.
    """

    event_type: Literal["token_delta"]
    agent_id: str
    text: str
    is_final: bool


class SSEMessagePreview(BaseModel):
    """SSE event for in-progress send_message text preview.

    Transient — not persisted to JSONL. The complete message arrives in a
    subsequent SSEMessageSent event.
    """

    event_type: Literal["message_preview"]
    agent_id: str
    channel_id: str
    text: str
    is_final: bool


SSEEvent = Annotated[
    Union[
        SSESimulationStarted,
        SSEAgentRegistered,
        SSETurnAssigned,
        SSEMessageSent,
        SSELLMResponseReceived,
        SSESimulationEnded,
        SSETokenDelta,
        SSEMessagePreview,
    ],
    Discriminator("event_type"),
]
