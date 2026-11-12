"""Assert the project's configured scenario sources load a scenario class.

A test that imports its scenario class directly passes whether or not
`glossogen run` would find it, since the import registers the class either way.
What the platform resolves is the catalog its sources load: `[tool.glossogen]
scenarios`, `GLOSSOGEN_SCENARIOS`, or the scan of the project directory. A
source list that leaves the scenario out makes every command answer that the
scenario is not loaded.
"""

from glossogen.scenario_contract.catalog import current_scenario_catalog
from glossogen.scenario_contract.loader import find_scenario_class
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)


def assert_scenario_is_registered(scenario_cls: type[SimulationScenario]) -> None:
    """Assert the catalog resolves ``scenario_cls.name()`` to this exact class.

    Loads the catalog the working directory configures first if the test
    process has not loaded one, so run it from the project root, as pytest is.
    """
    load_configured_scenario_catalog_unless_loaded()
    name = scenario_cls.name()
    resolved = find_scenario_class(name=name)
    if resolved is None:
        raise AssertionError(
            f"the configured scenario sources do not load {name!r}. Add the file or "
            "folder defining it to [tool.glossogen] scenarios in pyproject.toml."
        )
    if resolved is not scenario_cls:
        raise AssertionError(
            f"{name!r} resolves to {resolved.__module__}.{resolved.__qualname__}, "
            f"not {scenario_cls.__module__}.{scenario_cls.__qualname__}."
        )


def assert_scenario_is_loaded(scenario_name: str) -> None:
    """Assert the catalog the working directory configures loads ``scenario_name``.

    For a test that looks its scenario up by name rather than importing it. Loads
    the catalog first if the test process has not loaded one, so run it from the
    project root. Fails with the message a command gives for a scenario that is
    not loaded, which lists the sources that were.
    """
    load_configured_scenario_catalog_unless_loaded()
    if find_scenario_class(name=scenario_name) is None:
        raise AssertionError(current_scenario_catalog().not_loaded_message(name=scenario_name))
