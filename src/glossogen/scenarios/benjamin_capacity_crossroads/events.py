"""Typed endpoint and routing events for capacity crossroads."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminCapacityCrossroadsCompleted(EventBase):
    """Record the complete atomic plan and mechanically derived outcomes."""

    event_type: Literal["benjamin_capacity_crossroads_completed"] = (
        "benjamin_capacity_crossroads_completed"
    )
    agent_id: str
    selected_candidate_ids: list[str]
    focal_fixed: bool
    transfer_fixed: bool
    neutral_selected: bool
    continuity_selected: bool
    budget_remaining: int
    completed_by_agent: bool


class BenjaminCapacityCrossroadsStatusRouted(EventBase):
    """Record every in-world surface receiving the focal selection status."""

    event_type: Literal["benjamin_capacity_crossroads_status_routed"] = (
        "benjamin_capacity_crossroads_status_routed"
    )
    artifact_id: str
    destination_ids: list[str]
    external_recipient_ids: list[str]
