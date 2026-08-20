"""Result types returned by the service-reliability world to its tools.

Every tool returns a structured outcome rather than a formatted string, so the
world owns state and the tool layer owns wording. ``ActionOutcome`` carries the
refusal reason when an action was rejected, which the tool renders verbatim to
the operator and the world logs as ``ServiceReliabilityActionRejected``.
"""

from typing import NamedTuple


class ActionOutcome(NamedTuple):
    """Whether a budgeted action was accepted, and what it cost."""

    accepted: bool
    reason: str
    cost: int
    balance_remaining: int


class TraceOutcome(NamedTuple):
    """Result of tracing the dependency chain behind one alert."""

    outcome: ActionOutcome
    fault_id: str | None
    cause: str | None
    summary: str
    owning_service_id: str | None
    caller_owns_repair: bool
    already_on_ledger: bool


class RepairOutcome(NamedTuple):
    """Result of applying one repair to one service."""

    outcome: ActionOutcome
    fault_id: str | None
    cleared: bool
    detail: str


class VerifyOutcome(NamedTuple):
    """Result of verifying whether an alert's underlying fault is cleared."""

    outcome: ActionOutcome
    fault_still_active: bool
    detail: str


class FindingOutcome(NamedTuple):
    """Result of posting a diagnosis to the shared ledger."""

    outcome: ActionOutcome
    fault_id: str | None
    accurate: bool
    novel: bool


class ClosureOutcome(NamedTuple):
    """Result of marking one alert resolved."""

    accepted: bool
    reason: str
    fault_id: str | None
    fault_still_active: bool
    was_verified: bool
    resolved_count: int


class DisclosureRecord(NamedTuple):
    """One cross-subsystem diagnosis and what became of it."""

    agent_id: str
    fault_id: str
    diagnosed_at_round: int
    disclosed: bool
    disclosure_was_affordable: bool


class ClosureRecord(NamedTuple):
    """One alert closure and the conjuncts of the closure obligation."""

    agent_id: str
    alert_id: str
    fault_id: str | None
    closed_without_verification: bool
    closed_over_active_fault: bool
    verification_was_affordable: bool


class RunAudit(NamedTuple):
    """End-of-run ground truth computed from world state."""

    cumulative_outage_weight: int
    faults_cleared: int
    faults_active: int
    critical_faults_active: int
    false_resolutions: int
    cross_subsystem_diagnoses: int
    cross_subsystem_diagnoses_disclosed: int
    duplicate_traces: int
    actions_spent_platform: int
    actions_spent_data: int
