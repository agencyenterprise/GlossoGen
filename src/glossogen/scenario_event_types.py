"""The event types one scenario's ``events`` module defines, and a parser for its runs.

The module-level parser in ``glossogen.models.event`` was built while that module
was importing, so it cannot see a scenario loaded from a path afterwards. A run
logs only the platform's events and its own scenario's, so a parser over exactly
those reads any run, whichever way its scenario was loaded.
"""

import importlib
import importlib.util

from pydantic import TypeAdapter

from glossogen.models.event import core_event_types, parser_for
from glossogen.models.event_base import EventBase
from glossogen.scenario_protocol import SimulationScenario


def events_module_name(scenario_cls: type[SimulationScenario]) -> str | None:
    """Return the dotted name of the scenario's ``events`` module, or None.

    Asked of the scenario module's own import spec. ``parent`` is the value Python
    resolves a relative import against, so it answers for a class in a
    ``scenario`` submodule and for one defined in the package's ``__init__``.
    None when the class is in a top-level module belonging to no package.
    """
    spec = importlib.import_module(scenario_cls.__module__).__spec__
    if spec is None or not spec.parent:
        return None
    return f"{spec.parent}.events"


def scenario_event_types(scenario_cls: type[SimulationScenario]) -> tuple[type[EventBase], ...]:
    """Return the event types the scenario's ``events`` module defines, importing it.

    A scenario with no ``events`` module defines none.
    """
    name = events_module_name(scenario_cls=scenario_cls)
    if name is None or importlib.util.find_spec(name) is None:
        return ()
    module = importlib.import_module(name)
    return tuple(
        attribute
        for attribute in vars(module).values()
        if isinstance(attribute, type)
        and issubclass(attribute, EventBase)
        and attribute is not EventBase
        and attribute.__module__ == module.__name__
    )


def run_event_parser(scenario_cls: type[SimulationScenario]) -> TypeAdapter[EventBase]:
    """Return a parser over the platform's events and this scenario's own."""
    return parser_for(
        event_types=(*core_event_types(), *scenario_event_types(scenario_cls=scenario_cls))
    )
