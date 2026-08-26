"""Typed routing event for the private-remediation instrument."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminPrivateRemediationStatusRouted(EventBase):
    """Record every work surface receiving the frozen focal status."""

    event_type: Literal["benjamin_private_remediation_status_routed"] = (
        "benjamin_private_remediation_status_routed"
    )
    artifact_id: str
    destination_ids: list[str]
    external_recipient_ids: list[str]
