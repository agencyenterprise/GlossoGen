"""Event schemas for joint client-commitment trajectories."""

from typing import Literal

from glossogen.models.event_base import EventBase


class JointCommitmentRoundStarted(EventBase):
    """Records one shared client-protection opportunity."""

    event_type: Literal["joint_commitment_round_started"] = "joint_commitment_round_started"
    condition: str


class JointCommitmentPledgeSubmitted(EventBase):
    """Records one provider's public pledge choice."""

    event_type: Literal["joint_commitment_pledge_submitted"] = "joint_commitment_pledge_submitted"
    agent_id: str
    decision: str
    pledge_text: str


class JointCommitmentBondPosted(EventBase):
    """Records the escrowed covenant bond for one provider."""

    event_type: Literal["joint_commitment_bond_posted"] = "joint_commitment_bond_posted"
    agent_id: str
    amount: int


class JointCommitmentDecisionRecorded(EventBase):
    """Records a private reserve decision and public attestation."""

    event_type: Literal["joint_commitment_decision_recorded"] = "joint_commitment_decision_recorded"
    agent_id: str
    actual_action: str
    public_attestation: str
    reserve_remitted: int
    reserve_retained: int
    earnings_before: int
    earnings_after: int


class JointCommitmentRoundSettled(EventBase):
    """Records completion and client-safety state after both decisions."""

    event_type: Literal["joint_commitment_round_settled"] = "joint_commitment_round_settled"
    condition: str
    completed: bool
    missing_provider_ids: list[str]
    safe_client_outcome: bool | None
    audit_selected: bool


class JointCommitmentAuditResolved(EventBase):
    """Records a delayed audit's provider-level verification result."""

    event_type: Literal["joint_commitment_audit_resolved"] = "joint_commitment_audit_resolved"
    audited_round: int
    agent_id: str
    actual_action: str
    public_attestation: str
    truthful: bool
    violation: bool
    bond_forfeited: int
    membership_in_good_standing: bool


class JointCommitmentMembershipChanged(EventBase):
    """Records loss of covenant good standing after an audited violation."""

    event_type: Literal["joint_commitment_membership_changed"] = (
        "joint_commitment_membership_changed"
    )
    agent_id: str
    membership_in_good_standing: bool
    reason: str
