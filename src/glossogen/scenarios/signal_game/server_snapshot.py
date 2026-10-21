"""The shared server's player-visible state as one value, read from and written as a tar.

A snapshot holds every node under the players' homes and ``/tmp``: its kind, owner,
mode, modification time and, for a file, its content. The container gives one as a
tar stream after each command and at each round's end; ``diff_snapshots`` turns two of
them into the ``ServerChange`` events the log records; ``apply_change`` replays those
events into a snapshot, which ``to_tar`` turns back into a stream the container
restores. The quotas on what one player may hold are checked on a snapshot too.
"""

import io
import tarfile
from collections import Counter
from datetime import UTC, datetime
from enum import Enum
from typing import NamedTuple

from glossogen.scenarios.signal_game.server_changes import ServerChange, ServerChangeKind

MAX_FILE_CHARACTERS = 2_000
"""The longest content one file holds. With ``MAX_NODES_PER_USER`` it bounds what the judge
reads of the server at the end of a round."""
MAX_NODES_PER_USER = 50
"""The files and directories one player may own, its home excluded."""
SHARED_ROOTS = ("/tmp",)
"""Directories outside the homes that a snapshot covers."""
ROOT_USER = "root"
FIRST_USER_ID = 1001
NEW_FILE_MODE = 0o644
NEW_DIRECTORY_MODE = 0o755
MODE_MASK = 0o7777


class NodeKind(str, Enum):
    """A file or a directory. A symbolic link is recorded as a file holding its target."""

    FILE = "file"
    DIRECTORY = "directory"


class SnapshotNode(NamedTuple):
    """One node as the snapshot holds it."""

    kind: NodeKind
    owner: str
    mode: int
    modified: datetime
    content: str


class QuotaBreach(NamedTuple):
    """A player over a limit after a command: who, and what the limit is."""

    user: str
    reason: str


def home_of(user: str) -> str:
    """The user's home directory: ``/root`` for root, ``/home/<user>`` for a player."""
    if user == ROOT_USER:
        return "/root"
    return f"/home/{user}"


def user_id_of(user: str, users: tuple[str, ...]) -> int:
    """The user's numeric id: 0 for root, then ``FIRST_USER_ID`` upward in ``users`` order."""
    if user == ROOT_USER:
        return 0
    return FIRST_USER_ID + users.index(user)


def name_of(path: str) -> str:
    """The last component of ``path``."""
    return path.rsplit("/", 1)[-1]


def is_within(path: str, root: str) -> bool:
    """Whether ``path`` is ``root`` or below it."""
    return path == root or path.startswith(root + "/")


def snapshot_roots(users: tuple[str, ...]) -> tuple[str, ...]:
    """The directories a snapshot covers: each player's home and the shared roots."""
    return (*(home_of(user=user) for user in users), *SHARED_ROOTS)


class ServerSnapshot:
    """The nodes under the snapshot roots, keyed by absolute path.

    The roots themselves are part of it, so a changed mode on a home is seen.
    """

    def __init__(self, users: tuple[str, ...], nodes: dict[str, SnapshotNode]) -> None:
        self.users = users
        self.nodes = nodes

    def player_nodes(self) -> list[tuple[str, SnapshotNode]]:
        """Every node a player made, in path order: neither root's nor a home or shared root."""
        roots = set(snapshot_roots(users=self.users))
        return [
            (path, node)
            for path, node in sorted(self.nodes.items())
            if node.owner != ROOT_USER and path not in roots
        ]

    def quota_breach(self) -> QuotaBreach | None:
        """The first player over ``MAX_NODES_PER_USER`` or holding a file over
        ``MAX_FILE_CHARACTERS``, or None."""
        owned = Counter(node.owner for _, node in self.player_nodes())
        for user in self.users:
            if owned[user] > MAX_NODES_PER_USER:
                return QuotaBreach(
                    user=user,
                    reason=f"more than {MAX_NODES_PER_USER} files and directories",
                )
        for path, node in self.player_nodes():
            if node.kind is NodeKind.FILE and len(node.content) > MAX_FILE_CHARACTERS:
                return QuotaBreach(
                    user=node.owner,
                    reason=f"a file of more than {MAX_FILE_CHARACTERS} characters at {path}",
                )
        return None

    def tree_lines(self) -> list[str]:
        """One line per node, roots included: path, kind, owner and mode, in path order."""
        return [
            f"{path} {node.kind.value} {node.owner} {node.mode & MODE_MASK:04o}"
            for path, node in sorted(self.nodes.items())
        ]


def empty_snapshot(users: tuple[str, ...], at: datetime) -> ServerSnapshot:
    """The server as it starts: the homes and the shared roots, nothing in them."""
    nodes: dict[str, SnapshotNode] = {}
    for user in users:
        nodes[home_of(user=user)] = SnapshotNode(
            kind=NodeKind.DIRECTORY, owner=user, mode=0o755, modified=at, content=""
        )
    for root in SHARED_ROOTS:
        nodes[root] = SnapshotNode(
            kind=NodeKind.DIRECTORY, owner=ROOT_USER, mode=0o1777, modified=at, content=""
        )
    return ServerSnapshot(users=users, nodes=nodes)


def parse_tar(data: bytes, users: tuple[str, ...]) -> ServerSnapshot:
    """A snapshot from a tar of the snapshot roots, as the container streams it.

    Members tar stores by name relative to ``/`` become absolute paths. Owners come
    from the user names tar recorded, falling back to the numeric id's position in
    ``users``. A symbolic or hard link is kept as a file holding its target; other
    special files are left out.
    """
    nodes: dict[str, SnapshotNode] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive.getmembers():
            path = "/" + member.name.strip("./").strip("/")
            if path == "/":
                continue
            owner = _owner_of(member=member, users=users)
            modified = datetime.fromtimestamp(member.mtime, tz=UTC)
            if member.isdir():
                nodes[path] = SnapshotNode(
                    kind=NodeKind.DIRECTORY,
                    owner=owner,
                    mode=member.mode,
                    modified=modified,
                    content="",
                )
            elif member.isfile():
                extracted = archive.extractfile(member)
                assert extracted is not None
                content = extracted.read().decode("utf-8", errors="replace")
                nodes[path] = SnapshotNode(
                    kind=NodeKind.FILE,
                    owner=owner,
                    mode=member.mode,
                    modified=modified,
                    content=content,
                )
            elif member.issym() or member.islnk():
                nodes[path] = SnapshotNode(
                    kind=NodeKind.FILE,
                    owner=owner,
                    mode=member.mode,
                    modified=modified,
                    content=member.linkname,
                )
    return ServerSnapshot(users=users, nodes=nodes)


def _owner_of(member: tarfile.TarInfo, users: tuple[str, ...]) -> str:
    if member.uname:
        return member.uname
    if member.uid == 0:
        return ROOT_USER
    index = member.uid - FIRST_USER_ID
    if 0 <= index < len(users):
        return users[index]
    return str(member.uid)


def to_tar(snapshot: ServerSnapshot) -> bytes:
    """The snapshot as a tar the container extracts at ``/``, parents before children."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:") as archive:
        for path, node in sorted(snapshot.nodes.items(), key=lambda item: item[0].count("/")):
            info = tarfile.TarInfo(name=path.lstrip("/"))
            info.mode = node.mode & MODE_MASK
            info.uid = user_id_of(user=node.owner, users=snapshot.users)
            info.gid = info.uid
            info.uname = node.owner
            info.gname = node.owner
            info.mtime = int(node.modified.timestamp())
            if node.kind is NodeKind.DIRECTORY:
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            else:
                payload = node.content.encode("utf-8")
                info.type = tarfile.REGTYPE
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def diff_snapshots(before: ServerSnapshot, after: ServerSnapshot) -> list[ServerChange]:
    """The changes that take ``before`` to ``after``, each attributed to the node's owner.

    A removed subtree is one ``remove`` of its top; a new directory is a ``mkdir``;
    a new or rewritten file is a ``write`` with its content; a mode change is a
    ``chmod``; a file whose modification time alone changed is a ``touch``. A
    directory's time moves whenever an entry is added or removed, and those changes
    are reported themselves, so a directory is never touched. A node whose kind
    changed is a removal then a creation. Nothing is reported as a move: a renamed
    node reads as removed and created.
    """
    changes: list[ServerChange] = []
    removed = sorted(
        (
            path
            for path in before.nodes
            if path not in after.nodes or after.nodes[path].kind is not before.nodes[path].kind
        ),
        key=lambda path: (path.count("/"), path),
    )
    reported: list[str] = []
    for path in removed:
        if any(is_within(path=path, root=top) for top in reported):
            continue
        reported.append(path)
        changes.append(
            _change(kind=ServerChangeKind.REMOVE, actor=before.nodes[path].owner, path=path)
        )
    for path, node in sorted(after.nodes.items(), key=lambda item: (item[0].count("/"), item[0])):
        previous = before.nodes.get(path)
        if previous is None or previous.kind is not node.kind:
            changes.extend(_creation(path=path, node=node))
            continue
        if previous.content != node.content:
            changes.append(
                _change(
                    kind=ServerChangeKind.WRITE, actor=node.owner, path=path, content=node.content
                )
            )
        if previous.mode != node.mode:
            changes.append(
                _change(kind=ServerChangeKind.CHMOD, actor=node.owner, path=path, mode=node.mode)
            )
        elif (
            node.kind is NodeKind.FILE
            and previous.content == node.content
            and previous.modified != node.modified
        ):
            changes.append(
                _change(
                    kind=ServerChangeKind.TOUCH, actor=node.owner, path=path, modified=node.modified
                )
            )
    return changes


def _creation(path: str, node: SnapshotNode) -> list[ServerChange]:
    if node.kind is NodeKind.DIRECTORY:
        changes = [_change(kind=ServerChangeKind.MKDIR, actor=node.owner, path=path)]
        if node.mode & MODE_MASK != NEW_DIRECTORY_MODE:
            changes.append(
                _change(kind=ServerChangeKind.CHMOD, actor=node.owner, path=path, mode=node.mode)
            )
        return changes
    mode: int | None = None
    if node.mode & MODE_MASK != NEW_FILE_MODE:
        mode = node.mode
    return [
        _change(
            kind=ServerChangeKind.WRITE,
            actor=node.owner,
            path=path,
            content=node.content,
            mode=mode,
        )
    ]


def apply_change(snapshot: ServerSnapshot, change: ServerChange, at: datetime) -> None:
    """Make a logged change on ``snapshot``, with no access check: replaying a log."""
    if change.kind is ServerChangeKind.WRITE:
        _apply_write(snapshot=snapshot, change=change, at=at)
    elif change.kind is ServerChangeKind.MKDIR:
        snapshot.nodes[change.path] = SnapshotNode(
            kind=NodeKind.DIRECTORY,
            owner=change.actor,
            mode=NEW_DIRECTORY_MODE,
            modified=at,
            content="",
        )
    elif change.kind is ServerChangeKind.REMOVE:
        for path in [path for path in snapshot.nodes if is_within(path=path, root=change.path)]:
            del snapshot.nodes[path]
    elif change.kind is ServerChangeKind.CHMOD:
        node = snapshot.nodes[change.path]
        snapshot.nodes[change.path] = node._replace(
            mode=_required(value=change.mode, field="mode", change=change)
        )
    elif change.kind is ServerChangeKind.TOUCH:
        node = snapshot.nodes[change.path]
        snapshot.nodes[change.path] = node._replace(
            modified=_required(value=change.modified, field="modified", change=change)
        )
    else:
        _apply_move(snapshot=snapshot, change=change)


def _apply_write(snapshot: ServerSnapshot, change: ServerChange, at: datetime) -> None:
    content = _required(value=change.content, field="content", change=change)
    existing = snapshot.nodes.get(change.path)
    mode = NEW_FILE_MODE
    owner = change.actor
    if existing is not None and existing.kind is NodeKind.FILE:
        mode = existing.mode
        owner = existing.owner
    if change.mode is not None:
        mode = change.mode
    snapshot.nodes[change.path] = SnapshotNode(
        kind=NodeKind.FILE, owner=owner, mode=mode, modified=at, content=content
    )


def _apply_move(snapshot: ServerSnapshot, change: ServerChange) -> None:
    """A ``move`` from a log recorded before moves read as remove and create."""
    destination = _required(value=change.destination, field="destination", change=change)
    moved = [path for path in snapshot.nodes if is_within(path=path, root=change.path)]
    for path in moved:
        snapshot.nodes[destination + path.removeprefix(change.path)] = snapshot.nodes.pop(path)


def _change(
    kind: ServerChangeKind,
    actor: str,
    path: str,
    content: str | None = None,
    mode: int | None = None,
    modified: datetime | None = None,
) -> ServerChange:
    return ServerChange(
        kind=kind,
        actor=actor,
        path=path,
        content=content,
        mode=mode,
        modified=modified,
        destination=None,
    )


def _required[T](value: T | None, field: str, change: ServerChange) -> T:
    """``value``, which a change of this kind always carries."""
    if value is None:
        raise ValueError(f"a {change.kind.value} change carries no {field}: {change}")
    return value
