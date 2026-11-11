"""The ``@scenario`` decorator and the process-wide record of the classes it registered.

Registration is a side effect of importing the module that defines a scenario.
What gets imported is decided by :mod:`glossogen.scenario_contract.catalog`, which
reads this record afterwards; nothing looks a scenario up here directly.
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TypeVar

from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.scenario_base import REGISTERED_NAME_ATTRIBUTE

ScenarioClassT = TypeVar("ScenarioClassT", bound=type[SimulationScenario])

_REGISTERED: dict[str, type[SimulationScenario]] = {}


class ScenarioNameTaken(Exception):
    """Raised when a second class registers under a name another class already holds."""


def scenario(name: str) -> Callable[[ScenarioClassT], ScenarioClassT]:
    """Register the decorated class as the scenario called ``name``.

    The class's ``name()`` returns ``name`` from then on, so run directories and
    the ``scenario_name`` a run records use it. A second class registering the same
    name raises :class:`ScenarioNameTaken` naming both modules. The same class
    defined again by re-importing its module replaces the first registration.
    """

    def register(scenario_cls: ScenarioClassT) -> ScenarioClassT:
        if not issubclass(scenario_cls, SimulationScenario):
            raise TypeError(
                f"@scenario(name={name!r}) decorates {scenario_cls.__module__}."
                f"{scenario_cls.__qualname__}, which is not a SimulationScenario subclass."
            )
        existing = _REGISTERED.get(name)
        if existing is not None and not _same_definition(first=existing, second=scenario_cls):
            raise ScenarioNameTaken(
                f"Scenario name {name!r} is registered twice: by "
                f"{existing.__qualname__} in module {existing.__module__} and by "
                f"{scenario_cls.__qualname__} in module {scenario_cls.__module__}. "
                "Rename one of them."
            )
        setattr(scenario_cls, REGISTERED_NAME_ATTRIBUTE, name)
        _REGISTERED[name] = scenario_cls
        return scenario_cls

    return register


def registered_scenarios() -> Mapping[str, type[SimulationScenario]]:
    """Return every class registered so far in this process, keyed by name, read-only."""
    return MappingProxyType(_REGISTERED)


def _same_definition(first: type[SimulationScenario], second: type[SimulationScenario]) -> bool:
    """Return whether two classes are one definition, imported twice.

    A module imported a second time (a reload, or a tree evicted from
    ``sys.modules`` and imported again) defines a new class object with the same
    module and qualified name. That is not a collision between two scenarios.
    """
    return first.__module__ == second.__module__ and first.__qualname__ == second.__qualname__
