"""Typed routing event for the private-allocation instrument."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminPrivateAllocationStatusRouted(EventBase):
    """Record every work surface receiving the frozen focal status."""

    event_type: Literal["benjamin_private_allocation_status_routed"] = (
        "benjamin_private_allocation_status_routed"
    )
    artifact_id: str
    destination_ids: list[str]
    external_recipient_ids: list[str]
