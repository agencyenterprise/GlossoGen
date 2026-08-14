"""Scenarios contributed by other installed distributions.

A distribution advertises a scenario by declaring an entry point, under a group
naming the contract version it was written against::

    [project.entry-points."glossogen.scenarios.v1"]
    reactor_purge = "my_scenarios.reactor_purge.scenario:ReactorPurgeScenario"

:mod:`glossogen.plugin_entry_points` does the reading, and imports nothing. Event
discovery depends on that: :mod:`glossogen.models.event` builds its discriminated
union while it is itself mid-import, so it can afford to import a scenario's
``events`` module but not its ``scenario`` module, which imports back from
``models.event``.

Loading the class is a separate, explicit step, taken only when someone asks for
that scenario by name. See :mod:`glossogen.scenario_loader`.
"""

import re
from importlib.metadata import EntryPoint
from typing import NamedTuple

from glossogen.plugin_entry_points import (
    all_entry_points,
    by_name,
    entry_points_in_group,
    package_of,
)
from glossogen.scenario_api import SCENARIO_API_VERSION

SCENARIO_ENTRY_POINT_GROUP_PREFIX = "glossogen.scenarios.v"
SCENARIO_ENTRY_POINT_GROUP = f"{SCENARIO_ENTRY_POINT_GROUP_PREFIX}{SCENARIO_API_VERSION}"

# The group an author most plausibly types by mistake: the prefix without its
# version. Nothing reads it, so a declaration there would vanish unexplained.
_UNVERSIONED_GROUP = SCENARIO_ENTRY_POINT_GROUP_PREFIX.removesuffix(".v")
_VERSIONED_GROUP = re.compile(rf"^{re.escape(SCENARIO_ENTRY_POINT_GROUP_PREFIX)}\d+$")


def scenario_entry_points() -> dict[str, EntryPoint]:
    """Return every scenario declared for the contract version this platform speaks."""
    return entry_points_in_group(group=SCENARIO_ENTRY_POINT_GROUP)


def scenario_package_of(entry_point: EntryPoint) -> str:
    """Return the package holding the scenario an entry point points at."""
    return package_of(entry_point=entry_point)


class ScenarioDeclarations(NamedTuple):
    """Every installed scenario declaration, split by whether this platform reads it.

    ``current`` holds what can be resolved. ``other_groups`` maps a name to the
    group it was declared under instead, which turns an unreadable declaration from
    an absence into something explainable.
    """

    current: dict[str, EntryPoint]
    other_groups: dict[str, str]


def scenario_declarations() -> ScenarioDeclarations:
    """Return both halves from a single read of installed metadata.

    Listing wants the readable declarations and the unreadable ones together. One
    read serves both halves, which keeps it to a single scan.
    """
    installed = all_entry_points()
    current: dict[str, EntryPoint] = {}
    other_groups: dict[str, str] = {}
    for group in installed.groups:
        if not _is_scenario_group(group=group):
            continue
        declared = by_name(entry_points=installed.select(group=group), group=group)
        if group == SCENARIO_ENTRY_POINT_GROUP:
            current = declared
            continue
        for name in declared:
            other_groups[name] = group
    # A name declared under both a readable group and an unreadable one is
    # readable, so it is not a problem to report. That combination is what a
    # half-finished migration looks like: the new group added, the old one not yet
    # removed. Groups are visited in no particular order, so this is settled after
    # both passes rather than during them.
    for name in current:
        other_groups.pop(name, None)
    return ScenarioDeclarations(current=current, other_groups=other_groups)


def _is_scenario_group(group: str) -> bool:
    """Return whether a group name is one a scenario could plausibly be declared under.

    The bare prefix counts, because the group name is the one thing a plug-in
    author types by hand and dropping the ``.v1`` is the likeliest single mistake.
    """
    return group == _UNVERSIONED_GROUP or _VERSIONED_GROUP.match(group) is not None


def scenarios_declared_under_other_groups() -> dict[str, str]:
    """Return scenarios this platform will not read, name to the group they used.

    A plug-in declared under any group but the current one is absent from what this
    platform reads, and an absence looks the same as nothing being installed.
    Finding those declarations lets the situation be reported instead. Reads
    installed metadata and imports nothing.

    Covers two mistakes. One is a real version difference,
    ``glossogen.scenarios.v2`` against a platform speaking 1. The other is a
    typo: the group name is the one thing a plug-in author types by hand, and
    dropping the ``.v1`` leaves a declaration nothing reads and nothing explains.
    Both are answered the same way, by naming the group that was used.
    """
    return scenario_declarations().other_groups
