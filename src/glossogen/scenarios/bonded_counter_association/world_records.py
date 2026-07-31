"""Immutable records describing what the world did, for the scenario to log.

The world owns state mutation but has no event logger; the scenario and the
MCP tool executors own logging. So every world method that changes state
returns one of these records and the caller turns it into the corresponding
``bonded_counter_*`` event. Keeping the translation in one direction means a
state change can never happen without a loggable record of it.
"""

from typing import NamedTuple

from glossogen.scenarios.bonded_counter_association.client_choice import ClientDecision
from glossogen.scenarios.bonded_counter_association.world_state import ProcessAttestation


class BalanceChange(NamedTuple):
    """One provider's balance before and after a single settlement step."""

    agent_id: str
    balance_before: float
    balance_after: float


class MembershipChange(NamedTuple):
    """A membership transition applied at a round boundary."""

    agent_id: str
    previous_state: str
    new_state: str
    reason: str
    stake_paid: float
    stake_forfeited: float
    balance_before: float
    balance_after: float


class BondChange(NamedTuple):
    """One movement of the shared refund bond."""

    delta: float
    balance_before: float
    balance_after: float
    unpaid_liability: float
    reason: str


class SanctionRecord(NamedTuple):
    """A fine or individual refund liability charged to one provider."""

    agent_id: str
    case_number: int
    fine_amount: float
    individual_liability: float
    reason: str
    balance_before: float
    balance_after: float


class ExpulsionRecord(NamedTuple):
    """A membership removal caused by a detected violation."""

    agent_id: str
    case_number: int
    permanent: bool
    reentry_allowed_at_round: int | None
    reason: str


class InsolvencyRecord(NamedTuple):
    """The first time the bond could not cover a refund liability."""

    case_number: int
    refund_due: float
    bond_balance: float
    unpaid_liability: float


class AuditResolution(NamedTuple):
    """A delayed audit becoming public, with everything it triggered."""

    case_number: int
    contract_type: str
    count_correct: bool
    signed_count: int | None
    true_count: int
    primary_counter_id: str | None
    verifier_id: str | None
    primary_inspected: bool
    verifier_recounted: bool
    implicated_agent_ids: tuple[str, ...]
    refund_due: float
    client_error_loss: float
    bond_changes: tuple[BondChange, ...]
    sanctions: tuple[SanctionRecord, ...]
    expulsions: tuple[ExpulsionRecord, ...]
    insolvency: InsolvencyRecord | None


class RepairWindowOpened(NamedTuple):
    """A repair window opened for the providers an audit implicated."""

    case_number: int
    implicated_agent_ids: tuple[str, ...]
    contribution_allowed: bool
    contribution_limit: float


class JobAssignment(NamedTuple):
    """The round's contract type and role assignment."""

    contract_type: str
    primary_counter_id: str | None
    verifier_id: str | None
    client_decision: ClientDecision


class RoundOpening(NamedTuple):
    """Everything the world did while opening a round, in application order.

    Ordering matches the specified round flow: audits reveal, repair windows
    open, resulting corrections and sanctions apply, the membership window
    opens, then the client picks a contract and roles are assigned.
    """

    membership_changes: tuple[MembershipChange, ...]
    audit_resolutions: tuple[AuditResolution, ...]
    repair_windows: tuple[RepairWindowOpened, ...]
    membership_window_open: bool
    assignment: JobAssignment


class EffortResult(NamedTuple):
    """A paid inspection or recount."""

    agent_id: str
    true_count: int
    effort_cost: float
    balance_before: float
    balance_after: float


class CountSubmission(NamedTuple):
    """A primary counter's submitted count and the hidden facts around it."""

    agent_id: str
    submitted_count: int
    true_count: int
    correct: bool
    inspected: bool
    knew_true_count: bool
    reused_stale_count: bool


class SignoffSubmission(NamedTuple):
    """A verifier's sign-off and the hidden facts around it."""

    agent_id: str
    signed_count: int
    submitted_count: int
    true_count: int
    correct: bool
    recounted: bool
    knew_true_count: bool
    endorsed_without_change: bool


class RepairSubmission(NamedTuple):
    """One structured repair action and its material effect."""

    agent_id: str
    case_number: int
    action: str
    corrected_count: int | None
    contribution_amount: float
    statement: str
    rounds_since_audit: int
    material: bool
    balance_before: float
    balance_after: float
    record_correction: "RecordCorrection | None"
    bond_change: BondChange | None


class RecordCorrection(NamedTuple):
    """A repair action rewriting the public signed count for a job."""

    agent_id: str
    case_number: int
    previous_signed_count: int | None
    corrected_count: int
    corrected_count_matches_truth: bool


class MembershipDecisionRecord(NamedTuple):
    """A provider's membership decision, queued for the next round boundary."""

    agent_id: str
    decision: str
    current_state: str


class AttestationRecord(NamedTuple):
    """A submitted process attestation and the world's hidden comparison."""

    attestation: ProcessAttestation


class UnauthorizedAttempt(NamedTuple):
    """A rejected action outside the caller's role or phase."""

    agent_id: str
    tool_name: str
    expected_role: str
    actual_role: str
    phase: str
    reason: str
    prompted_by_probe: bool


class RoundSettlement(NamedTuple):
    """The end-of-round settlement of fees, effort, and bond contributions."""

    case_number: int
    contract_type: str
    completed: bool
    incomplete_reason: str
    signed_count: int | None
    true_count: int
    count_correct: bool
    primary_counter_id: str | None
    verifier_id: str | None
    primary_inspected: bool
    verifier_recounted: bool
    contract_fee: float
    bond_contribution: float
    provider_payments: tuple[BalanceChange, ...]
    client_fee_paid: float
    client_error_loss: float
    bond_change: BondChange | None
    audit_scheduled_at_round: int | None
