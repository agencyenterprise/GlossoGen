"""In-memory state and immutable records for team production."""

from dataclasses import dataclass, field
from typing import NamedTuple

from glossogen.scenarios.bonded_team_production.cases import ZoneCase
from glossogen.scenarios.bonded_team_production.ids import MEMBERSHIP_ACTIVE


@dataclass
class ProviderState:
    agent_id: str
    balance: float
    membership_state: str
    pending_membership_decision: str | None = None
    confirmed_violation_count: int = 0

    @property
    def is_member(self) -> bool:
        return self.membership_state == MEMBERSHIP_ACTIVE


class PrivateChannelRecord(NamedTuple):
    channel_id: str
    creator_id: str
    member_agent_ids: tuple[str, ...]
    name: str


@dataclass
class ZoneState:
    zone_id: str
    true_count: int
    stale_count: int
    assigned_agent_id: str | None = None
    promised_payment: float = 0.0
    accepted: bool = False
    inspected: bool = False
    submitted_count: int | None = None

    @property
    def correct(self) -> bool:
        return self.submitted_count is not None and self.submitted_count == self.true_count


@dataclass
class AssignmentOffer:
    zone_id: str
    lead_id: str
    provider_id: str
    promised_payment: float
    response: str | None = None


@dataclass
class WorkAttestation:
    agent_id: str
    zone_id: str
    claim: str
    effort_performed: bool
    false_claim: bool
    disclosed_concern: str


@dataclass
class JobState:
    case_number: int
    contract_type: str
    lead_id: str | None
    zones: dict[str, ZoneState]
    audit_sampled: bool
    attestation_queried: bool
    economic_profile: str
    effort_cost: float
    contract_fee: float
    stale_count_match_probability: float
    offers: dict[str, AssignmentOffer] = field(default_factory=dict[str, AssignmentOffer])
    delivered: bool = False
    lead_fee_credited: float = 0.0
    bond_contribution: float = 0.0
    distribution_finalized: bool = False
    attestations_requested: bool = False
    attestations: dict[str, WorkAttestation] = field(default_factory=dict[str, WorkAttestation])
    transfers: list["TransferRecord"] = field(default_factory=list["TransferRecord"])

    @property
    def staffed(self) -> bool:
        return self.lead_id is not None

    @property
    def all_zones_assigned(self) -> bool:
        return all(
            zone.assigned_agent_id is not None and zone.accepted for zone in self.zones.values()
        )

    @property
    def ready_to_deliver(self) -> bool:
        return self.all_zones_assigned and all(
            zone.submitted_count is not None for zone in self.zones.values()
        )

    @property
    def correct(self) -> bool:
        return self.delivered and all(zone.correct for zone in self.zones.values())

    def assigned_agent_ids(self) -> tuple[str, ...]:
        return tuple(
            zone.assigned_agent_id
            for zone in self.zones.values()
            if zone.assigned_agent_id is not None and zone.accepted
        )

    def actions_complete(self) -> bool:
        if not self.delivered or not self.distribution_finalized:
            return False
        if not self.attestations_requested:
            return True
        return all(agent_id in self.attestations for agent_id in self.assigned_agent_ids())


class BalanceChange(NamedTuple):
    agent_id: str
    balance_before: float
    balance_after: float


class MembershipChange(NamedTuple):
    agent_id: str
    previous_state: str
    new_state: str
    reason: str
    balance_before: float
    balance_after: float


class OfferRecord(NamedTuple):
    zone_id: str
    lead_id: str
    provider_id: str
    promised_payment: float


class OfferResponseRecord(NamedTuple):
    zone_id: str
    provider_id: str
    response: str
    promised_payment: float
    stale_count: int | None


class EffortRecord(NamedTuple):
    agent_id: str
    zone_id: str
    true_count: int
    effort_cost: float
    balance_before: float
    balance_after: float


class ZoneSubmissionRecord(NamedTuple):
    agent_id: str
    zone_id: str
    submitted_count: int
    true_count: int
    stale_count: int
    inspected: bool
    correct: bool


class DeliveryRecord(NamedTuple):
    lead_id: str
    contract_type: str
    contract_fee: float
    bond_contribution: float
    lead_credit: float
    balance_before: float
    balance_after: float
    correct: bool


class TransferRecord(NamedTuple):
    sender_id: str
    recipient_id: str
    amount: float
    note: str
    sender_balance_before: float
    sender_balance_after: float
    recipient_balance_before: float
    recipient_balance_after: float


class AttestationRecord(NamedTuple):
    attestation: WorkAttestation


class RepairRecord(NamedTuple):
    agent_id: str
    case_number: int
    action: str
    contribution_amount: float
    statement: str
    material: bool
    balance_before: float
    balance_after: float


class PendingAudit(NamedTuple):
    case_number: int
    resolve_at_round: int
    contract_type: str
    true_counts: dict[str, int]
    submitted_counts: dict[str, int]
    provider_by_zone: dict[str, str]
    lead_id: str | None
    contract_fee: float


class LeadLiabilityRecord(NamedTuple):
    lead_id: str
    case_number: int
    refund_amount: float
    balance_before: float
    balance_after: float


class AuditResolution(NamedTuple):
    case_number: int
    contract_type: str
    correct: bool
    incorrect_zone_ids: tuple[str, ...]
    implicated_agent_ids: tuple[str, ...]
    lead_id: str | None
    refund_due: float
    refund_paid: float
    refund_source: str
    bond_balance: float
    lead_liability: LeadLiabilityRecord | None
    sanctions: tuple["SanctionRecord", ...]
    probationed_agent_ids: tuple[str, ...]
    expelled_agent_ids: tuple[str, ...]


class SanctionRecord(NamedTuple):
    agent_id: str
    case_number: int
    fine_amount: float
    balance_before: float
    balance_after: float
    confirmed_violation_count: int
    expulsion_violation_threshold: int


@dataclass
class RepairCase:
    case_number: int
    implicated_agent_ids: tuple[str, ...]
    opened_at_round: int
    acted_agent_ids: set[str] = field(default_factory=set[str])


class RoundOpening(NamedTuple):
    membership_changes: tuple[MembershipChange, ...]
    audit_resolutions: tuple[AuditResolution, ...]


class RoundOutcome(NamedTuple):
    round_number: int
    case_number: int
    contract_type: str
    completed: bool
    correct: bool
    lead_id: str | None
    zone_count: int
    accepted_assignments: int
    submitted_assignments: int
    inspected_assignments: int
    promised_total: float
    paid_to_assignees: float
    distribution_finalized: bool
    bond_balance: float
    economic_profile: str
    effort_cost: float
    contract_fee: float
    stale_count_match_probability: float


def build_zone_states(zones: tuple[ZoneCase, ...]) -> dict[str, ZoneState]:
    """Convert immutable case zones into fresh mutable round state."""
    return {
        zone.zone_id: ZoneState(
            zone_id=zone.zone_id,
            true_count=zone.true_count,
            stale_count=zone.stale_count,
        )
        for zone in zones
    }
