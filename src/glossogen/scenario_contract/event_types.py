"""The event types a scenario's runs may log.

A scenario declares its own event types through ``event_types()``. A run logs
only the platform's events and its own scenario's, so these are the types its
event logger accepts.
"""

from glossogen.models.event import core_event_types
from glossogen.models.event_base import EventBase
from glossogen.scenario_contract.protocol import SimulationScenario


def loggable_event_types(scenario_cls: type[SimulationScenario]) -> frozenset[type[EventBase]]:
    """Return the event classes a run of this scenario may log: the platform's and its own."""
    return frozenset((*core_event_types(), *scenario_cls.event_types()))
