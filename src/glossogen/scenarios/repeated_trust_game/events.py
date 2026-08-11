"""Event schemas for repeated human-parallel trust-game decisions."""

from typing import Literal

from glossogen.models.event_base import EventBase


class RepeatedTrustRoundStarted(EventBase):
    """Records the condition and counterbalanced roles for one round."""

    event_type: Literal["repeated_trust_round_started"] = "repeated_trust_round_started"
    condition: str
    trustor_id: str
    trustee_id: str
    pledge_enabled: bool
    forfeiture_fraction: float


class RepeatedTrustPledgeSubmitted(EventBase):
    """Records one participant's structured covenant response."""

    event_type: Literal["repeated_trust_pledge_submitted"] = "repeated_trust_pledge_submitted"
    agent_id: str
    decision: str
    pledge_text: str


class RepeatedTrustDecisionRecorded(EventBase):
    """Records one amount selected in a trust or reciprocity role."""

    event_type: Literal["repeated_trust_decision_recorded"] = "repeated_trust_decision_recorded"
    agent_id: str
    role: str
    amount: int
    maximum_amount: int
    gross_earnings: float
    forfeiture_paid: float
    net_earnings: float
    balance_before: float
    balance_after: float


class RepeatedTrustRoundSettled(EventBase):
    """Records the paired decision outcome after a round boundary."""

    event_type: Literal["repeated_trust_round_settled"] = "repeated_trust_round_settled"
    condition: str
    completed: bool
    missing_participant_ids: list[str]
    trustor_id: str
    trustee_id: str
    trust_sent: int | None
    reciprocity_returned: int | None
