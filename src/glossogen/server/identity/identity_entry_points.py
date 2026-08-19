"""Identity providers contributed by other installed distributions.

A distribution advertises a provider by declaring an entry point, under a group
naming the contract version it was written against::

    [project.entry-points."glossogen.identity_provider.v1"]
    my_provider = "my_auth.identity_provider:MyIdentityProvider"

Reading imports nothing, the same as :mod:`glossogen.scenario_entry_points`. Loading
the class is a separate, explicit step; see
:mod:`glossogen.server.identity.identity_provider_loader`.
"""

import re
from importlib.metadata import EntryPoint
from typing import NamedTuple

from glossogen.plugin_entry_points import all_entry_points, by_name
from glossogen.server.identity.identity_api import IDENTITY_API_VERSION

IDENTITY_ENTRY_POINT_GROUP_PREFIX = "glossogen.identity_provider.v"
IDENTITY_ENTRY_POINT_GROUP = f"{IDENTITY_ENTRY_POINT_GROUP_PREFIX}{IDENTITY_API_VERSION}"

# The group an author most plausibly types by mistake: the prefix without its
# version. Nothing reads it, so a declaration there would vanish unexplained.
_UNVERSIONED_GROUP = IDENTITY_ENTRY_POINT_GROUP_PREFIX.removesuffix(".v")
_VERSIONED_GROUP = re.compile(rf"^{re.escape(IDENTITY_ENTRY_POINT_GROUP_PREFIX)}\d+$")


class IdentityProviderDeclarations(NamedTuple):
    """Every installed provider declaration, split by whether this platform reads it.

    ``current`` holds what can be resolved. ``other_groups`` maps a name to the group
    it was declared under instead, which turns an unreadable declaration from an
    absence into something explainable. For an authentication contract that
    distinction decides whether the server may boot at all.
    """

    current: dict[str, EntryPoint]
    other_groups: dict[str, str]


def _is_identity_group(group: str) -> bool:
    """Return whether a group name is one a provider could plausibly be declared under.

    The bare prefix counts, because the group name is the one thing a plug-in author
    types by hand and dropping the ``.v1`` is the likeliest single mistake.
    """
    return group == _UNVERSIONED_GROUP or _VERSIONED_GROUP.match(group) is not None


def identity_provider_declarations() -> IdentityProviderDeclarations:
    """Return both halves from a single read of installed metadata."""
    installed = all_entry_points()
    current: dict[str, EntryPoint] = {}
    other_groups: dict[str, str] = {}
    for group in installed.groups:
        if not _is_identity_group(group=group):
            continue
        declared = by_name(entry_points=installed.select(group=group), group=group)
        if group == IDENTITY_ENTRY_POINT_GROUP:
            current = declared
            continue
        for name in declared:
            other_groups[name] = group
    # A name declared under both a readable group and an unreadable one is readable,
    # so it is not a problem to report. That combination is what a half-finished
    # migration looks like: the new group added, the old one not yet removed.
    for name in current:
        other_groups.pop(name, None)
    return IdentityProviderDeclarations(current=current, other_groups=other_groups)
