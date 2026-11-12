"""Assert the project's configured scenario sources load a scenario class.

A test that imports its scenario class directly passes whether or not
`glossogen run` would find it, since the import registers the class either way.
What the platform resolves is the catalog its sources load: `[tool.glossogen]
scenarios`, `GLOSSOGEN_SCENARIOS`, or the scan of the project directory. A
source list that leaves the scenario out makes every command answer that the
scenario is not loaded.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from glossogen.scenario_contract.catalog import current_scenario_catalog
from glossogen.scenario_contract.loader import find_scenario_class
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.registration import same_scenario_definition
from glossogen.scenario_contract.scenario_sources import (
    SCENARIOS_ENV_VAR,
    find_project,
    load_configured_scenario_catalog_unless_loaded,
)


def assert_scenario_is_registered(scenario_cls: type[SimulationScenario]) -> None:
    """Assert the catalog resolves ``scenario_cls.name()`` to this class.

    The class the catalog holds counts as this one when it is the same
    definition: the same file imported under another module name, as a test that
    imports its scenario by a shorter name than the project scan does. Loads the
    catalog the working directory configures first if the test process has not
    loaded one, so run it from the project root, as pytest is.
    """
    load_configured_scenario_catalog_unless_loaded()
    name = scenario_cls.name()
    resolved = find_scenario_class(name=name)
    if resolved is None:
        raise AssertionError(
            f"the configured scenario sources do not load {name!r}. Add the file or "
            "folder defining it to [tool.glossogen] scenarios in pyproject.toml."
            f"{working_directory_hint(working_dir=Path.cwd(), environ=os.environ)}"
        )
    if not same_scenario_definition(first=resolved, second=scenario_cls):
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
        raise AssertionError(
            current_scenario_catalog().not_loaded_message(name=scenario_name)
            + working_directory_hint(working_dir=Path.cwd(), environ=os.environ)
        )


def working_directory_hint(working_dir: Path, environ: Mapping[str, str]) -> str:
    """Return a hint for pytest started outside any project, or ``""`` otherwise.

    With no ``pyproject.toml`` at or above ``working_dir`` and no
    ``GLOSSOGEN_SCENARIOS``, the scan of the project directory covers
    ``working_dir`` itself. Run from inside a scenario's
    folder, that scan is the folder, which does not load the scenario the way
    the project root does.
    """
    if SCENARIOS_ENV_VAR in environ:
        return ""
    if find_project(working_dir=working_dir).pyproject is not None:
        return ""
    return (
        f"\nNo pyproject.toml is at or above {working_dir}, so the scan covered that "
        "directory alone. Run pytest from the project root, or name the scenario's "
        "folder in GLOSSOGEN_SCENARIOS or [tool.glossogen] scenarios."
    )
