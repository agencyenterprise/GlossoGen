"""The ``@scenario`` decorator and the process-wide record of the classes it registered.

Registration is a side effect of importing the module that defines a scenario.
What gets imported is decided by :mod:`glossogen.scenario_contract.catalog`, which
reads this record afterwards; nothing looks a scenario up here directly.
"""

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.scenario_base import REGISTERED_NAME_ATTRIBUTE

ScenarioClassT = TypeVar("ScenarioClassT", bound=type[SimulationScenario])

_REGISTERED: dict[str, type[SimulationScenario]] = {}

# The resolved file each registered class was defined in, read while its module
# was being executed, so it is known even after the module leaves sys.modules.
_DEFINING_FILES: dict[type[SimulationScenario], Path | None] = {}


class ScenarioNameTaken(Exception):
    """Raised when a second class registers under a name another class already holds."""


def scenario(name: str) -> Callable[[ScenarioClassT], ScenarioClassT]:
    """Register the decorated class as the scenario called ``name``.

    The class's ``name()`` returns ``name`` from then on, so run directories and
    the ``scenario_name`` a run records use it. A second class registering the same
    name raises :class:`ScenarioNameTaken` naming both modules. The same class
    defined again, by re-importing its module or by importing its file under a
    second module name, replaces the first registration.
    """

    def register(scenario_cls: ScenarioClassT) -> ScenarioClassT:
        if not issubclass(scenario_cls, SimulationScenario):
            raise TypeError(
                f"@scenario(name={name!r}) decorates {scenario_cls.__module__}."
                f"{scenario_cls.__qualname__}, which is not a SimulationScenario subclass."
            )
        _DEFINING_FILES[scenario_cls] = _module_file(module_name=scenario_cls.__module__)
        existing = _REGISTERED.get(name)
        if existing is not None and not same_scenario_definition(
            first=existing, second=scenario_cls
        ):
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


def scenario_defining_file(scenario_cls: type[SimulationScenario]) -> Path | None:
    """Return the resolved file ``scenario_cls`` was defined in, or None if unknown.

    Known for every class ``@scenario`` registered, from the module it was
    executing at the time; otherwise read from ``sys.modules``.
    """
    if scenario_cls in _DEFINING_FILES:
        return _DEFINING_FILES[scenario_cls]
    return _module_file(module_name=scenario_cls.__module__)


def same_scenario_definition(
    first: type[SimulationScenario], second: type[SimulationScenario]
) -> bool:
    """Return whether two classes are one definition, imported twice.

    A module imported a second time (a reload, or a tree evicted from
    ``sys.modules`` and imported again) defines a new class object with the same
    module and qualified name. One file imported under two module names, such as
    ``src.pack.mod`` by the project scan and ``pack.mod`` by the pack's own tests,
    defines a new class object with the same file and qualified name. Neither is a
    collision between two scenarios.
    """
    if first.__qualname__ != second.__qualname__:
        return False
    if first.__module__ == second.__module__:
        return True
    first_file = scenario_defining_file(scenario_cls=first)
    return first_file is not None and first_file == scenario_defining_file(scenario_cls=second)


def _module_file(module_name: str) -> Path | None:
    """Return the resolved file of a module in ``sys.modules``, or None."""
    module = sys.modules.get(module_name)
    location = getattr(module, "__file__", None)
    if location is None:
        return None
    return Path(location).resolve()
