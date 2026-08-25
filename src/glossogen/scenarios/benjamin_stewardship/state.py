"""Structured world-transition results for Benjamin stewardship."""

from typing import NamedTuple


class ActionResult(NamedTuple):
    """Result of one private-workspace action."""

    accepted: bool
    message: str
    cost: int
    budget_remaining: int


class ReleaseResult(NamedTuple):
    """Mechanically derived final state at release completion."""

    completed: bool
    focal_fixed: bool
    transfer_fixed: bool
    optional_ticket_delivered: bool
    budget_remaining: int


class AuditResult(NamedTuple):
    """Post-decision result sent through the observed audit route."""

    focal_issue_found: bool
    transfer_issue_found: bool
    recipient_id: str
