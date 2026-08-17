"""Resolve one argument to a scenario, whether it names one or points at one.

`glossogen validate` takes either. A registered scenario is named
(`validate veyru`), and one that is not installed yet is pointed at
(`validate ./reactor-purge`). Both end up in the same contract checks, so which
form was used is a detail of finding the class rather than two different commands.

The two forms cannot be confused for each other. A scenario name is a Python
module name, an entry-point key and a directory name all at once, so it is a bare
lowercase identifier: it can hold no dot and no separator. Anything carrying one
is a path, and the only string that could read as either is a bare identifier that
is also a directory in the working directory. That resolves to the registered
scenario, which is the common reading, and says so, because the alternative is one
character away.
"""

import re
from pathlib import Path
from typing import NamedTuple

from glossogen.scenario_loader import available_scenario_names, get_scenario_class
from glossogen.scenario_path_loader import (
    PYPROJECT_NAME,
    PathLoadedScenario,
    ScenarioPathError,
    load_scenario_from_path,
)
from glossogen.scenario_protocol import SimulationScenario

# The same shape `new-scenario` enforces, because it is the same string: a module
# name, an entry-point key and a directory.
_SCENARIO_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class CheckTarget(NamedTuple):
    """A scenario to check, and how it was found.

    ``loaded`` is present only for the path form. The package checks read it, and
    they are the ones that stop meaning anything once the package is installed, so
    a scenario found by name has nothing for them to look at.
    """

    scenario_cls: type[SimulationScenario]
    label: str
    loaded: PathLoadedScenario | None
    notes: tuple[str, ...]


def resolve_check_target(target: str) -> CheckTarget:
    """Return the scenario ``target`` refers to.

    Raises :class:`ScenarioPathError` when it reads as a path that cannot be
    loaded, and ``ValueError`` when it reads as a name nothing answers to.
    """
    if _SCENARIO_NAME.match(target) and target in available_scenario_names():
        # `get_scenario_class` rather than `find_scenario_class`: the soft one answers
        # None both for a name nothing declares and for one that is declared and fails
        # to import, so resolving through it reported the second as the first, in a
        # message that then listed the very name it called unknown. Whether the name is
        # declared at all is settled above, by reading installed metadata, which
        # imports nothing.
        return CheckTarget(
            scenario_cls=get_scenario_class(name=target),
            label=target,
            loaded=None,
            notes=_shadowed_by_a_directory(target=target),
        )

    path = Path(target)
    if path.is_dir():
        loaded = load_scenario_from_path(package_dir=path)
        # The tree is named alongside the scenario, because the two can disagree: a
        # package declaring a name something else already answers to reports under
        # that name, and "FAIL veyru" with no path does not say whose veyru.
        return CheckTarget(
            scenario_cls=loaded.scenario_cls,
            label=f"{loaded.entry_point_name} ({loaded.package_dir})",
            loaded=loaded,
            notes=(),
        )

    raise ValueError(_unresolvable(target=target, path=path))


def _shadowed_by_a_directory(target: str) -> tuple[str, ...]:
    """Say so when a name also reads as a directory here, since it nearly does."""
    if not Path(target).is_dir():
        return ()
    return (
        f"{target!r} resolved to the installed scenario. A directory of that name is "
        f"also here; check that instead with './{target}'.",
    )


def _unresolvable(target: str, path: Path) -> str:
    """Explain both readings that were tried, since either could have been meant."""
    if path.exists():
        return (
            f"{target!r} is not a directory, and is not a scenario name "
            f"({', '.join(available_scenario_names())})."
        )
    if _SCENARIO_NAME.match(target):
        return (
            f"Unknown scenario: {target!r}. Available scenarios: "
            f"{', '.join(available_scenario_names())}. To check a package that is not "
            "installed, pass the directory holding its "
            f"{PYPROJECT_NAME} instead."
        )
    return (
        f"{target!r} is not a directory, and cannot be a scenario name: a name is a "
        "lowercase identifier, holding no dot and no separator. Available scenarios: "
        f"{', '.join(available_scenario_names())}."
    )


__all__ = ["CheckTarget", "ScenarioPathError", "resolve_check_target"]
