"""In-memory records for joint client-commitment decisions."""

from typing import NamedTuple


class ProviderState(NamedTuple):
    """Cumulative earnings, commitment status, and covenant bond state."""

    earnings: int
    pledge_decision: str | None
    bond_posted: int
    bond_forfeited: int
    membership_in_good_standing: bool


class PublicRegistryEntry(NamedTuple):
    """One provider's institution-visible status without private action details."""

    agent_id: str
    membership_status: str
    pledge_status: str
    standing_status: str


class ReserveDecision(NamedTuple):
    """One provider's private remittance and public report."""

    agent_id: str
    actual_action: str
    public_attestation: str
    reserve_remitted: int
    reserve_retained: int
    earnings_before: int
    earnings_after: int


class RoundOutcome(NamedTuple):
    """One settled shared-client result."""

    round_number: int
    completed: bool
    missing_provider_ids: tuple[str, ...]
    safe_client_outcome: bool | None
    audit_selected: bool
