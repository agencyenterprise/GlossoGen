"""Pydantic response models for all server API endpoints."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

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
