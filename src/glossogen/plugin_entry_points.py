"""Reading plug-in declarations from other installed distributions.

glossogen accepts two kinds of contribution from packages it does not ship:
scenarios (``glossogen.scenarios.v<N>``) and metrics (``glossogen.metrics``). Both
are advertised the same way, as entry points in the contributing package's
``pyproject.toml``, and both are read through this module.

Reading imports nothing. ``importlib.metadata`` answers from installed metadata,
so a caller can learn what exists, and which module each thing lives in, without
loading any of it. Scenario event discovery depends on that, running while
:mod:`glossogen.models.event` is still importing.
"""

import logging
from collections.abc import Iterable
from importlib.metadata import EntryPoint, EntryPoints, entry_points

logger = logging.getLogger(__name__)


def all_entry_points() -> EntryPoints:
    """Return every entry point installed metadata carries, across all groups.

    Reading scans the installed distributions, so a caller wanting several groups
    reads once and selects from the result rather than calling per group.

    Nothing is cached. A cache would make a distribution installed into a running
    process permanently invisible, and the scan measures ~5ms against paths that run
    once per request at most.
    """
    return entry_points()


def entry_points_in_group(group: str) -> dict[str, EntryPoint]:
    """Return every entry point declared in ``group``, keyed by its name."""
    return by_name(entry_points=all_entry_points().select(group=group), group=group)


def by_name(entry_points: Iterable[EntryPoint], group: str) -> dict[str, EntryPoint]:
    """Key entry points by name, keeping the first of any duplicate.

    A name claimed by two installed distributions keeps the first seen and logs
    the collision. Choosing silently between them would make a run
    unreproducible from its recorded configuration, which names only the
    scenario or metric rather than the package that supplied it.
    """
    found: dict[str, EntryPoint] = {}
    for entry_point in entry_points:
        existing = found.get(entry_point.name)
        if existing is not None:
            logger.warning(
                "Two installed distributions declare %r in %s (%s and %s); keeping %s",
                entry_point.name,
                group,
                existing.value,
                entry_point.value,
                existing.value,
            )
            continue
        found[entry_point.name] = entry_point
    return found


def package_of(entry_point: EntryPoint) -> str:
    """Return the package holding what an entry point points at.

    The entry point names the module defining the object
    (``my_scenarios.scenario``); its package is the parent
    (``my_scenarios``), which is where conventional sibling modules such as
    ``events`` and ``run_detail_extension`` live. A value naming a top-level
    module with no parent package yields that module's own name.
    """
    module = entry_point.module
    package, separator, _ = module.rpartition(".")
    if separator == "":
        return module
    return package
