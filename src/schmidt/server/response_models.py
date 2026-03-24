"""Pydantic response models for all server API endpoints and SSE event schemas."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

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
    timestamp: datetime
    total_messages: int
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
    """An LLM reasoning/thinking entry from an agent's turn.

    ``channel_ids`` links this reasoning to the channels of the surrounding
    send_message calls from the same agent, so the frontend can show only
    reasoning relevant to the selected channel.
    """

    message_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    turn_number: int
    round_number: int
    channel_ids: list[str]


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
    timestamp: datetime
    total_messages: int
    status: RunStatus
    channel_ids: list[str]
    agents: list[AgentDetail]
    messages: list[ChannelMessage]
    reasoning: list[ReasoningEntry]
    debug_logs: list[DebugLogEntry]
    evaluation: EvalReportResponse | None


# ---------------------------------------------------------------------------
# SSE event schemas — typed models for events streamed via
# GET /api/runs/{run_id}/events.
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


class SSEAgentConnected(BaseModel):
    """SSE event emitted when an agent connects to the MCP server."""

    event_type: Literal["agent_connected"]
    event_id: str
    timestamp: datetime
    agent_id: str


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


class SSERoundAdvanced(BaseModel):
    """SSE event emitted when the game clock advances to a new round."""

    event_type: Literal["round_advanced"]
    event_id: str
    timestamp: datetime
    round_number: int
    trigger: str


class SSEInjectionDelivered(BaseModel):
    """SSE event emitted when a scenario injection is pushed to an agent."""

    event_type: Literal["injection_delivered"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    injection_text: str


class SSESimulationEnded(BaseModel):
    """SSE event emitted once when the simulation finishes."""

    event_type: Literal["simulation_ended"]
    event_id: str
    timestamp: datetime
    reason: RunStatus
    total_messages: int


class SSETokenDelta(BaseModel):
    """SSE event emitted token-by-token during LLM response streaming."""

    event_type: Literal["token_delta"]
    agent_id: str
    text: str
    is_final: bool


class SSEMessagePreview(BaseModel):
    """SSE event for in-progress send_message text preview."""

    event_type: Literal["message_preview"]
    agent_id: str
    channel_id: str
    text: str
    is_final: bool


class SSEDebugLog(BaseModel):
    """SSE event for a real-time debug log entry from the simulation process."""

    event_type: Literal["debug_log"]
    timestamp: str
    logger_name: str
    level: str
    message: str


SSEEvent = Annotated[
    Union[
        SSESimulationStarted,
        SSEAgentRegistered,
        SSEAgentConnected,
        SSEMessageSent,
        SSELLMResponseReceived,
        SSERoundAdvanced,
        SSEInjectionDelivered,
        SSESimulationEnded,
        SSETokenDelta,
        SSEMessagePreview,
        SSEDebugLog,
    ],
    Discriminator("event_type"),
]
