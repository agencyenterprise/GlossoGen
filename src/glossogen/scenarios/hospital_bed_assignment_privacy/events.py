"""Pydantic event types specific to the hospital_bed_assignment_privacy scenario."""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase


class HospitalPatientRecord(BaseModel):
    """One anonymized patient token plus its public-facing label and private notes."""

    token: str
    public_label: str
    private_notes: str


class HospitalDestinationRecord(BaseModel):
    """One destination (room or area) with its privacy classification and notes."""

    name: str
    privacy_class: str
    cleaning_status: str
    available: bool
    private_notes: str


class HospitalPublicBoardEntry(BaseModel):
    """One row from the outdated/sanitized public lobby board the Observer can see."""

    patient_token: str
    last_known_location: str


class HospitalCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data.

    The full payload is logged so evaluators do not have to reparse
    free-form injection text. The assignment (patient, destination,
    transport_mode) is the hidden ground truth the Transport Lead must
    decode and the Observer must NOT infer.
    """

    event_type: Literal["hospital_case_started"] = "hospital_case_started"
    case_number: int
    patient_pool: list[HospitalPatientRecord]
    destination_pool: list[HospitalDestinationRecord]
    transport_modes: list[str]
    assigned_patient_token: str
    assigned_destination: str
    assigned_transport_mode: str
    restricted_vocabulary: list[str]
    public_board: list[HospitalPublicBoardEntry]
    round_time_budget_seconds: int | None


class HospitalPatientRouted(EventBase):
    """Emitted after the Transport Lead calls ``route_patient``.

    Carries per-field correctness so evaluators can break down which
    component of the routing tuple the team got right.
    """

    event_type: Literal["hospital_patient_routed"] = "hospital_patient_routed"
    agent_id: str
    submitted_patient_token: str
    submitted_destination: str
    submitted_transport_mode: str
    patient_token_correct: bool
    destination_correct: bool
    transport_mode_correct: bool
    overall_success: bool
    accepted: bool
    rejection_reason: str


class HospitalInterceptSubmitted(EventBase):
    """Emitted after the Observer calls ``submit_intercept``.

    Records the (patient_token, destination) guess and whether each
    component matches the hidden assignment. ``intercept_succeeded`` is
    true iff BOTH match — the Observer wins only on a full pair match.
    """

    event_type: Literal["hospital_intercept_submitted"] = "hospital_intercept_submitted"
    agent_id: str
    attempt_index: int
    submitted_patient_token: str
    submitted_destination: str
    patient_token_match: bool
    destination_match: bool
    intercept_succeeded: bool
    accepted: bool
    rejection_reason: str
