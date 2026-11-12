"""The event type this fake external scenario contributes.

A run is parsed with the event types its scenario returns from
``event_types()``.
"""

from typing import Literal

from glossogen.models.event_base import EventBase


class ExternalScenarioProbed(EventBase):
    """Emitted by the fake external scenario. Exists to be discovered."""

    event_type: Literal["external_scenario_probed"] = "external_scenario_probed"
    detail: str
