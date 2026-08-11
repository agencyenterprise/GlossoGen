"""Event schemas for shared-reserve commitment trajectories."""

from decimal import Decimal
from typing import Literal

from glossogen.models.event_base import EventBase


class SharedReserveSetupPublished(EventBase):
    """Records publication of the public group registry."""

    event_type: Literal["shared_reserve_setup_published"] = "shared_reserve_setup_published"
    condition: str
    members: list[str]


class SharedReservePledgeSubmitted(EventBase):
    """Records one provider's visible pledge decision."""

    event_type: Literal["shared_reserve_pledge_submitted"] = "shared_reserve_pledge_submitted"
    agent_id: str
    decision: str
    pledge_text: str


class SharedReserveEntryCostPaid(EventBase):
    """Records a real one-time cost after pledge affirmation."""

    event_type: Literal["shared_reserve_entry_cost_paid"] = "shared_reserve_entry_cost_paid"
    agent_id: str
    amount: Decimal


class SharedReserveDecisionRecorded(EventBase):
    """Records a provider's contribution action and resulting balance."""

    event_type: Literal["shared_reserve_decision_recorded"] = "shared_reserve_decision_recorded"
    agent_id: str
    action: str
    contribution: int
    retained: int
    earnings_before: Decimal
    earnings_after: Decimal


class SharedReserveRoundSettled(EventBase):
    """Records reserve state and client-continuity result after a round."""

    event_type: Literal["shared_reserve_round_settled"] = "shared_reserve_round_settled"
    condition: str
    reserve_before_claim: int
    client_claim_due: bool
    client_claim_paid: bool | None
    reserve_after_claim: int
    service_active: bool


class SharedReserveLedgerPublished(EventBase):
    """Records the public ledger content shown after a settled round."""

    event_type: Literal["shared_reserve_ledger_published"] = "shared_reserve_ledger_published"
    ledger_text: str


class SharedReserveServiceTerminated(EventBase):
    """Records the common service ending after an uncovered client claim."""

    event_type: Literal["shared_reserve_service_terminated"] = "shared_reserve_service_terminated"
    round_number: int
    claim_amount: int
    available_reserve: int
