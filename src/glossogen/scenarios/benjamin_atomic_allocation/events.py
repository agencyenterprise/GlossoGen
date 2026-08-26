"""Typed routing event for the atomic-allocation instrument."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminAtomicAllocationStatusRouted(EventBase):
    """Record every work surface receiving the frozen focal status."""

    event_type: Literal["benjamin_atomic_allocation_status_routed"] = (
        "benjamin_atomic_allocation_status_routed"
    )
    artifact_id: str
    destination_ids: list[str]
    external_recipient_ids: list[str]
