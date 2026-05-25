"""Shared response models used across multiple server subpackages."""

from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Health check status values."""

    OK = "ok"


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: HealthStatus


class LaunchStatus(str, Enum):
    """Status value for subprocess launch responses."""

    STARTED = "started"
