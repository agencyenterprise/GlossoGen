"""Make entry points look installed, without installing a distribution.

`entry_points()` reads installed metadata, so anything exercising identity
provider discovery has to stand in for it. The reader takes every group from one
`entry_points()` call, so a test declares the whole set and selection happens
the way it does in production.
"""

from importlib.metadata import EntryPoint
from typing import NamedTuple

import pytest

from glossogen.server.identity import identity_entry_points


class FakeInstalledEntryPoints(NamedTuple):
    """Stands in for everything installed metadata carries, across all groups."""

    by_group: dict[str, list[EntryPoint]]

    @property
    def groups(self) -> set[str]:
        """The groups anything is declared under."""
        return set(self.by_group)

    def select(self, group: str) -> list[EntryPoint]:
        """Return the entry points declared under one group."""
        return list(self.by_group.get(group, []))


def declare_in_groups(
    monkeypatch: pytest.MonkeyPatch,
    groups: dict[str, list[EntryPoint]],
) -> None:
    """Make entry points look installed across several groups at once.

    Needed where a group name carries meaning, which is how the identity contract
    version is recorded.
    """

    def fake_all() -> FakeInstalledEntryPoints:
        return FakeInstalledEntryPoints(by_group=groups)

    monkeypatch.setattr(target=identity_entry_points, name="entry_points", value=fake_all)
