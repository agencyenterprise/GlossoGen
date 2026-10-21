"""The shared server of signal_game's ``file_system`` medium: users, files and modes.

Both players are users of one in-memory server. Each owns a home directory under
``/home``, ``/tmp`` is open to both with the sticky bit set, and ``/etc/passwd``
names the users. Paths reach this module absolute and normalised; the shell
resolves them against its working directory first.

Access follows Unix for two users who share no group and neither of whom is root: a
node's owner bits apply to its owner and its other bits to everyone else. Reaching a
node needs execute on every directory above it, listing a directory needs read and
execute, and creating or removing an entry needs write and execute on its
directory, where the sticky bit also restricts removal to the entry's or the
directory's owner. Only a node's owner changes its mode.

A refused call raises the exception a filesystem would, built by ``refusal``. Every
change is made through ``apply``, which a fork's replay also uses.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import NamedTuple

from glossogen.scenarios.signal_game.server_changes import ServerChange, ServerChangeKind

ROOT_USER = "root"
NEW_FILE_MODE = 0o644
NEW_DIRECTORY_MODE = 0o755
HOME_MODE = 0o755
SHARED_TMP_MODE = 0o1777
UMASK = 0o022
MODE_MASK = 0o1777
DIRECTORY_SIZE = 4096
MAX_FILE_CHARACTERS = 2_000
"""The longest content one file holds. With ``MAX_NODES_PER_USER`` it bounds what the judge
reads of the server at the end of a round."""
MAX_NODES_PER_USER = 50
MAX_NAME_LENGTH = 255
PASSWD_PATH = "/etc/passwd"
FIRST_USER_ID = 1001

_READ = 4
_WRITE = 2
_EXECUTE = 1


class NodeKind(str, Enum):
    """A file or a directory; the server has no links or devices."""

    FILE = "file"
    DIRECTORY = "directory"


@dataclass
class _Node:
    kind: NodeKind
    owner: str
    mode: int
    content: str
    modified: datetime
    changed: datetime


class NodeInfo(NamedTuple):
    """What ``ls -l`` and ``stat`` show of one node: everything but its content."""

    path: str
    name: str
    kind: NodeKind
    owner: str
    mode: int
    size: int
    modified: datetime
    changed: datetime


class PlayerNode(NamedTuple):
    """A file or directory a player made, with its content (empty for a directory)."""

    path: str
    kind: NodeKind
    owner: str
    content: str


class _Failure(str, Enum):
    NOT_FOUND = "No such file or directory"
    NOT_DIRECTORY = "Not a directory"
    DENIED = "Permission denied"


class _Walk(NamedTuple):
    """Where reaching a path got: its node, or the failure on the way and where it was."""

    node: _Node | None
    failure: _Failure | None


def home_of(user: str) -> str:
    """The user's home directory."""
    return f"/home/{user}"


def user_id_of(user: str, users: tuple[str, ...]) -> int:
    """The user's numeric id: 0 for root, then ``FIRST_USER_ID`` upward in ``users`` order."""
    if user == ROOT_USER:
        return 0
    return FIRST_USER_ID + users.index(user)


def normalize(path: str) -> str:
    """``path`` made absolute, with ``.``, ``..`` and repeated slashes resolved."""
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def join(base: str, path: str) -> str:
    """``path`` resolved against the directory ``base``, as a shell resolves it."""
    if path.startswith("/"):
        return normalize(path=path)
    return normalize(path=f"{base}/{path}")


def parent_of(path: str) -> str:
    """The directory holding ``path``; ``/`` for ``/`` itself."""
    head = path.rsplit("/", 1)[0]
    if head == "":
        return "/"
    return head


def name_of(path: str) -> str:
    """The last component of ``path``; ``/`` for the root."""
    if path == "/":
        return "/"
    return path.rsplit("/", 1)[-1]


def is_within(path: str, root: str) -> bool:
    """Whether ``path`` is ``root`` or below it."""
    return path == root or root == "/" or path.startswith(root + "/")


def _ancestors_of(path: str) -> list[str]:
    """Every directory above ``path``, from ``/`` down to its parent."""
    if path == "/":
        return []
    parts = path.strip("/").split("/")
    return ["/"] + ["/" + "/".join(parts[:depth]) for depth in range(1, len(parts))]


class RefusedPath(OSError):
    """A refused call: the message is the reason, and ``path`` the path the call named.

    Commands print their own ``cannot remove 'PATH':`` before the message, so the
    message holds the reason alone; ``path`` serves an error a command lets escape.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(reason)
        self.path = path


class PathNotFound(RefusedPath, FileNotFoundError):
    """No node at the path, or none the user can reach."""


class PathNotADirectory(RefusedPath, NotADirectoryError):
    """A file where the path needs a directory."""


class PathIsADirectory(RefusedPath, IsADirectoryError):
    """A directory where the call needs a file."""


class PathExists(RefusedPath, FileExistsError):
    """A node already at the path."""


class PathDenied(RefusedPath, PermissionError):
    """Refused by the modes, the sticky bit, or ownership."""


class PathRefused(RefusedPath):
    """Refused for another reason, such as a limit."""


def _raise(failure: _Failure, path: str) -> None:
    if failure is _Failure.NOT_FOUND:
        raise PathNotFound(path=path, reason=failure.value)
    if failure is _Failure.NOT_DIRECTORY:
        raise PathNotADirectory(path=path, reason=failure.value)
    raise PathDenied(path=path, reason=failure.value)


def passwd_content(users: tuple[str, ...]) -> str:
    """``/etc/passwd`` naming root and the players, each in a group of its own."""
    lines = [f"{ROOT_USER}:x:0:0:{ROOT_USER}:/root:/bin/bash"]
    for user in users:
        user_id = user_id_of(user=user, users=users)
        lines.append(f"{user}:x:{user_id}:{user_id}::{home_of(user=user)}:/bin/bash")
    return "\n".join(lines) + "\n"


class SharedServer:
    """The server's nodes, keyed by absolute path."""

    def __init__(self, users: tuple[str, ...], at: datetime) -> None:
        self.users = users
        self._nodes: dict[str, _Node] = {}
        for path, mode in (
            ("/", 0o755),
            ("/home", 0o755),
            ("/tmp", SHARED_TMP_MODE),
            ("/etc", 0o755),
        ):
            self._nodes[path] = _Node(
                kind=NodeKind.DIRECTORY,
                owner=ROOT_USER,
                mode=mode,
                content="",
                modified=at,
                changed=at,
            )
        self._nodes[PASSWD_PATH] = _Node(
            kind=NodeKind.FILE,
            owner=ROOT_USER,
            mode=NEW_FILE_MODE,
            content=passwd_content(users=users),
            modified=at,
            changed=at,
        )
        for user in users:
            self._nodes[home_of(user=user)] = _Node(
                kind=NodeKind.DIRECTORY,
                owner=user,
                mode=HOME_MODE,
                content="",
                modified=at,
                changed=at,
            )

    def info(self, user: str, path: str) -> NodeInfo:
        """A node's metadata, which needs only execute on the directories above it."""
        return self._info(path=path, node=self._reach(user=user, path=path))

    def look(self, user: str, path: str) -> NodeInfo | str:
        """A node's metadata, or why ``user`` cannot reach it, such as ``Permission denied``."""
        walk = self._walk(user=user, path=path)
        if walk.node is None:
            return _failure_of(walk=walk).value
        return self._info(path=path, node=walk.node)

    def look_inside(self, user: str, path: str) -> list[NodeInfo] | str:
        """A directory's entries, or the reason ``user`` cannot list it."""
        walk = self._walk(user=user, path=path)
        if walk.node is None:
            return _failure_of(walk=walk).value
        if walk.node.kind is not NodeKind.DIRECTORY:
            return _Failure.NOT_DIRECTORY.value
        if not self._allows(node=walk.node, user=user, bit=_READ | _EXECUTE):
            return _Failure.DENIED.value
        return self.list_infos(user=user, path=path)

    def kind_of(self, user: str, path: str) -> NodeKind | None:
        """What is at ``path``, or None when ``user`` cannot reach anything there."""
        node = self._walk(user=user, path=path).node
        if node is None:
            return None
        return node.kind

    def exists(self, user: str, path: str) -> bool:
        """Whether ``user`` can reach a node at ``path``."""
        return self._walk(user=user, path=path).node is not None

    def may_list(self, user: str, path: str) -> bool:
        """Whether ``user`` can list the directory at ``path``."""
        node = self._walk(user=user, path=path).node
        return (
            node is not None
            and node.kind is NodeKind.DIRECTORY
            and self._allows(node=node, user=user, bit=_READ | _EXECUTE)
        )

    def list_infos(self, user: str, path: str) -> list[NodeInfo]:
        """A directory's entries in name order; needs read and execute on it."""
        node = self._reach(user=user, path=path)
        if node.kind is not NodeKind.DIRECTORY:
            raise PathNotADirectory(path=path, reason="Not a directory")
        if not self._allows(node=node, user=user, bit=_READ | _EXECUTE):
            raise PathDenied(path=path, reason="Permission denied")
        return [
            self._info(path=child_path, node=child)
            for child_path, child in sorted(self._nodes.items())
            if child_path != "/" and parent_of(path=child_path) == path
        ]

    def read(self, user: str, path: str) -> str:
        """A file's content; needs read on it."""
        node = self._reach(user=user, path=path)
        if node.kind is NodeKind.DIRECTORY:
            raise PathIsADirectory(path=path, reason="Is a directory")
        if not self._allows(node=node, user=user, bit=_READ):
            raise PathDenied(path=path, reason="Permission denied")
        return node.content

    def may_read(self, user: str, path: str) -> bool:
        """Whether ``user`` can read the file at ``path``."""
        node = self._walk(user=user, path=path).node
        return (
            node is not None
            and node.kind is NodeKind.FILE
            and self._allows(node=node, user=user, bit=_READ)
        )

    def write(self, user: str, path: str, content: str, at: datetime) -> list[ServerChange]:
        """Replace a file's content, or create the file; needs write on it, or on its directory."""
        node = self._walk(user=user, path=path).node
        if node is None:
            self._require_creatable(user=user, path=path)
        elif node.kind is NodeKind.DIRECTORY:
            raise PathIsADirectory(path=path, reason="Is a directory")
        elif not self._allows(node=node, user=user, bit=_WRITE):
            raise PathDenied(path=path, reason="Permission denied")
        self._require_size(path=path, length=len(content))
        return self._apply_all(
            changes=[
                _change(
                    kind=ServerChangeKind.WRITE,
                    actor=user,
                    path=path,
                    content=content,
                    mode=None,
                    modified=None,
                    destination=None,
                )
            ],
            at=at,
        )

    def append(self, user: str, path: str, content: str, at: datetime) -> list[ServerChange]:
        """Add to a file's content without reading it, creating the file when it is missing."""
        node = self._walk(user=user, path=path).node
        if node is None:
            return self.write(user=user, path=path, content=content, at=at)
        if node.kind is NodeKind.DIRECTORY:
            raise PathIsADirectory(path=path, reason="Is a directory")
        if not self._allows(node=node, user=user, bit=_WRITE):
            raise PathDenied(path=path, reason="Permission denied")
        whole = node.content + content
        self._require_size(path=path, length=len(whole))
        return self._apply_all(
            changes=[
                _change(
                    kind=ServerChangeKind.WRITE,
                    actor=user,
                    path=path,
                    content=whole,
                    mode=None,
                    modified=None,
                    destination=None,
                )
            ],
            at=at,
        )

    def make_directory(
        self, user: str, path: str, parents: bool, at: datetime
    ) -> list[ServerChange]:
        """Create a directory, and under ``parents`` the missing ones above it."""
        missing: list[str] = []
        for candidate in [*_ancestors_of(path=path)[1:], path]:
            walk = self._walk(user=user, path=candidate)
            if walk.node is not None:
                if candidate == path:
                    if parents and walk.node.kind is NodeKind.DIRECTORY:
                        continue
                    raise PathExists(path=path, reason="File exists")
                continue
            if candidate != path and not parents:
                raise PathNotFound(path=path, reason="No such file or directory")
            missing.append(candidate)
        if not missing:
            return []
        self._require_creatable(user=user, path=missing[0])
        self._require_quota(user=user, path=path, adding=len(missing))
        return self._apply_all(
            changes=[
                _change(
                    kind=ServerChangeKind.MKDIR,
                    actor=user,
                    path=candidate,
                    content=None,
                    mode=None,
                    modified=None,
                    destination=None,
                )
                for candidate in missing
            ],
            at=at,
        )

    def remove(
        self, user: str, path: str, recursive: bool, force: bool, at: datetime
    ) -> list[ServerChange]:
        """Remove a file, an empty directory, or under ``recursive`` a whole tree."""
        walk = self._walk(user=user, path=path)
        if walk.node is None:
            if force and walk.failure is _Failure.NOT_FOUND:
                return []
            _raise(failure=_failure_of(walk=walk), path=path)
            return []
        if path == "/":
            raise PathDenied(path=path, reason="Permission denied")
        below = self._below(path=path)
        if below and not recursive:
            raise PathRefused(path=path, reason="Directory not empty")
        self._require_removable(user=user, path=path, node=walk.node)
        for child_path in below:
            self._require_removable(user=user, path=child_path, node=self._nodes[child_path])
        return self._apply_all(
            changes=[
                _change(
                    kind=ServerChangeKind.REMOVE,
                    actor=user,
                    path=path,
                    content=None,
                    mode=None,
                    modified=None,
                    destination=None,
                )
            ],
            at=at,
        )

    def change_mode(self, user: str, path: str, mode: int, at: datetime) -> list[ServerChange]:
        """Set a node's mode; only its owner may, and setuid and setgid are refused."""
        node = self._reach(user=user, path=path)
        if node.owner != user or mode & ~MODE_MASK:
            raise PathDenied(path=path, reason="Operation not permitted")
        return self._apply_all(
            changes=[
                _change(
                    kind=ServerChangeKind.CHMOD,
                    actor=user,
                    path=path,
                    mode=mode,
                    content=None,
                    modified=None,
                    destination=None,
                )
            ],
            at=at,
        )

    def set_modified(
        self, user: str, path: str, modified: datetime, at: datetime
    ) -> list[ServerChange]:
        """Set a node's modification time; its owner may, or a user who may write it."""
        node = self._reach(user=user, path=path)
        if node.owner != user and not self._allows(node=node, user=user, bit=_WRITE):
            raise PathDenied(path=path, reason="Permission denied")
        return self._apply_all(
            changes=[
                _change(
                    kind=ServerChangeKind.TOUCH,
                    actor=user,
                    path=path,
                    modified=modified,
                    content=None,
                    mode=None,
                    destination=None,
                )
            ],
            at=at,
        )

    def copy(
        self, user: str, source: str, destination: str, recursive: bool, at: datetime
    ) -> list[ServerChange]:
        """Copy a file, or under ``recursive`` a directory, to ``destination``.

        A new copy takes the source's permission bits less the umask, as ``cp``
        without ``-p`` does; an existing destination file keeps its own mode.
        """
        node = self._reach(user=user, path=source)
        if is_within(path=destination, root=source):
            raise PathRefused(path=destination, reason="cannot copy a directory into itself")
        if node.kind is NodeKind.DIRECTORY and not recursive:
            raise PathIsADirectory(path=source, reason="Is a directory")
        plan: list[ServerChange] = []
        for from_path in [source, *self._below(path=source)]:
            from_node = self._nodes[from_path]
            to_path = destination + from_path.removeprefix(source)
            plan.extend(
                self._copy_one(user=user, from_path=from_path, from_node=from_node, to_path=to_path)
            )
        created = sum(change.kind is ServerChangeKind.MKDIR for change in plan) + sum(
            change.kind is ServerChangeKind.WRITE and change.path not in self._nodes
            for change in plan
        )
        self._require_quota(user=user, path=destination, adding=created)
        return self._apply_all(changes=plan, at=at)

    def move(self, user: str, source: str, destination: str, at: datetime) -> list[ServerChange]:
        """Move a node and everything below it to ``destination``, replacing a file there."""
        node = self._reach(user=user, path=source)
        if source == destination:
            raise PathRefused(
                path=source,
                reason=f"'{source}' and '{destination}' are the same file",
            )
        if is_within(path=destination, root=source):
            raise PathRefused(path=destination, reason="cannot move a directory into itself")
        self._require_removable(user=user, path=source, node=node)
        target = self._walk(user=user, path=destination).node
        changes: list[ServerChange] = []
        if target is None:
            self._require_creatable(user=user, path=destination)
        elif target.kind is NodeKind.DIRECTORY:
            raise PathIsADirectory(path=destination, reason="Is a directory")
        else:
            self._require_removable(user=user, path=destination, node=target)
            changes.append(
                _change(
                    kind=ServerChangeKind.REMOVE,
                    actor=user,
                    path=destination,
                    content=None,
                    mode=None,
                    modified=None,
                    destination=None,
                )
            )
        changes.append(
            _change(
                kind=ServerChangeKind.MOVE,
                actor=user,
                path=source,
                destination=destination,
                content=None,
                mode=None,
                modified=None,
            )
        )
        return self._apply_all(changes=changes, at=at)

    def apply(self, change: ServerChange, at: datetime) -> None:
        """Make ``change`` at time ``at``, with no access check; live calls and replay share it."""
        if change.kind is ServerChangeKind.WRITE:
            self._apply_write(change=change, at=at)
        elif change.kind is ServerChangeKind.MKDIR:
            self._nodes[change.path] = _Node(
                kind=NodeKind.DIRECTORY,
                owner=change.actor,
                mode=NEW_DIRECTORY_MODE,
                content="",
                modified=at,
                changed=at,
            )
            self._touch(path=parent_of(path=change.path), at=at)
        elif change.kind is ServerChangeKind.REMOVE:
            for path in [*self._below(path=change.path), change.path]:
                del self._nodes[path]
            self._touch(path=parent_of(path=change.path), at=at)
        elif change.kind is ServerChangeKind.CHMOD:
            node = self._nodes[change.path]
            node.mode = _required(value=change.mode, field="mode", change=change)
            node.changed = at
        elif change.kind is ServerChangeKind.TOUCH:
            node = self._nodes[change.path]
            node.modified = _required(value=change.modified, field="modified", change=change)
            node.changed = at
        else:
            self._apply_move(change=change, at=at)

    def player_nodes(self) -> list[PlayerNode]:
        """Every node a player made, in path order: neither root's nor a home directory."""
        return [
            PlayerNode(path=path, kind=node.kind, owner=node.owner, content=node.content)
            for path, node in sorted(self._nodes.items())
            if node.owner != ROOT_USER and path != home_of(user=node.owner)
        ]

    def _apply_write(self, change: ServerChange, at: datetime) -> None:
        content = _required(value=change.content, field="content", change=change)
        node = self._nodes.get(change.path)
        if node is None:
            mode = NEW_FILE_MODE
            if change.mode is not None:
                mode = change.mode
            self._nodes[change.path] = _Node(
                kind=NodeKind.FILE,
                owner=change.actor,
                mode=mode,
                content=content,
                modified=at,
                changed=at,
            )
            self._touch(path=parent_of(path=change.path), at=at)
            return
        node.content = content
        node.modified = at
        node.changed = at

    def _apply_move(self, change: ServerChange, at: datetime) -> None:
        destination = _required(value=change.destination, field="destination", change=change)
        moved = [change.path, *self._below(path=change.path)]
        nodes = {path: self._nodes.pop(path) for path in moved}
        for path, node in nodes.items():
            self._nodes[destination + path.removeprefix(change.path)] = node
        self._nodes[destination].changed = at
        self._touch(path=parent_of(path=change.path), at=at)
        self._touch(path=parent_of(path=destination), at=at)

    def _copy_one(
        self, user: str, from_path: str, from_node: _Node, to_path: str
    ) -> list[ServerChange]:
        """The changes copying one node makes, after checking ``user`` may make them."""
        if from_node.kind is NodeKind.DIRECTORY:
            if not self._allows(node=from_node, user=user, bit=_READ | _EXECUTE):
                raise PathDenied(path=from_path, reason="Permission denied")
            if self._nodes.get(to_path) is not None:
                return []
            if self._nodes.get(parent_of(path=to_path)) is not None:
                self._require_creatable(user=user, path=to_path)
            return [
                _change(
                    kind=ServerChangeKind.MKDIR,
                    actor=user,
                    path=to_path,
                    content=None,
                    mode=None,
                    modified=None,
                    destination=None,
                )
            ]
        if not self._allows(node=from_node, user=user, bit=_READ):
            raise PathDenied(path=from_path, reason="Permission denied")
        self._require_size(path=to_path, length=len(from_node.content))
        existing = self._nodes.get(to_path)
        if existing is not None:
            if existing.kind is NodeKind.DIRECTORY:
                raise PathIsADirectory(path=to_path, reason="Is a directory")
            if not self._allows(node=existing, user=user, bit=_WRITE):
                raise PathDenied(path=to_path, reason="Permission denied")
            return [
                _change(
                    kind=ServerChangeKind.WRITE,
                    actor=user,
                    path=to_path,
                    content=from_node.content,
                    mode=None,
                    modified=None,
                    destination=None,
                )
            ]
        if self._nodes.get(parent_of(path=to_path)) is not None:
            self._require_creatable(user=user, path=to_path)
        return [
            _change(
                kind=ServerChangeKind.WRITE,
                actor=user,
                path=to_path,
                content=from_node.content,
                mode=from_node.mode & 0o777 & ~UMASK,
                modified=None,
                destination=None,
            )
        ]

    def _apply_all(self, changes: list[ServerChange], at: datetime) -> list[ServerChange]:
        for change in changes:
            self.apply(change=change, at=at)
        return changes

    def _walk(self, user: str, path: str) -> _Walk:
        """The node at ``path`` when every directory above it lets ``user`` through."""
        for ancestor in _ancestors_of(path=path):
            node = self._nodes.get(ancestor)
            if node is None:
                return _Walk(node=None, failure=_Failure.NOT_FOUND)
            if node.kind is not NodeKind.DIRECTORY:
                return _Walk(node=None, failure=_Failure.NOT_DIRECTORY)
            if not self._allows(node=node, user=user, bit=_EXECUTE):
                return _Walk(node=None, failure=_Failure.DENIED)
        node = self._nodes.get(path)
        if node is None:
            return _Walk(node=None, failure=_Failure.NOT_FOUND)
        return _Walk(node=node, failure=None)

    def _reach(self, user: str, path: str) -> _Node:
        """The node at ``path``, or the exception for why ``user`` cannot reach it."""
        walk = self._walk(user=user, path=path)
        if walk.node is None:
            _raise(failure=_failure_of(walk=walk), path=path)
        assert walk.node is not None
        return walk.node

    def _require_creatable(self, user: str, path: str) -> None:
        """Raise unless ``user`` may create an entry at ``path``."""
        if len(name_of(path=path)) > MAX_NAME_LENGTH:
            raise PathRefused(path=path, reason="File name too long")
        parent = self._reach(user=user, path=parent_of(path=path))
        if parent.kind is not NodeKind.DIRECTORY:
            raise PathNotADirectory(path=path, reason="Not a directory")
        if not self._allows(node=parent, user=user, bit=_WRITE | _EXECUTE):
            raise PathDenied(path=path, reason="Permission denied")
        self._require_quota(user=user, path=path, adding=1)

    def _require_removable(self, user: str, path: str, node: _Node) -> None:
        """Raise unless ``user`` may remove the entry at ``path`` from its directory."""
        parent = self._nodes[parent_of(path=path)]
        if not self._allows(node=parent, user=user, bit=_WRITE | _EXECUTE):
            raise PathDenied(path=path, reason="Permission denied")
        if parent.mode & 0o1000 and user not in (node.owner, parent.owner):
            raise PathDenied(path=path, reason="Operation not permitted")
        if node.kind is NodeKind.DIRECTORY and self._below(path=path):
            if not self._allows(node=node, user=user, bit=_READ | _WRITE | _EXECUTE):
                raise PathDenied(path=path, reason="Permission denied")

    def _require_quota(self, user: str, path: str, adding: int) -> None:
        """Raise when ``adding`` more nodes would take ``user`` past ``MAX_NODES_PER_USER``."""
        home = home_of(user=user)
        owned = sum(node.owner == user and other != home for other, node in self._nodes.items())
        if owned + adding > MAX_NODES_PER_USER:
            raise PathRefused(path=path, reason="Disk quota exceeded")

    @staticmethod
    def _require_size(path: str, length: int) -> None:
        if length > MAX_FILE_CHARACTERS:
            raise PathRefused(path=path, reason="File too large")

    def _below(self, path: str) -> list[str]:
        """Every path strictly below ``path``, shallowest first: a parent before its entries."""
        return sorted(
            (other for other in self._nodes if other != path and is_within(path=other, root=path)),
            key=lambda other: (other.count("/"), other),
        )

    def _touch(self, path: str, at: datetime) -> None:
        """A directory whose entries changed: its modification and change times move."""
        node = self._nodes[path]
        node.modified = at
        node.changed = at

    @staticmethod
    def _allows(node: _Node, user: str, bit: int) -> bool:
        """Whether every permission in ``bit`` applies to ``user`` on ``node``."""
        shift = 0
        if node.owner == user:
            shift = 6
        return node.mode & (bit << shift) == bit << shift

    @staticmethod
    def _info(path: str, node: _Node) -> NodeInfo:
        size = DIRECTORY_SIZE
        if node.kind is NodeKind.FILE:
            size = len(node.content.encode("utf-8"))
        return NodeInfo(
            path=path,
            name=name_of(path=path),
            kind=node.kind,
            owner=node.owner,
            mode=node.mode,
            size=size,
            modified=node.modified,
            changed=node.changed,
        )


def _failure_of(walk: _Walk) -> _Failure:
    """Why a walk that found no node stopped; set on every such walk."""
    if walk.failure is None:
        raise ValueError("a walk that found no node carries no failure")
    return walk.failure


def _change(
    kind: ServerChangeKind,
    actor: str,
    path: str,
    content: str | None,
    mode: int | None,
    modified: datetime | None,
    destination: str | None,
) -> ServerChange:
    """A change with every field given; the kind decides which are set."""
    return ServerChange(
        kind=kind,
        actor=actor,
        path=path,
        content=content,
        mode=mode,
        modified=modified,
        destination=destination,
    )


def _required[T](value: T | None, field: str, change: ServerChange) -> T:
    """``value``, which a change of this kind always carries."""
    if value is None:
        raise ValueError(f"a {change.kind.value} change carries no {field}: {change}")
    return value
