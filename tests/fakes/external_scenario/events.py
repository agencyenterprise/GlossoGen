"""The event type this fake external scenario contributes.

Imports only from ``glossogen.models.event_base``, which is the rule every
scenario's ``events`` module follows and the reason discovery can run while
``glossogen.models.event`` is still importing.
"""

from typing import Literal

from glossogen.models.event_base import EventBase


class ExternalScenarioProbed(EventBase):
    """Emitted by the fake external scenario. Exists to be discovered."""

    event_type: Literal["external_scenario_probed"] = "external_scenario_probed"
    detail: str
