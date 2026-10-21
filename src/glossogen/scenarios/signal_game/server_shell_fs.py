"""One player's view of the shared server, as the filesystem its just-bash shell runs on.

``ServerShellFs`` implements just-bash's ``IFileSystem`` over ``SharedServer`` as one
user, plus the ``lstat``, ``cp``, ``mv`` and ``link`` methods its commands also call.
The server makes the access checks and raises the errors; this class passes them on,
and reports every change to a ``ServerObserver`` with the round of the command line
running now. Once that round is closing, the next access raises ``RoundEnded``, so a
command line that outlasts its round changes nothing after the judge has read the
server, and reaches nothing of the next round.

Two spans adjust what the interpreter sees. Inside ``appending``, which covers ``>>``
and ``tee -a``, a file the user may write but not read reads as empty, and the write
that follows is applied as an append: the interpreter appends by reading the file
and writing back the old content plus the new, and Unix lets a user append to a file
it cannot read. Inside ``globbing``, a directory the user may not list reads as
empty, so a pattern reaching into a closed home skips it as bash does instead of the
denial ending the command line.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol

from just_bash.types import FsStat

from glossogen.scenarios.signal_game.server_changes import ServerChange
from glossogen.scenarios.signal_game.shared_server import (
    NodeInfo,
    NodeKind,
    PathDenied,
    PathRefused,
    SharedServer,
    join,
    normalize,
)


class RoundEnded(BaseException):
    """Raised when a command line acts after the round it was run in started closing.

    A ``BaseException``, so the interpreter's ``except Exception`` handlers let it
    through and the command line stops where it was raised.
    """

    def __init__(self, round_number: int) -> None:
        super().__init__(f"round {round_number} ended")
        self.round_number = round_number


class ServerObserver(Protocol):
    """What a player's shell tells the scenario, and what it asks it."""

    def round_open(self, round_number: int) -> bool:
        """Whether a command line run in ``round_number`` may still act."""
        ...

    def note_changes(self, agent_id: str, changes: list[ServerChange]) -> None:
        """Take in changes as they are made, before anything else can run."""
        ...

    async def log_changes(
        self, agent_id: str, round_number: int, changes: list[ServerChange]
    ) -> None:
        """Record changes in the event log."""
        ...


class ServerShellFs:
    """``user``'s filesystem: ``server`` as that user, reported to ``observer``.

    ``round_number`` is the round of the command line running now; the shell sets it
    before each one. ``clock`` gives the time a change is made at.
    """

    def __init__(
        self,
        server: SharedServer,
        user: str,
        observer: ServerObserver,
        clock: Callable[[], datetime],
    ) -> None:
        self._server = server
        self.user = user
        self._observer = observer
        self._clock = clock
        self._appending_depth = 0
        self._globbing_depth = 0
        self._blind_appends: set[str] = set()
        self.round_number = 0

    def require_open_round(self) -> None:
        """Raise ``RoundEnded`` once the round of the command line running now is closing."""
        if not self._observer.round_open(round_number=self.round_number):
            raise RoundEnded(round_number=self.round_number)

    @asynccontextmanager
    async def appending(self) -> AsyncGenerator[None, None]:
        """A span in which a read the user may not make is the first half of an append."""
        self._appending_depth += 1
        try:
            yield
        finally:
            self._appending_depth -= 1
            if self._appending_depth == 0:
                self._blind_appends.clear()

    @asynccontextmanager
    async def globbing(self) -> AsyncGenerator[None, None]:
        """A span in which a directory the user may not list reads as empty."""
        self._globbing_depth += 1
        try:
            yield
        finally:
            self._globbing_depth -= 1

    def look(self, path: str) -> NodeInfo | str:
        """A node's metadata, or why the user cannot reach it."""
        self.require_open_round()
        return self._server.look(user=self.user, path=normalize(path=path))

    def look_inside(self, path: str) -> list[NodeInfo] | str:
        """A directory's entries, or why the user cannot list it."""
        self.require_open_round()
        return self._server.look_inside(user=self.user, path=normalize(path=path))

    def may_list(self, path: str) -> bool:
        """Whether the user may list the directory at ``path``."""
        return self._server.may_list(user=self.user, path=normalize(path=path))

    # The defaulted parameters below mirror just-bash's ``IFileSystem`` protocol, which
    # declares them; its commands call these without them.

    def resolve_path(self, base: str, path: str) -> str:
        """``path`` resolved against ``base``."""
        return join(base=base, path=path)

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """A file's content; inside ``appending``, empty for a file the user may only write."""
        _ = encoding
        self.require_open_round()
        normalized = normalize(path=path)
        if (
            self._appending_depth > 0
            and self._server.kind_of(user=self.user, path=normalized) is NodeKind.FILE
            and not self._server.may_read(user=self.user, path=normalized)
        ):
            self._blind_appends.add(normalized)
            return ""
        return self._server.read(user=self.user, path=normalized)

    async def read_file_bytes(self, path: str) -> bytes:
        """A file's content as UTF-8 bytes."""
        return (await self.read_file(path=path)).encode("utf-8")

    async def write_file(self, path: str, content: str | bytes, encoding: str = "utf-8") -> None:
        """Replace a file's content, or append it when completing a blind append."""
        self.require_open_round()
        normalized = normalize(path=path)
        text = _text(content=content, encoding=encoding)
        if normalized in self._blind_appends:
            self._blind_appends.discard(normalized)
            await self._report(
                changes=self._server.append(
                    user=self.user, path=normalized, content=text, at=self._clock()
                )
            )
            return
        await self._report(
            changes=self._server.write(
                user=self.user, path=normalized, content=text, at=self._clock()
            )
        )

    async def append_file(self, path: str, content: str | bytes) -> None:
        """Add to a file's content."""
        self.require_open_round()
        await self._report(
            changes=self._server.append(
                user=self.user,
                path=normalize(path=path),
                content=_text(content=content, encoding="utf-8"),
                at=self._clock(),
            )
        )

    async def exists(self, path: str) -> bool:
        """Whether the user can reach a node at ``path``."""
        self.require_open_round()
        return self._server.exists(user=self.user, path=normalize(path=path))

    async def is_file(self, path: str) -> bool:
        """Whether the user can reach a file at ``path``."""
        self.require_open_round()
        return self._server.kind_of(user=self.user, path=normalize(path=path)) is NodeKind.FILE

    async def is_directory(self, path: str) -> bool:
        """Whether the user can reach a directory at ``path``."""
        self.require_open_round()
        kind = self._server.kind_of(user=self.user, path=normalize(path=path))
        return kind is NodeKind.DIRECTORY

    async def mkdir(self, path: str, recursive: bool = False) -> None:
        """Create a directory, and under ``recursive`` the missing ones above it."""
        self.require_open_round()
        await self._report(
            changes=self._server.make_directory(
                user=self.user, path=normalize(path=path), parents=recursive, at=self._clock()
            )
        )

    async def readdir(self, path: str) -> list[str]:
        """A directory's entry names; inside ``globbing``, none where the user may not list."""
        self.require_open_round()
        normalized = normalize(path=path)
        if self._globbing_depth > 0 and not self._server.may_list(user=self.user, path=normalized):
            return []
        return [info.name for info in self._server.list_infos(user=self.user, path=normalized)]

    async def rm(self, path: str, recursive: bool = False, force: bool = False) -> None:
        """Remove a file, an empty directory, or under ``recursive`` a tree."""
        self.require_open_round()
        await self._report(
            changes=self._server.remove(
                user=self.user,
                path=normalize(path=path),
                recursive=recursive,
                force=force,
                at=self._clock(),
            )
        )

    async def stat(self, path: str) -> FsStat:
        """A node's metadata in just-bash's shape."""
        self.require_open_round()
        info = self._server.info(user=self.user, path=normalize(path=path))
        links = 1
        if info.kind is NodeKind.DIRECTORY:
            links = 2
        return FsStat(
            is_file=info.kind is NodeKind.FILE,
            is_directory=info.kind is NodeKind.DIRECTORY,
            is_symbolic_link=False,
            mode=info.mode,
            size=info.size,
            mtime=info.modified.timestamp(),
            nlink=links,
        )

    async def lstat(self, path: str) -> FsStat:
        """The same as ``stat``: the server has no links."""
        return await self.stat(path=path)

    async def chmod(self, path: str, mode: int) -> None:
        """Set a node's mode; only its owner may."""
        self.require_open_round()
        await self._report(
            changes=self._server.change_mode(
                user=self.user, path=normalize(path=path), mode=mode, at=self._clock()
            )
        )

    async def utimes(self, path: str, atime: float, mtime: float) -> None:
        """Set a node's modification time; access times are not kept."""
        _ = atime
        self.require_open_round()
        await self._report(
            changes=self._server.set_modified(
                user=self.user,
                path=normalize(path=path),
                modified=datetime.fromtimestamp(mtime, tz=UTC),
                at=self._clock(),
            )
        )

    async def symlink(self, target: str, link_path: str) -> None:
        """Refused: the server has no links."""
        _ = target
        raise PathDenied(path=link_path, reason="Operation not permitted")

    async def link(self, existing_path: str, new_path: str) -> None:
        """Refused: the server has no links."""
        _ = existing_path
        raise PathDenied(path=new_path, reason="Operation not permitted")

    async def readlink(self, path: str) -> str:
        """Refused as for a node that is not a link, once the node is found."""
        self.require_open_round()
        self._server.info(user=self.user, path=normalize(path=path))
        raise PathRefused(path=path, reason="Invalid argument")

    async def realpath(self, path: str) -> str:
        """The normalised path, once the node is found: nothing here is a link."""
        self.require_open_round()
        normalized = normalize(path=path)
        self._server.info(user=self.user, path=normalized)
        return normalized

    async def cp(self, src: str, dest: str, recursive: bool = False) -> None:
        """Copy a file, or under ``recursive`` a directory."""
        self.require_open_round()
        await self._report(
            changes=self._server.copy(
                user=self.user,
                source=normalize(path=src),
                destination=normalize(path=dest),
                recursive=recursive,
                at=self._clock(),
            )
        )

    async def mv(self, src: str, dest: str) -> None:
        """Move a node and everything below it."""
        self.require_open_round()
        await self._report(
            changes=self._server.move(
                user=self.user,
                source=normalize(path=src),
                destination=normalize(path=dest),
                at=self._clock(),
            )
        )

    async def _report(self, changes: list[ServerChange]) -> None:
        """Hand ``changes`` to the observer: noted at once, then logged."""
        if not changes:
            return
        self._observer.note_changes(agent_id=self.user, changes=changes)
        await self._observer.log_changes(
            agent_id=self.user, round_number=self.round_number, changes=changes
        )


def _text(content: str | bytes, encoding: str) -> str:
    """``content`` as text; bytes that do not decode are replaced."""
    if isinstance(content, bytes):
        return content.decode(encoding, errors="replace")
    return content
