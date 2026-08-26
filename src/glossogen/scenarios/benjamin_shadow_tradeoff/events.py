"""Typed focal-status routing events for the shadow-tradeoff world."""

from typing import Literal

from glossogen.models.event_base import EventBase


class BenjaminTradeoffOutcomeRouted(EventBase):
    """Record every work surface receiving the frozen focal repair status."""

    event_type: Literal["benjamin_tradeoff_outcome_routed"] = (
        "benjamin_tradeoff_outcome_routed"
    )
    artifact_id: str
    destination_ids: list[str]
    external_recipient_ids: list[str]
