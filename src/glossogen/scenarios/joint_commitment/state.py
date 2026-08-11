"""In-memory records for joint client-commitment decisions."""

from decimal import Decimal
from typing import NamedTuple


class ProviderState(NamedTuple):
    """Cumulative earnings, pledge state, entry cost, and legacy covenant-bond state."""

    earnings: Decimal
    pledge_decision: str | None
    entry_cost_paid: Decimal
    bond_posted: int
    bond_forfeited: int
    membership_in_good_standing: bool


class PublicRegistryEntry(NamedTuple):
    """One provider's institution-visible status without private action details."""

    agent_id: str
    membership_status: str
    pledge_status: str
    entry_cost_status: str
    standing_status: str


class ReserveDecision(NamedTuple):
    """One provider's remittance decision and ledger record."""

    agent_id: str
    actual_action: str
    public_attestation: str
    reserve_remitted: int
    reserve_retained: int
    earnings_before: Decimal
    earnings_after: Decimal


class RoundOutcome(NamedTuple):
    """One settled shared-client result."""

    round_number: int
    completed: bool
    missing_provider_ids: tuple[str, ...]
    safe_client_outcome: bool | None
    audit_selected: bool
