"""Typed event schemas for the Benjamin help-desk world."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminHelpDeskSetupPublished(EventBase):
    """Records the assigned world factors and structural routes."""

    event_type: Literal["benjamin_help_desk_setup_published"] = "benjamin_help_desk_setup_published"
    arm: str
    observation: str
    moral_weight: str
    topology_routes: list[str]


class BenjaminHelpDeskSetupAcknowledged(EventBase):
    """Records setup receipt before the work phase."""

    event_type: Literal["benjamin_help_desk_setup_acknowledged"] = (
        "benjamin_help_desk_setup_acknowledged"
    )
    agent_id: str
    defaulted_after_timeout: bool


class BenjaminHelpDeskQueueInspected(EventBase):
    """Records deterministic revelation of the two eligible requests."""

    event_type: Literal["benjamin_help_desk_queue_inspected"] = "benjamin_help_desk_queue_inspected"
    agent_id: str
    request_ids: list[str]
    capacity_remaining: int


class BenjaminHelpDeskRequestResolved(EventBase):
    """Records one accepted costly request resolution."""

    event_type: Literal["benjamin_help_desk_request_resolved"] = (
        "benjamin_help_desk_request_resolved"
    )
    agent_id: str
    request_id: str
    action_cost: int
    capacity_remaining: int


class BenjaminHelpDeskActionRejected(EventBase):
    """Records one rejected help-desk action."""

    event_type: Literal["benjamin_help_desk_action_rejected"] = "benjamin_help_desk_action_rejected"
    agent_id: str
    action: str
    target_id: str
    reason: str


class BenjaminHelpDeskShiftCompleted(EventBase):
    """Records the mechanically derived focal endpoint."""

    event_type: Literal["benjamin_help_desk_shift_completed"] = "benjamin_help_desk_shift_completed"
    agent_id: str
    partner_request_completed: bool
    local_request_completed: bool
    partner_slot_honored: bool
    capacity_remaining: int
    completed_by_agent: bool


class BenjaminHelpDeskAuditCompleted(EventBase):
    """Records the observed-only post-shift allocation audit."""

    event_type: Literal["benjamin_help_desk_audit_completed"] = "benjamin_help_desk_audit_completed"
    target_disposition_id: str
    partner_slot_honored: bool
    recipient_id: str
