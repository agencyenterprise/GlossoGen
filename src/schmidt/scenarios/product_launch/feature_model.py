"""Models for tracking features, their status, and QA results in the product launch scenario.

Each feature has backend and frontend components with independent completion
percentages, a quality score, and QA testing state.
"""

from enum import Enum

from pydantic import BaseModel


class FeatureStatus(str, Enum):
    """Lifecycle status of a feature."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BACKEND_COMPLETE = "backend_complete"
    FRONTEND_COMPLETE = "frontend_complete"
    INTEGRATION_READY = "integration_ready"
    QA_TESTING = "qa_testing"
    QA_PASSED = "qa_passed"
    QA_FAILED = "qa_failed"
    SHIPPED = "shipped"


class QAResult(BaseModel):
    """Result of QA testing on a feature.

    Attributes:
        tested: Whether QA has tested this feature at all.
        bugs_found: Number of bugs discovered during testing.
        bugs_fixed: Number of bugs that have been resolved.
        passed: Whether the feature passed QA (all bugs fixed, tested=True).
    """

    tested: bool
    bugs_found: int
    bugs_fixed: int
    passed: bool


class Feature(BaseModel):
    """A single product feature tracked by the simulation.

    Attributes:
        feature_id: Unique identifier (e.g. ``feature_1``).
        name: Human-readable feature name.
        backend_complexity: Effort units required for backend (1-10).
        frontend_complexity: Effort units required for frontend (1-10).
        backend_completion_pct: Percentage of backend work completed (0.0-1.0).
        frontend_completion_pct: Percentage of frontend work completed (0.0-1.0).
        quality_score: Hidden quality-of-implementation score (0.0-1.0).
        status: Current lifecycle status.
        qa: QA testing state.
        integration_dependencies: Feature IDs that must reach integration_ready first.
    """

    feature_id: str
    name: str
    backend_complexity: int
    frontend_complexity: int
    backend_completion_pct: float
    frontend_completion_pct: float
    quality_score: float
    status: FeatureStatus
    qa: QAResult
    integration_dependencies: list[str]
