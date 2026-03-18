"""Pydantic response models for all server API endpoints."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

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
    initials: str
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


class RunDetailResponse(BaseModel):
    """Full detail of a simulation run including agents and messages."""

    run_id: str
    scenario_name: str
    timestamp: datetime
    total_turns: int
    end_reason: EndReason
    channel_ids: list[str]
    agents: list[AgentDetail]
    messages: list[MessageDetail]
