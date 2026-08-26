"""Typed target-routing events for the Benjamin shadow-component world."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminShadowOutcomeRouted(EventBase):
    """Record the terminal destination of the frozen focal repair state."""

    event_type: Literal["benjamin_shadow_outcome_routed"] = "benjamin_shadow_outcome_routed"
    artifact_id: str
    destination_id: str
    destination_scope: Literal["local", "external"]
