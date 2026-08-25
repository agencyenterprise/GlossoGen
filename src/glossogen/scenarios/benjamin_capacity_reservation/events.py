"""Typed event schemas for the Benjamin capacity-reservation world."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminCapacitySetupPublished(EventBase):
    """Record assigned factors and structural routes."""

    event_type: Literal["benjamin_capacity_setup_published"] = "benjamin_capacity_setup_published"
    arm: str
    observation: str
    moral_weight: str
    topology_routes: list[str]


class BenjaminCapacitySetupAcknowledged(EventBase):
    """Record setup receipt before private work."""

    event_type: Literal["benjamin_capacity_setup_acknowledged"] = (
        "benjamin_capacity_setup_acknowledged"
    )
    agent_id: str
    defaulted_after_timeout: bool


class BenjaminCapacityOptionsInspected(EventBase):
    """Record deterministic revelation of the two allocation branches."""

    event_type: Literal["benjamin_capacity_options_inspected"] = (
        "benjamin_capacity_options_inspected"
    )
    agent_id: str
    allocation_ids: list[str]
    capacity_remaining: int


class BenjaminCapacityAllocated(EventBase):
    """Record one accepted private capacity allocation."""

    event_type: Literal["benjamin_capacity_allocated"] = "benjamin_capacity_allocated"
    agent_id: str
    allocation_id: str
    action_cost: int
    capacity_remaining: int


class BenjaminCapacityActionRejected(EventBase):
    """Record one rejected capacity action."""

    event_type: Literal["benjamin_capacity_action_rejected"] = "benjamin_capacity_action_rejected"
    agent_id: str
    action: str
    target_id: str
    reason: str


class BenjaminCapacityShiftCompleted(EventBase):
    """Record the mechanically derived focal endpoint."""

    event_type: Literal["benjamin_capacity_shift_completed"] = "benjamin_capacity_shift_completed"
    agent_id: str
    allocation_id: str | None
    partner_capacity_reserved: bool | None
    capacity_remaining: int
    completed_by_agent: bool


class BenjaminCapacityAuditCompleted(EventBase):
    """Record the observed-only post-shift capacity audit."""

    event_type: Literal["benjamin_capacity_audit_completed"] = "benjamin_capacity_audit_completed"
    target_allocation_id: str
    partner_capacity_reserved: bool
    recipient_id: str
