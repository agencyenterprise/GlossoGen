"""Harnesses contributed by other installed distributions.

A distribution advertises a harness by declaring an entry point, under a group
naming the contract version it was written against::

    [project.entry-points."glossogen.agent_harnesses.v1"]
    my_harness = "my_harnesses.harness:MyHarness"

The entry-point name is the harness name a seat selects it by, so it must match
the class's own ``name()``. Reading imports nothing; the class is loaded when a
launch names it, in :mod:`glossogen.runners.harness_loader`.
"""

import re
from importlib.metadata import EntryPoint
from typing import NamedTuple

from glossogen.plugin_entry_points import all_entry_points, by_name
from glossogen.runners.harness_api import HARNESS_API_VERSION

HARNESS_ENTRY_POINT_GROUP_PREFIX = "glossogen.agent_harnesses.v"
HARNESS_ENTRY_POINT_GROUP = f"{HARNESS_ENTRY_POINT_GROUP_PREFIX}{HARNESS_API_VERSION}"

_UNVERSIONED_GROUP = HARNESS_ENTRY_POINT_GROUP_PREFIX.removesuffix(".v")
_VERSIONED_GROUP = re.compile(rf"^{re.escape(HARNESS_ENTRY_POINT_GROUP_PREFIX)}\d+$")


class HarnessDeclarations(NamedTuple):
    """Every installed harness declaration, split by whether this platform reads it.

    ``current`` holds what can be resolved. ``other_groups`` maps a name to the
    group it was declared under instead, so an unreadable declaration can be
    reported rather than looking like nothing installed.
    """

    current: dict[str, EntryPoint]
    other_groups: dict[str, str]


def harness_declarations() -> HarnessDeclarations:
    """Both halves from a single read of installed metadata."""
    installed = all_entry_points()
    current: dict[str, EntryPoint] = {}
    other_groups: dict[str, str] = {}
    for group in installed.groups:
        if not _is_harness_group(group=group):
            continue
        declared = by_name(entry_points=installed.select(group=group), group=group)
        if group == HARNESS_ENTRY_POINT_GROUP:
            current = declared
            continue
        for name in declared:
            other_groups[name] = group
    for name in current:
        other_groups.pop(name, None)
    return HarnessDeclarations(current=current, other_groups=other_groups)


def _is_harness_group(group: str) -> bool:
    """Whether a group name is one a harness could plausibly be declared under.

    The bare prefix counts, so a declaration that leaves out the ``.v<N>``
    suffix is reported rather than ignored.
    """
    return group == _UNVERSIONED_GROUP or _VERSIONED_GROUP.match(group) is not None
