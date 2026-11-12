"""Resolve one argument to the scenarios it refers to, by name or by path.

`glossogen validate` takes either. A loaded scenario is named (`validate veyru`),
and a file or directory is pointed at (`validate ./negotiation/negotiation.py`). Both
end up in the same contract checks, so which form was used is a detail of
finding the classes rather than two different commands.

A scenario name is a lowercase identifier, holding no dot and no separator, so
anything carrying one is a path. A bare identifier is a name when a loaded
scenario has it, and a path otherwise. When it is also a directory here, it
resolves to the loaded scenario, which is the common reading, and says so,
because the alternative is one character away.
"""

from pathlib import Path
from typing import NamedTuple

from glossogen.scenario_contract.loader import available_scenario_names, get_scenario_class
from glossogen.scenario_contract.path_loader import (
    PathLoadedScenario,
    ScenarioPathError,
    load_scenarios_from_path,
)
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.scenario_name import is_valid_scenario_name


class CheckTarget(NamedTuple):
    """A scenario to check, and how it was found.

    ``loaded`` is present only for the path form. The package checks read it,
    since they are about the project the path is in.
    """

    scenario_cls: type[SimulationScenario]
    label: str
    loaded: PathLoadedScenario | None
    notes: tuple[str, ...]


def resolve_check_targets(target: str) -> list[CheckTarget]:
    """Return the scenarios ``target`` refers to: one for a name, each one a path registers.

    Raises :class:`ScenarioPathError` when it reads as a path that cannot be
    loaded, and ``ValueError`` when it reads as a name nothing answers to.
    """
    if is_valid_scenario_name(name=target) and target in available_scenario_names():
        return [
            CheckTarget(
                scenario_cls=get_scenario_class(name=target),
                label=target,
                loaded=None,
                notes=_shadowed_by_a_directory(target=target),
            )
        ]

    path = Path(target)
    if path.exists():
        # The path is named alongside each scenario, because the two can disagree
        # and "FAIL veyru" with no path does not say whose veyru. Echoed as the
        # caller typed it, which reads back as what they ran.
        return [
            CheckTarget(
                scenario_cls=loaded.scenario_cls,
                label=f"{loaded.name} ({target})",
                loaded=loaded,
                notes=(),
            )
            for loaded in load_scenarios_from_path(path=path)
        ]

    raise ValueError(_unresolvable(target=target))


def _shadowed_by_a_directory(target: str) -> tuple[str, ...]:
    """Say so when a name also reads as a directory here, since it nearly does."""
    if not Path(target).is_dir():
        return ()
    return (
        f"{target!r} resolved to the loaded scenario. A directory of that name is "
        f"also here; check that instead with './{target}'.",
    )


def _unresolvable(target: str) -> str:
    """Explain both readings that were tried, since either could have been meant."""
    available = ", ".join(available_scenario_names())
    if is_valid_scenario_name(name=target):
        return (
            f"Unknown scenario: {target!r}. Loaded scenarios: {available}. To check a "
            "scenario this process has not loaded, pass the file or directory that "
            "defines it."
        )
    return (
        f"{target!r} does not exist, and cannot be a scenario name: a name is a "
        f"lowercase identifier, holding no dot and no separator. Loaded scenarios: "
        f"{available}."
    )


__all__ = ["CheckTarget", "ScenarioPathError", "resolve_check_targets"]
