"""In-memory state records for shared-reserve commitment trajectories."""

from decimal import Decimal
from typing import NamedTuple


class ProviderState(NamedTuple):
    """One provider's balance and voluntary membership choice."""

    earnings: Decimal
    pledge_decision: str | None
    entry_cost_paid: Decimal


class ReserveDecision(NamedTuple):
    """One provider's contribution decision in an active round."""

    agent_id: str
    action: str
    contribution: int
    retained: int
    earnings_before: Decimal
    earnings_after: Decimal


class RoundSettlement(NamedTuple):
    """Public result of one round after both decisions are recorded."""

    round_number: int
    missing_provider_ids: tuple[str, ...]
    reserve_before_claim: int
    client_claim_due: bool
    client_claim_paid: bool | None
    reserve_after_claim: int
    service_active: bool
