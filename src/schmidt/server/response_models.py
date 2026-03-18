"""Pydantic response models for all server API endpoints."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from schmidt.evaluation.evaluation_report import Verdict
from schmidt.models.event import EndReason


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
    timestamp: datetime
    total_turns: int
    end_reason: EndReason
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


class MessageDetail(BaseModel):
    """A single message with turn context for the run detail endpoint."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    turn_number: int
    round_number: int


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
    right_answer_wrong_reasons: bool | None


class RunDetailResponse(BaseModel):
    """Full detail of a simulation run including agents, messages, and evaluation."""

    run_id: str
    scenario_name: str
    timestamp: datetime
    total_turns: int
    end_reason: EndReason
    channel_ids: list[str]
    agents: list[AgentDetail]
    messages: list[MessageDetail]
    evaluation: EvalReportResponse | None
