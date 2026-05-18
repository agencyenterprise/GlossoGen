"""Pydantic event types specific to the satellite_contact_window scenario."""

from typing import Literal

from pydantic import BaseModel

from schmidt.models.event_base import EventBase


class SatelliteCommandStep(BaseModel):
    """One action in a satellite command sequence, with its required wait time."""

    action: str
    wait_seconds: int


class SatelliteActionDependency(BaseModel):
    """An action that must follow another in the submitted command sequence."""

    action: str
    requires_prior_action: str


class SatelliteAuthorizationEnvelope(BaseModel):
    """Per-pass authorization envelope visible only to the flight director."""

    authorized_actions: list[str]
    forbidden_actions: list[str]
    dependencies: list[SatelliteActionDependency]
    remaining_window_seconds: int
    notes: str


class SatelliteTelemetryPatternInstance(BaseModel):
    """One telemetry pattern present on the satellite, with its expected commands."""

    pattern_name: str
    observable_readings: list[str]
    command_sequence: list[SatelliteCommandStep]


class SatelliteCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data.

    Evaluators read patterns, expected command sequence, and the
    authorization envelope directly from this event so they do not have to
    reparse free-form injection text.
    """

    event_type: Literal["satellite_case_started"] = "satellite_case_started"
    case_number: int
    pattern_name: str
    patterns: list[SatelliteTelemetryPatternInstance]
    expected_sequence: list[SatelliteCommandStep]
    authorization_envelope: SatelliteAuthorizationEnvelope
    round_time_budget_seconds: int


class SatelliteCommandJudgment(BaseModel):
    """Structured per-criterion verdict from the satellite command judge."""

    targets_expected_actions: bool
    correct_order: bool
    correct_wait_times: bool
    no_forbidden_actions: bool
    respects_dependencies: bool
    no_missing_steps: bool


class SatelliteCommandSequenceJudged(EventBase):
    """Emitted after the satellite command judge rules on a ``send_command_sequence`` call.

    Captures the ground-truth expected sequence, the authorization envelope,
    the operator's submitted sequence, the per-criterion judge verdict, and
    the judge's free-form explanation so the frontend can show full context
    alongside the ``ToolResultReceived``.
    """

    event_type: Literal["satellite_command_sequence_judged"] = "satellite_command_sequence_judged"
    agent_id: str
    expected_sequence: list[SatelliteCommandStep]
    authorization_envelope: SatelliteAuthorizationEnvelope
    submitted_sequence: list[SatelliteCommandStep]
    judgment: SatelliteCommandJudgment
    overall_success: bool
    budget_exceeded: bool
    violations: list[str]
    judge_explanation: str
