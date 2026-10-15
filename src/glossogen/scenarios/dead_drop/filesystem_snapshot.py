"""The server's files as each round ended, rebuilt from a run's log without the shell.

The run logs every case it laid out and every change an agent made. Replaying
those in order over a plain mapping of location to content gives the same tree
the agents worked on, and the authorship ledger the live server keeps gives each
file's authors. Nothing here awaits, so the run-detail API can call it from a
request handler.

The replay follows the in-memory filesystem the shell runs on: a write or copy
creates missing parent directories, a copy or move of a directory carries
everything below it, and a move is a copy followed by a remove.
"""

from typing import NamedTuple

from glossogen.models.event import SimulationEvent
from glossogen.scenarios.dead_drop.authorship import AuthorshipLedger
from glossogen.scenarios.dead_drop.case_generation import AgentCase
from glossogen.scenarios.dead_drop.case_rendering import render_case
from glossogen.scenarios.dead_drop.events import DeadDropCaseStarted, DeadDropFsChanged
from glossogen.scenarios.dead_drop.ids import (
    AGENT_IDS,
    PARTNER_OF,
    PASSWD_PATH,
    SYSTEM_AUTHOR,
    TMP_PATH,
    FsOperation,
    case_file_path,
    home_of,
)
from glossogen.scenarios.dead_drop.server_filesystem import passwd_content
from glossogen.scenarios.dead_drop.server_paths import (
    SERVER_VOLUME,
    AccessPolicy,
    Location,
    is_within,
    location_of,
)
from glossogen.template_renderer import TemplateRenderer


class TreeFile(NamedTuple):
    """One file's content and the last change made to it."""

    content: str
    last_changed_by: str
    last_changed_round: int


class SnapshotFile(NamedTuple):
    """A file as a round ended: where it is, what it holds, who wrote and can read it.

    ``tmp_of`` names the agent whose private ``/tmp`` holds the file under
    ``fs_isolated``, and is None for a file every agent names by the same path.
    """

    path: str
    tmp_of: str | None
    content: str
    authors: list[str]
    readers: list[str]
    last_changed_by: str
    last_changed_round: int


class SnapshotDirectory(NamedTuple):
    """A directory as a round ended."""

    path: str
    tmp_of: str | None


class RoundSnapshot(NamedTuple):
    """Every file and directory on the server at the end of round ``round_number``."""

    round_number: int
    files: list[SnapshotFile]
    directories: list[SnapshotDirectory]


def _tmp_owner(location: Location) -> str | None:
    """The agent whose private ``/tmp`` volume holds ``location``, if it is one."""
    _, separator, agent_id = location.volume.partition(":")
    if separator == "":
        return None
    return agent_id


class FilesystemReplay:
    """The server's files, rebuilt one logged case or change at a time."""

    def __init__(self, fs_isolated: bool, case_in_file: bool, renderer: TemplateRenderer) -> None:
        self._fs_isolated = fs_isolated
        self._case_in_file = case_in_file
        self._renderer = renderer
        self._files: dict[Location, TreeFile] = {}
        self._directories: set[Location] = set()
        self._ledger = AuthorshipLedger()
        self._lay_out()

    def apply_case(self, event: DeadDropCaseStarted) -> None:
        """Lay out a round's case: its case files under ``case_delivery=file``."""
        if not self._case_in_file:
            return
        for agent_case in event.cases:
            location = Location(
                volume=SERVER_VOLUME,
                path=case_file_path(agent_id=agent_case.agent_id, round_number=event.round_number),
            )
            content = render_case(
                renderer=self._renderer,
                round_number=event.round_number,
                agent_case=AgentCase(
                    codebook=dict(agent_case.codebook), requests=tuple(agent_case.requests)
                ),
            )
            self._write_system_file(
                location=location, content=content, round_number=event.round_number
            )

    def apply_change(self, event: DeadDropFsChanged) -> None:
        """Make one logged change again, and record its authors."""
        source = location_of(
            agent_id=event.agent_id, path=event.path, fs_isolated=self._fs_isolated
        )
        destination: Location | None = None
        if event.destination is not None:
            destination = location_of(
                agent_id=event.agent_id, path=event.destination, fs_isolated=self._fs_isolated
            )
        self._apply_content(event=event, source=source, destination=destination)
        self._ledger.record_change(
            operation=event.operation, actor=event.agent_id, source=source, destination=destination
        )

    def snapshot(self, round_number: int) -> RoundSnapshot:
        """The tree as it stands, labelled as the end of round ``round_number``."""
        files = [
            SnapshotFile(
                path=location.path,
                tmp_of=_tmp_owner(location=location),
                content=tree_file.content,
                authors=self._ledger.authors_of(location=location),
                readers=self._readers(location=location),
                last_changed_by=tree_file.last_changed_by,
                last_changed_round=tree_file.last_changed_round,
            )
            for location, tree_file in sorted(self._files.items())
        ]
        directories = [
            SnapshotDirectory(path=location.path, tmp_of=_tmp_owner(location=location))
            for location in sorted(self._directories)
        ]
        return RoundSnapshot(round_number=round_number, files=files, directories=directories)

    def _lay_out(self) -> None:
        """The layout before the first round: ``/etc/passwd``, the homes, ``/tmp``."""
        for agent_id in AGENT_IDS:
            self._put_directory(
                location=Location(volume=SERVER_VOLUME, path=home_of(agent_id=agent_id))
            )
            self._put_directory(
                location=location_of(
                    agent_id=agent_id, path=TMP_PATH, fs_isolated=self._fs_isolated
                )
            )
        self._write_system_file(
            location=Location(volume=SERVER_VOLUME, path=PASSWD_PATH),
            content=passwd_content(),
            round_number=0,
        )

    def _write_system_file(self, location: Location, content: str, round_number: int) -> None:
        self._put_file(
            location=location,
            tree_file=TreeFile(
                content=content, last_changed_by=SYSTEM_AUTHOR, last_changed_round=round_number
            ),
        )
        self._ledger.record_write(location=location, author=SYSTEM_AUTHOR)

    def _apply_content(
        self, event: DeadDropFsChanged, source: Location, destination: Location | None
    ) -> None:
        """Change the tree's contents the way the shell's filesystem did."""
        changed = TreeFile(
            content="", last_changed_by=event.agent_id, last_changed_round=event.round_number
        )
        if event.operation is FsOperation.WRITE and event.content is not None:
            self._put_file(location=source, tree_file=changed._replace(content=event.content))
        elif event.operation is FsOperation.APPEND and event.content is not None:
            existing = self._files.get(source)
            previous = ""
            if existing is not None:
                previous = existing.content
            self._put_file(
                location=source, tree_file=changed._replace(content=previous + event.content)
            )
        elif event.operation is FsOperation.MKDIR:
            self._put_directory(location=source)
        elif event.operation is FsOperation.REMOVE:
            self._remove(root=source)
        elif event.operation is FsOperation.COPY and destination is not None:
            self._copy(source=source, destination=destination, changed=changed)
        elif event.operation is FsOperation.MOVE and destination is not None:
            self._copy(source=source, destination=destination, changed=changed)
            self._remove(root=source)

    def _put_file(self, location: Location, tree_file: TreeFile) -> None:
        self._put_parents(location=location)
        self._files[location] = tree_file

    def _put_directory(self, location: Location) -> None:
        self._put_parents(location=location)
        self._directories.add(location)

    def _put_parents(self, location: Location) -> None:
        """Create every missing directory above ``location``, as a write does."""
        parent = location.path.rpartition("/")[0]
        while parent not in ("", "/"):
            self._directories.add(Location(volume=location.volume, path=parent))
            parent = parent.rpartition("/")[0]

    def _remove(self, root: Location) -> None:
        """Remove ``root`` and everything below it."""
        for location in [known for known in self._files if self._below(known=known, root=root)]:
            del self._files[location]
        self._directories = {
            known for known in self._directories if not self._below(known=known, root=root)
        }

    def _copy(self, source: Location, destination: Location, changed: TreeFile) -> None:
        """Copy ``source`` and everything below it to the same place below ``destination``."""
        files = {
            known: tree_file
            for known, tree_file in self._files.items()
            if self._below(known=known, root=source)
        }
        directories = [
            known for known in self._directories if self._below(known=known, root=source)
        ]
        for known in directories:
            self._put_directory(
                location=self._placed(known=known, source=source, destination=destination)
            )
        for known, tree_file in files.items():
            self._put_file(
                location=self._placed(known=known, source=source, destination=destination),
                tree_file=changed._replace(content=tree_file.content),
            )

    @staticmethod
    def _below(known: Location, root: Location) -> bool:
        return known.volume == root.volume and is_within(path=known.path, root=root.path)

    @staticmethod
    def _placed(known: Location, source: Location, destination: Location) -> Location:
        return Location(
            volume=destination.volume,
            path=destination.path + known.path.removeprefix(source.path),
        )

    def _readers(self, location: Location) -> list[str]:
        """The agents who can read the file at ``location``."""
        owner = _tmp_owner(location=location)
        if owner is not None:
            return [owner]
        return [
            agent_id
            for agent_id in AGENT_IDS
            if AccessPolicy(agent_id=agent_id, partner_id=PARTNER_OF[agent_id]).may_read(
                path=location.path
            )
        ]


def round_snapshots(
    events: list[SimulationEvent],
    fs_isolated: bool,
    case_in_file: bool,
    renderer: TemplateRenderer,
) -> list[RoundSnapshot]:
    """The files as each round with a logged case ended, replayed from ``events`` in order.

    A round's snapshot is taken once every event of that round is applied, so it
    holds what the agents left when the round got its verdict.
    """
    replay = FilesystemReplay(fs_isolated=fs_isolated, case_in_file=case_in_file, renderer=renderer)
    snapshots: list[RoundSnapshot] = []
    current_round: int | None = None
    for event in events:
        if current_round is not None and event.round_number > current_round:
            snapshots.append(replay.snapshot(round_number=current_round))
            current_round = None
        if isinstance(event, DeadDropCaseStarted):
            replay.apply_case(event=event)
            current_round = event.round_number
        elif isinstance(event, DeadDropFsChanged):
            replay.apply_change(event=event)
    if current_round is not None:
        snapshots.append(replay.snapshot(round_number=current_round))
    return snapshots
