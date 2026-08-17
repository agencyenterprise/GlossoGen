"""Load a scenario from a source tree, before anything has been installed.

Every other way into a scenario goes through installed entry-point metadata, so
the loop for an author writing one is edit, reinstall, check. That is slow, and
it hides the failures that exist only before installation: an entry-point group
naming a contract version this platform does not read, ``package-data`` that
omits the prompts, a name a built-in already holds.

So this reads the declaration out of the tree's own ``pyproject.toml`` and builds
an :class:`~importlib.metadata.EntryPoint` from it by hand. That is what lets the
rest be reuse rather than a second implementation: the synthetic entry point
imports through ``load()`` like any other, and
:func:`glossogen.scenario_loader.check_entry_point_declaration` then applies the
same two rules an installed scenario is held to.

Importing is not free of consequence. The package's root goes on ``sys.path`` and
its modules stay in ``sys.modules`` afterwards, so one process loads one tree.
That is enough for a command that checks a scenario and exits.
"""

import re
import sys
import tomllib
from collections.abc import Generator
from contextlib import contextmanager
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any, NamedTuple, cast

from glossogen.plugin_entry_points import package_of
from glossogen.scenario_api import SCENARIO_API_VERSION
from glossogen.scenario_entry_points import (
    SCENARIO_ENTRY_POINT_GROUP,
    SCENARIO_ENTRY_POINT_GROUP_PREFIX,
)
from glossogen.scenario_loader import check_entry_point_declaration
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY

PYPROJECT_NAME = "pyproject.toml"

_VERSIONED_GROUP = re.compile(rf"^{re.escape(SCENARIO_ENTRY_POINT_GROUP_PREFIX)}\d+$")

# The group an author most plausibly types by mistake, the prefix without its
# version. Nothing reads it, so a declaration there would vanish unexplained.
_UNVERSIONED_GROUP = SCENARIO_ENTRY_POINT_GROUP_PREFIX.removesuffix(".v")


class PathLoadedScenario(NamedTuple):
    """A scenario imported from a tree, and what its declaration said.

    ``package_dir`` is the distribution root, the directory holding
    ``pyproject.toml``. ``module_dir`` is the importable package inside it, which
    is where the prompts, the presets and ``events.py`` live. The two differ
    whenever the distribution is named with hyphens, which the scaffold does.
    """

    scenario_cls: type[SimulationScenario]
    entry_point: EntryPoint
    entry_point_name: str
    entry_point_group: str
    package_dir: Path
    module_dir: Path
    pyproject: dict[str, Any]


class ScenarioPathError(Exception):
    """Raised when a tree cannot be loaded, carrying the reason for a user."""


def load_scenario_from_path(package_dir: Path) -> PathLoadedScenario:
    """Import the scenario a tree declares, and check its declaration.

    Raises :class:`ScenarioPathError` for anything that stops the class being
    reached: no ``pyproject.toml``, no scenario entry point, a value that does
    not import, a class that is not a ``SimulationScenario``, or a declaration
    that disagrees with the class it names.

    A group naming another contract version is deliberately not refused here.
    The class still imports, and refusing would report one problem where the
    author wants every one their scenario has; the version is reported as a
    failed check instead.
    """
    resolved = package_dir.resolve()
    pyproject = _read_pyproject(package_dir=resolved)
    declaration = _find_scenario_declaration(pyproject=pyproject, package_dir=resolved)
    entry_point = EntryPoint(
        name=declaration.name, value=declaration.value, group=declaration.group
    )

    with _path_prepended(root=resolved):
        _evict_modules_loaded_elsewhere(package=package_of(entry_point=entry_point), root=resolved)
        try:
            loaded = entry_point.load()
        except Exception as exc:
            raise ScenarioPathError(
                f"The scenario {declaration.name!r} is declared as {declaration.value!r} "
                f"but does not import from {resolved}: {type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(loaded, type) or not issubclass(loaded, SimulationScenario):
            raise ScenarioPathError(
                f"{declaration.value!r} does not name a SimulationScenario subclass."
            )

        try:
            check_entry_point_declaration(
                name=declaration.name, entry_point=entry_point, loaded=loaded
            )
        except ValueError as exc:
            raise ScenarioPathError(str(exc)) from exc

    return PathLoadedScenario(
        scenario_cls=loaded,
        entry_point=entry_point,
        entry_point_name=declaration.name,
        entry_point_group=declaration.group,
        package_dir=resolved,
        module_dir=resolved / package_of(entry_point=entry_point),
        pyproject=pyproject,
    )


class _Declaration(NamedTuple):
    """One scenario entry point, as written in a tree's ``pyproject.toml``."""

    group: str
    name: str
    value: str


def _read_pyproject(package_dir: Path) -> dict[str, Any]:
    """Parse the tree's ``pyproject.toml``, or say why it could not be read."""
    if not package_dir.is_dir():
        raise ScenarioPathError(f"{package_dir} is not a directory.")
    path = package_dir / PYPROJECT_NAME
    if not path.is_file():
        raise ScenarioPathError(
            f"No {PYPROJECT_NAME} in {package_dir}. Point this at the directory holding "
            "it, which is the one `glossogen new-scenario` created rather than the "
            "package inside it."
        )
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ScenarioPathError(f"{path} is not valid TOML: {exc}") from exc


def _find_scenario_declaration(pyproject: dict[str, Any], package_dir: Path) -> _Declaration:
    """Return the single scenario entry point the tree declares.

    Every versioned group is searched rather than only the one this platform
    reads, so a scenario written against another contract version still loads and
    has its version reported as a check. A declaration under the unversioned
    group is named in the error, since nothing reads it and the omission is one
    character.
    """
    groups = _entry_point_groups(pyproject=pyproject)
    found = [
        _Declaration(group=group, name=name, value=value)
        for group, entries in groups.items()
        if _VERSIONED_GROUP.match(group)
        for name, value in entries.items()
    ]
    if len(found) > 1:
        listed = ", ".join(f"{one.group}:{one.name}" for one in sorted(found))
        raise ScenarioPathError(
            f"{package_dir} declares more than one scenario ({listed}). Check them one "
            "at a time by pointing this at a tree that declares one."
        )
    if found:
        return found[0]

    unversioned = groups.get(_UNVERSIONED_GROUP, {})
    if unversioned:
        raise ScenarioPathError(
            f"{package_dir} declares {', '.join(sorted(unversioned))} under "
            f"'{_UNVERSIONED_GROUP}', which nothing reads. The group carries the contract "
            f"version: rename it to '{SCENARIO_ENTRY_POINT_GROUP}'."
        )
    raise ScenarioPathError(
        f"{package_dir}/{PYPROJECT_NAME} declares no scenario. Add an entry point under "
        f'[project.entry-points."{SCENARIO_ENTRY_POINT_GROUP}"] whose key is what the '
        "scenario's name() returns."
    )


def _entry_point_groups(pyproject: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return ``[project.entry-points]`` as group name to name-value mapping.

    Shapes that are present but not the expected tables are treated as absent
    rather than raising, so a malformed file reports the missing declaration
    instead of a ``TypeError`` from the middle of a lookup.
    """
    declared = table_at(document=pyproject, path=("project", "entry-points"))
    groups: dict[str, dict[str, str]] = {}
    for group, entries in declared.items():
        if not isinstance(entries, dict):
            continue
        entry_table = cast(dict[str, object], entries)
        groups[group] = {
            name: value for name, value in entry_table.items() if isinstance(value, str)
        }
    return groups


def table_at(document: dict[str, Any], path: tuple[str, ...]) -> dict[str, object]:
    """Return the table at a dotted path in a parsed TOML document, or an empty one.

    Shared with the package checks, which read ``tool.setuptools`` tables out of
    the same document. Anything along the path that is present but not a table
    reads as absent, so a caller gets to report what it wanted rather than a
    ``TypeError`` raised inside a lookup.
    """
    current: object = document
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = cast(dict[str, object], current).get(key)
    if not isinstance(current, dict):
        return {}
    return cast(dict[str, object], current)


def _evict_modules_loaded_elsewhere(package: str, root: Path) -> None:
    """Drop an already-imported scenario package that came from another tree.

    ``import`` answers from ``sys.modules`` before it consults ``sys.path``, so a
    second tree declaring the same package name would hand back the first tree's
    class and every check would then describe a scenario the caller did not name.
    A wrong answer is worse than a refusal, and this one is invisible: the name
    matches, the class is real, and only the file it came from is different.

    Modules already loaded from inside ``root`` are left alone, so the ordinary
    case of validating a tree that is also installed as editable does not import
    it twice.
    """
    prefix = f"{package}."
    for name in [name for name in sys.modules if name == package or name.startswith(prefix)]:
        existing = sys.modules[name]
        origin = getattr(existing, "__file__", None)
        if origin is not None and root in Path(origin).resolve().parents:
            continue
        del sys.modules[name]


@contextmanager
def _path_prepended(root: Path) -> Generator[None]:
    """Put ``root`` first on ``sys.path`` for the duration of the block.

    Removed again afterwards so a caller that loads a tree does not change how
    every later import in the process resolves. What the block imported stays in
    ``sys.modules`` regardless, which is why one process loads one tree.
    """
    entry = str(root)
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        if entry in sys.path:
            sys.path.remove(entry)


@contextmanager
def registered_for_checks(loaded: PathLoadedScenario) -> Generator[None]:
    """Put a path-loaded scenario in the registry for the duration of the block.

    Some checks resolve a scenario by name rather than holding the class, because
    they are checking that a name-based caller agrees with it. Those callers read
    the registry and installed metadata, and a tree that has not been installed is
    in neither, so the platform failing to find it reads as the scenario having
    declared something wrong: `the API agrees on primary channels` resolves an
    empty list and reports a disagreement against a scenario that is fine.

    Registering makes the name resolve the way it will once the package is
    installed, which is the condition every check was written against. Run the
    package checks before entering this, since the collision check has to see the
    registry as it really is.
    """
    previous = SCENARIO_REGISTRY.get(loaded.entry_point_name)
    SCENARIO_REGISTRY[loaded.entry_point_name] = loaded.scenario_cls
    try:
        yield
    finally:
        if previous is None:
            SCENARIO_REGISTRY.pop(loaded.entry_point_name, None)
        else:
            SCENARIO_REGISTRY[loaded.entry_point_name] = previous


def declared_contract_version(group: str) -> int | None:
    """Return the contract version a group names, or None if it names none."""
    if not _VERSIONED_GROUP.match(group):
        return None
    return int(group.removeprefix(SCENARIO_ENTRY_POINT_GROUP_PREFIX))


def platform_contract_version() -> int:
    """Return the contract version this platform reads, for a check to compare."""
    return SCENARIO_API_VERSION
