"""Resolves scenario names to classes for every caller.

Every answer comes from the scenario catalog this process loaded
(:mod:`glossogen.scenario_contract.catalog`), and every lookup raises
:class:`~glossogen.scenario_contract.catalog.ScenarioCatalogNotLoaded` before it
is loaded.
"""

from glossogen.scenario_contract.catalog import current_scenario_catalog
from glossogen.scenario_contract.protocol import SimulationScenario


def available_scenario_names() -> list[str]:
    """Return every scenario name this process can run, sorted."""
    return current_scenario_catalog().names()


def find_scenario_class(name: str) -> type[SimulationScenario] | None:
    """Return the scenario class registered under ``name``, or None if there is none.

    For callers that treat a missing scenario as an ordinary outcome and degrade:
    run detail, the run list and export, reading a run whose scenario this process
    has not loaded. Use :func:`get_scenario_class` where the caller asked for this
    scenario by name and wants to be told why it cannot have it.
    """
    return current_scenario_catalog().find(name=name)


def get_scenario_class(name: str) -> type[SimulationScenario]:
    """Return the scenario class registered under ``name``.

    Raises :class:`~glossogen.scenario_contract.catalog.ScenarioNotLoaded`, a
    ``ValueError``, naming the sources this process loaded and how to add one.
    """
    return current_scenario_catalog().get(name=name)


def iter_scenario_classes() -> list[tuple[str, type[SimulationScenario]]]:
    """Return every loaded scenario as ``(name, class)``, ordered by name."""
    return current_scenario_catalog().classes()
