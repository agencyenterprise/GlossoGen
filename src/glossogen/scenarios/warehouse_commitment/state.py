"""In-memory state records for repeated commitment decisions."""

from typing import NamedTuple


class ProviderState(NamedTuple):
    """Cumulative state for one provider."""

    balance: float
    forfeiture_paid: float
    pledge_decision: str | None


class ActionRecord(NamedTuple):
    """One private choice and its realized payoff."""

    agent_id: str
    action: str
    inspected: bool
    gross_payment: float
    forfeiture_paid: float
    net_payment: float
    balance_before: float
    balance_after: float


class RoundOutcome(NamedTuple):
    """Aggregate inspection outcome for one round."""

    round_number: int
    completed: bool
    inspected_provider_count: int
    shortcut_provider_count: int
    missing_provider_ids: tuple[str, ...]
    joint_inspection: bool
    actions_by_provider: dict[str, str]
