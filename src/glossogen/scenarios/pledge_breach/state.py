"""In-memory state records for pledge-breach trajectories."""

from decimal import Decimal
from typing import NamedTuple


class ProviderState(NamedTuple):
    """The live provider's balance and membership choices."""

    earnings: Decimal
    pledge_decision: str | None
    membership_cost_paid: Decimal


class RoundActions(NamedTuple):
    """Both parties' actions in one settled round."""

    round_number: int
    provider_action: str
    partner_action: str
    provider_contribution: int
    partner_contribution: int
    partner_breached: bool


class RoundSettlement(NamedTuple):
    """Public result of one settled round."""

    round_number: int
    actions: RoundActions
    reserve_before_claim: int
    claim_due: bool
    claim_paid: bool | None
    reserve_after_claim: int
    service_active: bool
