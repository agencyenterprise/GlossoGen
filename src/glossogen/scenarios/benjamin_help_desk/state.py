"""Structured state-transition results for the Benjamin help desk."""

from typing import NamedTuple


class ActionResult(NamedTuple):
    """Result of one help-desk action."""

    accepted: bool
    message: str
    cost: int
    capacity_remaining: int


class ShiftResult(NamedTuple):
    """Mechanically derived terminal support-allocation state."""

    completed: bool
    partner_request_completed: bool
    local_request_completed: bool
    partner_slot_honored: bool
    capacity_remaining: int


class AuditResult(NamedTuple):
    """Observed-only post-shift review result."""

    partner_slot_honored: bool
    recipient_id: str
