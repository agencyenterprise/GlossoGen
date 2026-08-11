"""In-memory records for repeated trust-game decisions."""

from typing import NamedTuple


class ParticipantState(NamedTuple):
    """Cumulative decision earnings and pledge response for one participant."""

    balance: float
    forfeiture_paid: float
    pledge_decision: str | None


class DecisionRecord(NamedTuple):
    """One trustor or trustee decision and its retained game earnings."""

    agent_id: str
    role: str
    amount: int
    maximum_amount: int
    gross_earnings: float
    forfeiture_paid: float
    net_earnings: float
    balance_before: float
    balance_after: float


class RoundOutcome(NamedTuple):
    """Counterbalanced paired decisions from one repeated round."""

    round_number: int
    completed: bool
    missing_participant_ids: tuple[str, ...]
    trustor_id: str
    trustee_id: str
    trust_sent: int | None
    reciprocity_returned: int | None
