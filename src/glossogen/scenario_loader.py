"""Resolves scenario names to classes for every caller.

Two sources feed it: the registry of scenarios shipped here, and scenarios
declared by other installed distributions under the versioned
``glossogen.scenarios.v<N>`` entry-point group. Callers ask by name and do not
know which source answered.

Scenarios shipped here are imported when the registry module is. An external
scenario's class is imported the first time someone asks for it, so listing the
available names stays cheap.
"""

import logging
import sys
from importlib.metadata import EntryPoint

from glossogen.scenario_api import SCENARIO_API_VERSION
from glossogen.scenario_entry_points import (
    SCENARIO_ENTRY_POINT_GROUP,
    ScenarioDeclarations,
    scenario_declarations,
    scenario_entry_points,
    scenarios_declared_under_other_groups,
)
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY

logger = logging.getLogger(__name__)

# Problems already reported this process, so a per-request listing does not repeat
# them. Keyed by the problem and the declaration it concerns, not by name alone,
# so a plug-in that changes its declaration is reported again.
_ALREADY_WARNED: set[tuple[str, ...]] = set()


def available_scenario_names() -> list[str]:
    """Return every scenario name that can be run, built-in and external.

    Imports no scenario class: external names come from installed metadata.
    """
    declarations = scenario_declarations()
    _report_unusable(declarations=declarations)
    return sorted(set(SCENARIO_REGISTRY) | set(declarations.current))


def find_scenario_class(name: str) -> type[SimulationScenario] | None:
    """Return the scenario class registered under ``name``, or None if there is none.

    The soft half of the pair, for callers that treat not having a scenario as an
    ordinary outcome: a run whose recorded scenario is no longer installed, or a
    run-detail page for one that a plug-in has since broken. Those callers degrade,
    reporting no primary channels or a 404, and a raise from here would turn each
    into a 500 on the one path the design otherwise keeps serving.

    So a misdeclared plug-in is logged and answered with None, the same tolerance
    :func:`iter_scenario_classes` applies for the same reason. Use
    :func:`get_scenario_class` where the caller asked for this scenario by name and
    wants to be told why it cannot have it.
    """
    built_in = SCENARIO_REGISTRY.get(name)
    if built_in is not None:
        return built_in
    entry_point = scenario_entry_points().get(name)
    if entry_point is None:
        return None
    try:
        return _load_external(name=name, entry_point=entry_point)
    except ValueError:
        logger.exception("Scenario %r is installed but could not be loaded", name)
        return None


def get_scenario_class(name: str) -> type[SimulationScenario]:
    """Return the scenario class registered under ``name``.

    Raises ValueError if the name does not match any registered scenario, or names
    one that is installed and cannot be loaded. Resolves without going through
    :func:`find_scenario_class`, which answers None in that second case and would
    lose the explanation.
    """
    built_in = SCENARIO_REGISTRY.get(name)
    if built_in is not None:
        return built_in
    entry_point = scenario_entry_points().get(name)
    if entry_point is not None:
        return _load_external(name=name, entry_point=entry_point)
    other_group = scenarios_declared_under_other_groups().get(name)
    if other_group is not None:
        raise ValueError(
            f"Scenario '{name}' is installed, but declared under the entry-point group "
            f"'{other_group}', which this glossogen does not read. It reads "
            f"'{SCENARIO_ENTRY_POINT_GROUP}' (scenario contract version "
            f"{SCENARIO_API_VERSION}). Upgrade whichever side is older, or correct the "
            "group name."
        )
    available = ", ".join(available_scenario_names())
    raise ValueError(f"Unknown scenario: '{name}'. Available scenarios: {available}")


def iter_scenario_classes() -> list[tuple[str, type[SimulationScenario]]]:
    """Return every loadable scenario as ``(name, class)``, ordered by name.

    Unlike :func:`available_scenario_names` this imports every external
    scenario, so use it only where the classes themselves are needed, such as
    listing each scenario's metrics and presets. Installed metadata is read once
    for the whole listing rather than once per name.

    An external scenario that cannot be loaded is logged and left out, rather
    than raising. This backs the scenario list, so one unusable third-party
    plug-in would otherwise take the list down for every scenario shipped here
    and leave the caller no way to run any of them. Asking for that scenario by
    name still raises, because then there is nothing else the caller wanted.
    """
    declarations = scenario_declarations()
    _report_unusable(declarations=declarations)
    external = declarations.current
    resolved: list[tuple[str, type[SimulationScenario]]] = list(SCENARIO_REGISTRY.items())
    for name in set(external) - set(SCENARIO_REGISTRY):
        try:
            resolved.append((name, _load_external(name=name, entry_point=external[name])))
        except ValueError:
            logger.exception("Leaving scenario %r out of the listing", name)
    return sorted(resolved, key=lambda pair: pair[0])


def _report_unusable(declarations: ScenarioDeclarations) -> None:
    """Report every installed scenario declaration this platform will not use.

    Both cases are silent by nature: a shadowed name resolves to somebody else's
    scenario, and one declared under a group nothing reads is missing from the list
    with nothing said. An operator looks at the listing first after installing a
    plug-in, so both are reported there.

    Each distinct problem is reported once per process. Listing backs a web endpoint
    and an MCP tool, and repeating the same warning per request would bury it in its
    own copies.
    """
    for name, entry_point in declarations.current.items():
        if name not in SCENARIO_REGISTRY:
            continue
        _warn_once(
            key=("shadowed", name, entry_point.value),
            message=(
                "Scenario %r is already provided by glossogen; ignoring the one declared by %s"
            ),
            args=(name, entry_point.value),
        )
    for name, group in declarations.other_groups.items():
        _warn_once(
            key=("other-group", name, group),
            message=(
                "Scenario %r is declared under entry-point group %r, which this glossogen "
                "does not read; it reads %r. Not listing it."
            ),
            args=(name, group, SCENARIO_ENTRY_POINT_GROUP),
        )


def forget_reported_problems() -> None:
    """Forget which problems have been reported, so they are reported again.

    The suppression below is per process, so a warning fires only the first time its
    key is seen. In a running server that is the intent. In a test suite it couples
    one test's assertions to another's choice of scenario name, so tests call this
    between cases.
    """
    _ALREADY_WARNED.clear()


def _warn_once(key: tuple[str, ...], message: str, args: tuple[str, ...]) -> None:
    """Log a warning the first time this exact problem is seen in this process."""
    if key in _ALREADY_WARNED:
        return
    _ALREADY_WARNED.add(key)
    logger.warning(message, *args)


def _load_external(name: str, entry_point: EntryPoint) -> type[SimulationScenario]:
    """Import an externally-declared scenario class and check it over.

    Every failure here is the plug-in's problem rather than the platform's, so
    each one raises ValueError naming the entry point. Unlike a metric, which is
    skipped so the others still run, a scenario that cannot be loaded is one the
    caller asked for by name, so there is nothing to fall back to.
    """
    try:
        loaded = entry_point.load()
    except Exception as exc:
        raise ValueError(
            f"Scenario entry point '{name}' ({entry_point.value}) failed to import: {exc}"
        ) from exc
    if not isinstance(loaded, type) or not issubclass(loaded, SimulationScenario):
        raise ValueError(
            f"Scenario entry point '{name}' ({entry_point.value}) "
            "does not name a SimulationScenario subclass"
        )
    _check_defined_in_a_submodule(name=name, entry_point=entry_point, loaded=loaded)
    _check_reported_name(name=name, entry_point=entry_point, loaded=loaded)
    return loaded


def _check_defined_in_a_submodule(
    name: str,
    entry_point: EntryPoint,
    loaded: type[SimulationScenario],
) -> None:
    """Refuse an entry point that points at a package rather than a module.

    Event discovery reads the package a scenario lives in from the entry-point
    string, without importing anything, because it runs while
    ``glossogen.models.event`` is mid-import. That read assumes the string names a
    module inside the package, and takes everything before the last dot. Point it
    at the package itself and the package is misread as its own parent, the
    ``events`` module looks absent, and the scenario's event types never reach the
    parser: the run writes fine and its JSONL will not parse back afterwards.

    Checked against the module the entry point names, not the module the class is
    defined in. Those differ whenever the package's ``__init__`` re-exports the
    class, which is ordinary Python packaging: the class itself then looks fine
    while discovery still reads from the wrong place.
    """
    module = sys.modules.get(entry_point.module)
    if module is None or not hasattr(module, "__path__"):
        return
    if loaded.__module__ != entry_point.module:
        # The class is in a submodule and the package re-exports it, so the entry
        # point only has to name where it was defined.
        remedy = (
            f"Point it at the module defining the class ('{loaded.__module__}:{loaded.__name__}')"
        )
    else:
        remedy = (
            "Move the class into a submodule and point the entry point at it "
            f"('{entry_point.module}.scenario:{loaded.__name__}')"
        )
    raise ValueError(
        f"Scenario entry point '{name}' ({entry_point.value}) points at the "
        f"'{entry_point.module}' package rather than a module inside it, which glossogen "
        f"cannot discover events for. {remedy}, and keep the package's __init__ empty."
    )


def _check_reported_name(
    name: str,
    entry_point: EntryPoint,
    loaded: type[SimulationScenario],
) -> None:
    """Refuse a class that answers to a different name than it is registered under.

    ``name()`` is what a run directory is named after and what
    ``SimulationStarted`` records, while the name here is what ``glossogen run``,
    ``evaluate`` and the resume flows look a run up by. Let the two disagree and
    a run launched as ``reactor_purge`` lands in ``runs/purge/``, where none of
    those commands will find it again. Nothing about the run looks wrong at the
    time.
    """
    try:
        reported = loaded.name()
    except Exception as exc:
        raise ValueError(
            f"Scenario entry point '{name}' ({entry_point.value}) "
            f"could not report its own name: {exc}"
        ) from exc
    if reported != name:
        raise ValueError(
            f"Scenario entry point '{name}' names a class that calls itself {reported!r}. "
            "The entry-point name and the scenario's name() must match, because run "
            "directories are named after name() and every later command looks a run up "
            "by the name it was launched with. Rename the entry point to "
            f"{reported!r}, or override name() to return {name!r}."
        )
