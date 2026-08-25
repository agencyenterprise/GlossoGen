"""Typed destination-routing events for the Benjamin release instrument."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminDeploymentSummaryRouted(EventBase):
    """Records the terminal destination selected by the assigned world."""

    event_type: Literal["benjamin_deployment_summary_routed"] = "benjamin_deployment_summary_routed"
    artifact_id: str
    destination_id: str
    destination_scope: Literal["local", "external"]
