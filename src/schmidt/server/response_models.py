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
