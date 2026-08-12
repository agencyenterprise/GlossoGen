"""Event schemas for pledge-breach trajectories."""

from decimal import Decimal
from typing import Literal

from glossogen.models.event_base import EventBase


class PledgeBreachSetupPublished(EventBase):
    """Records publication of the public group registry."""

    event_type: Literal["pledge_breach_setup_published"] = "pledge_breach_setup_published"
    condition: str
    members: list[str]


class PledgeBreachPledgeSubmitted(EventBase):
    """Records one party's visible pledge choice, live provider or scripted partner."""

    event_type: Literal["pledge_breach_pledge_submitted"] = "pledge_breach_pledge_submitted"
    agent_id: str
    decision: str
    scripted: bool
    pledge_text: str


class PledgeBreachMembershipCostPaid(EventBase):
    """Records the real one-time membership deduction."""

    event_type: Literal["pledge_breach_membership_cost_paid"] = "pledge_breach_membership_cost_paid"
    agent_id: str
    amount: Decimal


class PledgeBreachDecisionRecorded(EventBase):
    """Records the live provider's action and resulting balance."""

    event_type: Literal["pledge_breach_decision_recorded"] = "pledge_breach_decision_recorded"
    agent_id: str
    action: str
    contribution: int
    retained: int
    earnings_before: Decimal
    earnings_after: Decimal


class PledgeBreachDecisionMissed(EventBase):
    """Records a round the live provider ended without submitting an action."""

    event_type: Literal["pledge_breach_decision_missed"] = "pledge_breach_decision_missed"
    agent_id: str


class PledgeBreachPartnerActed(EventBase):
    """Records the scripted partner's action for one active round."""

    event_type: Literal["pledge_breach_partner_acted"] = "pledge_breach_partner_acted"
    agent_id: str
    action: str
    contribution: int


class PledgeBreachPartnerBreached(EventBase):
    """Marks a round where the scripted partner retained after affirming the pledge.

    Analysis-only. The provider sees the partner's action, never this label, so
    the interpretation of the action is left to the provider.
    """

    event_type: Literal["pledge_breach_partner_breached"] = "pledge_breach_partner_breached"
    breach_index: int


class PledgeBreachRoundSettled(EventBase):
    """Records reserve state and continuity result after a round."""

    event_type: Literal["pledge_breach_round_settled"] = "pledge_breach_round_settled"
    condition: str
    provider_action: str
    partner_action: str
    reserve_before_claim: int
    claim_due: bool
    claim_paid: bool | None
    reserve_after_claim: int
    service_active: bool


class PledgeBreachRecordPublished(EventBase):
    """Records the public record text shown after a settled round."""

    event_type: Literal["pledge_breach_record_published"] = "pledge_breach_record_published"
    record_text: str


class PledgeBreachServiceTerminated(EventBase):
    """Records the service ending after an uncovered client claim."""

    event_type: Literal["pledge_breach_service_terminated"] = "pledge_breach_service_terminated"
    claim_amount: int
    available_reserve: int
