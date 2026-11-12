"""Test helpers that put a hand-built scenario catalog in place of the process catalog."""

from collections.abc import Generator
from contextlib import contextmanager

import pytest

from glossogen.run_storage.event_parsing import install_scenario_event_types
from glossogen.scenario_contract import catalog as catalog_module
from glossogen.scenario_contract.catalog import (
    ScenarioCatalog,
    ScenarioCatalogNotLoaded,
    current_scenario_catalog,
)
from glossogen.scenario_contract.protocol import SimulationScenario


def catalog_including(
    base: ScenarioCatalog, name: str, scenario_cls: type[SimulationScenario]
) -> ScenarioCatalog:
    """Return a copy of ``base`` with ``scenario_cls`` under ``name``, replacing any.

    Skips the name and shared-directory checks the catalog applies at load.
    """
    scenarios = dict(base.classes())
    scenarios[name] = scenario_cls
    return ScenarioCatalog(scenarios=scenarios, loaded_sources=base.loaded_sources)


def _current_or_none() -> ScenarioCatalog | None:
    """Return the process's current catalog, or None when none has been loaded."""
    try:
        return current_scenario_catalog()
    except ScenarioCatalogNotLoaded:
        return None


@contextmanager
def scenario_catalog_installed(catalog: ScenarioCatalog) -> Generator[None]:
    """Make ``catalog`` the current catalog and the run readers' lookup, then restore both."""
    previous = _current_or_none()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(catalog_module, "_current", catalog)
        install_scenario_event_types(lookup=catalog.event_types_of)
        try:
            yield
        finally:
            if previous is None:
                install_scenario_event_types(lookup=None)
            else:
                install_scenario_event_types(lookup=previous.event_types_of)
