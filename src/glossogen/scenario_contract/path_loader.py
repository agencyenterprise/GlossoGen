"""Load the scenarios a file or directory registers, for ``glossogen validate <path>``.

The path becomes one more source on top of the ones this process already loaded,
and the catalog is loaded again with it, so the scenarios it registers resolve
by name the way they will once the path is configured as a source. Importing
leaves the path's modules in ``sys.modules`` and its import root on ``sys.path``,
so one process loads one path. That is enough for a command that checks and exits.
"""

import sys
import tomllib
from pathlib import Path
from typing import Any, NamedTuple, cast

from glossogen.scenario_contract.catalog import (
    ScenarioCatalogError,
    current_scenario_catalog,
    load_scenario_catalog,
)
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.scenario_sources import find_project, path_source


class PathLoadedScenario(NamedTuple):
    """A scenario registered by a path, and the project around it.

    ``module_dir`` is the directory holding the module that defines the class,
    which is where its prompts and presets live. ``package_name`` is the dotted
    package that module belongs to, the key setuptools' ``package-data`` uses for
    that directory, or "" for a top-level module. ``pyproject`` is the nearest
    ``pyproject.toml`` at or above the path, parsed, or None when there is none.
    """

    scenario_cls: type[SimulationScenario]
    name: str
    module_dir: Path
    package_name: str
    project_dir: Path
    pyproject: dict[str, Any] | None


class ScenarioPathError(Exception):
    """Raised when a path cannot be loaded, carrying the reason for a user."""


def load_scenarios_from_path(path: Path) -> list[PathLoadedScenario]:
    """Import ``path`` as one more scenario source and return what it registered.

    Raises :class:`ScenarioPathError` when the path does not exist, is a file
    that is not ``.py``, fails to import, or registers no scenario.
    """
    try:
        source = path_source(path=path, working_dir=Path.cwd(), origin="validate")
        widened = load_scenario_catalog(sources=(*current_scenario_catalog().sources, source))
    except ScenarioCatalogError as exc:
        raise ScenarioPathError(str(exc)) from exc
    names = widened.loaded_sources[-1].scenario_names
    if not names:
        raise ScenarioPathError(
            f"{path} registers no scenario. Decorate the scenario class with "
            "@scenario(name=...) from glossogen.scenario_contract.registration."
        )
    project = find_project(working_dir=_directory_of(path=path.resolve()))
    pyproject = _read_pyproject(path=project.pyproject)
    loaded: list[PathLoadedScenario] = []
    for name in names:
        scenario_cls = widened.get(name=name)
        module_file = Path(cast(str, sys.modules[scenario_cls.__module__].__file__))
        package_name = scenario_cls.__module__
        if module_file.name != "__init__.py":
            package_name = scenario_cls.__module__.rpartition(".")[0]
        loaded.append(
            PathLoadedScenario(
                scenario_cls=scenario_cls,
                name=name,
                module_dir=module_file.parent,
                package_name=package_name,
                project_dir=project.root,
                pyproject=pyproject,
            )
        )
    return loaded


def _directory_of(path: Path) -> Path:
    """Return ``path`` if it is a directory, else the directory holding it."""
    if path.is_dir():
        return path
    return path.parent


def _read_pyproject(path: Path | None) -> dict[str, Any] | None:
    """Parse the project's ``pyproject.toml``, or return None when there is none."""
    if path is None:
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ScenarioPathError(f"{path} is not valid TOML: {exc}") from exc


def table_at(document: dict[str, Any], path: tuple[str, ...]) -> dict[str, object]:
    """Return the table at a dotted path in a parsed TOML document, or an empty one.

    Anything along the path that is present but not a table reads as absent, so
    a caller reports what it wanted rather than a ``TypeError`` from a lookup.
    """
    current: object = document
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = cast(dict[str, object], current).get(key)
    if not isinstance(current, dict):
        return {}
    return cast(dict[str, object], current)
