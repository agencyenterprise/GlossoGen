"""Event log schema for the team-production experiment."""

from typing import Literal

from pydantic import BaseModel, Field

from glossogen.models.event_base import EventBase


class TeamZoneSnapshot(BaseModel):
    zone_id: str
    true_count: int
    stale_count: int


class TeamProductionCaseStarted(EventBase):
    event_type: Literal["team_production_case_started"] = "team_production_case_started"
    case_number: int
    contract_type: str
    lead_id: str | None
    zones: list[TeamZoneSnapshot]
    association_members: list[str]
    bond_balance: float
    audit_sampled: bool
    attestation_queried: bool
    economic_profile: str = "fixed"
    effort_cost: float = 0.0
    contract_fee: float = 0.0
    stale_count_match_probability: float = 0.0


class TeamProductionMembershipChanged(EventBase):
    event_type: Literal["team_production_membership_changed"] = "team_production_membership_changed"
    agent_id: str
    previous_state: str
    new_state: str
    reason: str
    balance_before: float
    balance_after: float


class TeamProductionMembershipDecisionSubmitted(EventBase):
    event_type: Literal["team_production_membership_decision_submitted"] = (
        "team_production_membership_decision_submitted"
    )
    agent_id: str
    decision: str
    current_state: str


class TeamProductionPrivateChannelCreated(EventBase):
    event_type: Literal["team_production_private_channel_created"] = (
        "team_production_private_channel_created"
    )
    channel_id: str
    creator_id: str
    member_agent_ids: list[str]
    name: str


class TeamProductionAssignmentOffered(EventBase):
    event_type: Literal["team_production_assignment_offered"] = "team_production_assignment_offered"
    zone_id: str
    lead_id: str
    provider_id: str
    promised_payment: float


class TeamProductionAssignmentResponded(EventBase):
    event_type: Literal["team_production_assignment_responded"] = (
        "team_production_assignment_responded"
    )
    zone_id: str
    provider_id: str
    response: str
    promised_payment: float


class TeamProductionZoneInspected(EventBase):
    event_type: Literal["team_production_zone_inspected"] = "team_production_zone_inspected"
    agent_id: str
    zone_id: str
    true_count: int
    effort_cost: float
    balance_before: float
    balance_after: float


class TeamProductionZoneSubmitted(EventBase):
    event_type: Literal["team_production_zone_submitted"] = "team_production_zone_submitted"
    agent_id: str
    zone_id: str
    submitted_count: int
    true_count: int
    stale_count: int
    inspected: bool
    correct: bool


class TeamProductionOrderDelivered(EventBase):
    event_type: Literal["team_production_order_delivered"] = "team_production_order_delivered"
    lead_id: str
    contract_type: str
    contract_fee: float
    bond_contribution: float
    lead_credit: float
    balance_before: float
    balance_after: float
    correct: bool


class TeamProductionFundsTransferred(EventBase):
    event_type: Literal["team_production_funds_transferred"] = "team_production_funds_transferred"
    sender_id: str
    recipient_id: str
    amount: float
    note: str
    sender_balance_before: float
    sender_balance_after: float
    recipient_balance_before: float
    recipient_balance_after: float


class TeamProductionDistributionFinalized(EventBase):
    event_type: Literal["team_production_distribution_finalized"] = (
        "team_production_distribution_finalized"
    )
    lead_id: str
    promised_total: float
    paid_to_assignees: float


class TeamProductionAttestationRequested(EventBase):
    event_type: Literal["team_production_attestation_requested"] = (
        "team_production_attestation_requested"
    )
    requested_agent_ids: list[str]


class TeamProductionAttestationSubmitted(EventBase):
    event_type: Literal["team_production_attestation_submitted"] = (
        "team_production_attestation_submitted"
    )
    agent_id: str
    zone_id: str
    claim: str
    effort_performed: bool
    false_claim: bool
    disclosed_concern: str


class TeamProductionAuditScheduled(EventBase):
    event_type: Literal["team_production_audit_scheduled"] = "team_production_audit_scheduled"
    case_number: int
    resolve_at_round: int
    contract_type: str
    correct: bool


class TeamProductionExternalViolationInjected(EventBase):
    event_type: Literal["team_production_external_violation_injected"] = (
        "team_production_external_violation_injected"
    )
    case_number: int
    agent_id: str
    contract_fee: float


class TeamProductionAuditResolved(EventBase):
    event_type: Literal["team_production_audit_resolved"] = "team_production_audit_resolved"
    case_number: int
    contract_type: str
    correct: bool
    incorrect_zone_ids: list[str]
    implicated_agent_ids: list[str]
    lead_id: str | None = None
    refund_due: float
    refund_paid: float
    refund_source: str = "none"
    bond_balance: float
    probationed_agent_ids: list[str] = Field(default_factory=list[str])
    expelled_agent_ids: list[str]


class TeamProductionLeadLiabilityCharged(EventBase):
    event_type: Literal["team_production_lead_liability_charged"] = (
        "team_production_lead_liability_charged"
    )
    lead_id: str
    case_number: int
    refund_amount: float
    balance_before: float
    balance_after: float


class TeamProductionProviderSanctioned(EventBase):
    event_type: Literal["team_production_provider_sanctioned"] = (
        "team_production_provider_sanctioned"
    )
    agent_id: str
    case_number: int
    fine_amount: float
    balance_before: float
    balance_after: float
    confirmed_violation_count: int = 1
    expulsion_violation_threshold: int = 1


class TeamProductionRepairSubmitted(EventBase):
    event_type: Literal["team_production_repair_submitted"] = "team_production_repair_submitted"
    agent_id: str
    case_number: int
    action: str
    contribution_amount: float
    statement: str
    material: bool
    balance_before: float
    balance_after: float


class TeamProductionOrderSettled(EventBase):
    event_type: Literal["team_production_order_settled"] = "team_production_order_settled"
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
    economic_profile: str = "fixed"
    effort_cost: float = 0.0
    contract_fee: float = 0.0
    stale_count_match_probability: float = 0.0
