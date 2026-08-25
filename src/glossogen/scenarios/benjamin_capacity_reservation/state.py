"""Structured state-transition results for the capacity-reservation world."""

from typing import NamedTuple


class ActionResult(NamedTuple):
    """Result of one private capacity action."""

    accepted: bool
    message: str
    cost: int
    capacity_remaining: int


class ShiftResult(NamedTuple):
    """Mechanically derived terminal capacity-allocation state."""

    completed: bool
    allocation_id: str | None
    partner_capacity_reserved: bool | None
    capacity_remaining: int


class AuditResult(NamedTuple):
    """Observed-only post-shift review result."""

    partner_capacity_reserved: bool
    recipient_id: str


class RoleVisibleState(NamedTuple):
    """All non-Developer state that can be surfaced after shift close."""

    mara_batch_window_status: str
    team_a_window_status: str
    scheduler_pool_status: str
