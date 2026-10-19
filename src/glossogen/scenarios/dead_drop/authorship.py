"""Who wrote the content of each file, carried through copies and moves.

Files are keyed by location: the volume they live on plus their path, since under
``fs_isolated`` two agents' ``/tmp/x`` are different files. A write makes the
writer the only author, an append adds the appender, and a copy or move carries
the source's authors to the destination, so a file the partner wrote stays the
partner's after an agent copies it home.

Content the scenario wrote, such as a case file, becomes the content of the
agent that copies or moves it, as it would had the agent written it out with
``cat``. That is the one case where a copy changes who the authors are.
"""

from typing import NamedTuple

from glossogen.scenarios.dead_drop.ids import SYSTEM_AUTHOR
from glossogen.scenarios.dead_drop.server_paths import is_within


class Location(NamedTuple):
    """A file's volume and its path on that volume."""

    volume: str
    path: str


def _claimed_by(authors: frozenset[str], actor: str) -> frozenset[str]:
    """``authors``, with the scenario's own authorship handed to ``actor``."""
    if SYSTEM_AUTHOR not in authors:
        return authors
    return (authors - {SYSTEM_AUTHOR}) | {actor}


class AuthorshipLedger:
    """The authors of every file content written during the run."""

    def __init__(self) -> None:
        self._authors: dict[Location, frozenset[str]] = {}

    def authors_of(self, location: Location) -> list[str]:
        """The authors of the file at ``location``, sorted; empty when nobody wrote it."""
        return sorted(self._authors.get(location, frozenset()))

    def record_write(self, location: Location, author: str) -> None:
        """``author`` replaced the file's content."""
        self._authors[location] = frozenset({author})

    def record_append(self, location: Location, author: str) -> None:
        """``author`` added to the file's content."""
        self._authors[location] = self._authors.get(location, frozenset()) | {author}

    def record_remove(self, location: Location) -> None:
        """The file or directory at ``location`` was removed, with everything below it."""
        for known in self._below(root=location):
            del self._authors[known]

    def record_copy(self, source: Location, destination: Location, actor: str) -> None:
        """``actor`` copied everything at and below ``source`` to ``destination``."""
        copied = {
            known: _claimed_by(authors=self._authors[known], actor=actor)
            for known in self._below(root=source)
        }
        self._place(entries=copied, source=source, destination=destination)

    def record_move(self, source: Location, destination: Location, actor: str) -> None:
        """``actor`` moved everything at and below ``source`` to ``destination``."""
        if source == destination:
            return
        moved = {
            known: _claimed_by(authors=self._authors[known], actor=actor)
            for known in self._below(root=source)
        }
        for known in moved:
            del self._authors[known]
        self._place(entries=moved, source=source, destination=destination)

    def clear(self) -> None:
        """Forget every file, as when the filesystem is rebuilt between rounds."""
        self._authors.clear()

    def _place(
        self,
        entries: dict[Location, frozenset[str]],
        source: Location,
        destination: Location,
    ) -> None:
        """Record ``entries``, taken from below ``source``, at the same place below
        ``destination``."""
        for known, authors in entries.items():
            relative = known.path.removeprefix(source.path)
            placed = Location(volume=destination.volume, path=destination.path + relative)
            self._authors[placed] = authors

    def _below(self, root: Location) -> list[Location]:
        """Every known location at or below ``root`` on the same volume."""
        return [
            known
            for known in self._authors
            if known.volume == root.volume and is_within(path=known.path, root=root.path)
        ]
