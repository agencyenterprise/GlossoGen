"""One agent's view of the server filesystem: access rules, and a report of what it did.

``RecordingFs`` implements just-bash's ``IFileSystem`` over a ``MountableFs``,
plus the copy, move and ``lstat`` methods its commands also call. Every path is
normalized before the access rules see it. A refused access raises the errors a
real filesystem would, which the commands render as ``Permission denied``.

Each completed change, read and listing is reported to an ``FsObserver`` with the
agent and the round of the command that made it. Symbolic and hard links are
refused, since a link would let a path inside ``/tmp`` reach a file the rules
keep out of reach.
"""

from typing import NamedTuple, Protocol

from just_bash.fs import MountableFs
from just_bash.types import FsStat

from glossogen.scenarios.dead_drop.ids import FsOperation
from glossogen.scenarios.dead_drop.server_paths import (
    AccessPolicy,
    normalize_path,
    permission_denied,
)


class FsChange(NamedTuple):
    """One change, as reported to the observer and logged for replay."""

    operation: FsOperation
    path: str
    destination: str | None
    content: str | None
    mode: int | None
    recursive: bool


class FsObserver(Protocol):
    """Receives what an agent did to the filesystem, after it succeeded."""

    async def changed(self, agent_id: str, round_number: int, change: FsChange) -> None: ...

    async def read(self, agent_id: str, round_number: int, path: str, content: str) -> None: ...

    async def listed(self, agent_id: str, round_number: int, path: str) -> None: ...


def _text(content: str | bytes) -> str:
    """``content`` as text, for the log; bytes that are not UTF-8 are replaced."""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


class RecordingFs:
    """``agent_id``'s filesystem: ``inner`` behind ``policy``, reported to ``observer``.

    ``round_number`` is the round of the command running now; the shell session
    sets it before each command, and every report carries it.
    """

    def __init__(self, inner: MountableFs, policy: AccessPolicy, observer: FsObserver) -> None:
        self._inner = inner
        self._policy = policy
        self._observer = observer
        self.round_number = 0

    @property
    def agent_id(self) -> str:
        """The agent whose view this is."""
        return self._policy.agent_id

    def rebind(self, inner: MountableFs) -> None:
        """Point this view at a rebuilt filesystem."""
        self._inner = inner

    def resolve_path(self, base: str, path: str) -> str:
        """Resolve ``path`` against ``base`` the way the inner filesystem does."""
        return self._inner.resolve_path(base=base, path=path)

    # The defaulted parameters below mirror just-bash's ``IFileSystem`` protocol and
    # ``MountableFs``, which declare them; its commands call these without them.

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """Read a file as text, if the agent may read it."""
        normalized = self._readable(path=path)
        content = await self._inner.read_file(path=normalized, encoding=encoding)
        await self._report_read(path=normalized, content=content)
        return content

    async def read_file_bytes(self, path: str) -> bytes:
        """Read a file as bytes, if the agent may read it."""
        normalized = self._readable(path=path)
        content = await self._inner.read_file_bytes(path=normalized)
        await self._report_read(path=normalized, content=_text(content=content))
        return content

    async def write_file(self, path: str, content: str | bytes, encoding: str = "utf-8") -> None:
        """Replace a file's content, if the agent may write there.

        The interpreter implements ``>>`` as a write of the old content plus the
        new, so a write that extends the existing content is reported as an
        append of the added part. That keeps the earlier author on the file.
        """
        normalized = self._writable(path=path)
        previous: str | None = None
        if await self._inner.is_file(path=normalized):
            previous = await self._inner.read_file(path=normalized)
        await self._inner.write_file(path=normalized, content=content, encoding=encoding)
        written = _text(content=content)
        operation = FsOperation.WRITE
        if previous is not None and previous != "" and written.startswith(previous):
            operation = FsOperation.APPEND
            written = written.removeprefix(previous)
        await self._report_change(
            change=FsChange(
                operation=operation,
                path=normalized,
                destination=None,
                content=written,
                mode=None,
                recursive=False,
            )
        )

    async def append_file(self, path: str, content: str | bytes) -> None:
        """Add to a file's content, if the agent may write there."""
        normalized = self._writable(path=path)
        await self._inner.append_file(path=normalized, content=content)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.APPEND,
                path=normalized,
                destination=None,
                content=_text(content=content),
                mode=None,
                recursive=False,
            )
        )

    async def exists(self, path: str) -> bool:
        """Whether ``path`` exists; false where the agent may not look."""
        normalized = normalize_path(path=path)
        if not self._policy.may_inspect(path=normalized):
            return False
        return await self._inner.exists(path=normalized)

    async def is_file(self, path: str) -> bool:
        """Whether ``path`` is a file; false where the agent may not look."""
        normalized = normalize_path(path=path)
        if not self._policy.may_inspect(path=normalized):
            return False
        return await self._inner.is_file(path=normalized)

    async def is_directory(self, path: str) -> bool:
        """Whether ``path`` is a directory; false where the agent may not look."""
        normalized = normalize_path(path=path)
        if not self._policy.may_inspect(path=normalized):
            return False
        return await self._inner.is_directory(path=normalized)

    async def mkdir(self, path: str, recursive: bool = False) -> None:
        """Create a directory, if the agent may write there."""
        normalized = self._writable(path=path)
        await self._inner.mkdir(path=normalized, recursive=recursive)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.MKDIR,
                path=normalized,
                destination=None,
                content=None,
                mode=None,
                recursive=recursive,
            )
        )

    async def readdir(self, path: str) -> list[str]:
        """List a directory, if the agent may read it."""
        normalized = self._readable(path=path)
        entries = await self._inner.readdir(path=normalized)
        await self._observer.listed(
            agent_id=self.agent_id, round_number=self.round_number, path=normalized
        )
        return entries

    async def rm(self, path: str, recursive: bool = False, force: bool = False) -> None:
        """Remove a file or directory, if the agent may write there."""
        normalized = self._writable(path=path)
        existed = await self._inner.exists(path=normalized)
        await self._inner.rm(path=normalized, recursive=recursive, force=force)
        if existed:
            await self._report_change(
                change=FsChange(
                    operation=FsOperation.REMOVE,
                    path=normalized,
                    destination=None,
                    content=None,
                    mode=None,
                    recursive=recursive,
                )
            )

    async def stat(self, path: str) -> FsStat:
        """A file's metadata, where the agent may look."""
        return await self._inner.stat(path=self._inspectable(path=path))

    async def lstat(self, path: str) -> FsStat:
        """A file's metadata without following links, where the agent may look."""
        return await self._inner.lstat(path=self._inspectable(path=path))

    async def chmod(self, path: str, mode: int) -> None:
        """Change a file's mode, if the agent may write there."""
        normalized = self._writable(path=path)
        await self._inner.chmod(path=normalized, mode=mode)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.CHMOD,
                path=normalized,
                destination=None,
                content=None,
                mode=mode,
                recursive=False,
            )
        )

    async def utimes(self, path: str, atime: float, mtime: float) -> None:
        """Change a file's times, if the agent may write there."""
        normalized = self._writable(path=path)
        await self._inner.utimes(path=normalized, atime=atime, mtime=mtime)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.TOUCH,
                path=normalized,
                destination=None,
                content=None,
                mode=None,
                recursive=False,
            )
        )

    async def symlink(self, target: str, link_path: str) -> None:
        """Refused: a link could reach a file the access rules keep out of reach."""
        raise PermissionError(
            f"EPERM: operation not permitted, symlink '{target}' -> '{link_path}'"
        )

    async def link(self, existing_path: str, new_path: str) -> None:
        """Refused, for the same reason as ``symlink``."""
        raise PermissionError(
            f"EPERM: operation not permitted, link '{existing_path}' -> '{new_path}'"
        )

    async def readlink(self, path: str) -> str:
        """A link's target, where the agent may look."""
        return await self._inner.readlink(path=self._inspectable(path=path))

    async def realpath(self, path: str) -> str:
        """The normalized path; nothing here is a link, so that is the real one."""
        normalized = self._inspectable(path=path)
        if not await self._inner.exists(path=normalized):
            raise FileNotFoundError(f"ENOENT: no such file or directory, realpath '{path}'")
        return normalized

    async def cp(self, src: str, dest: str, recursive: bool = False) -> None:
        """Copy, if the agent may read the source and write the destination."""
        source = self._readable(path=src)
        destination = self._writable(path=dest)
        await self._inner.cp(src=source, dest=destination, recursive=recursive)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.COPY,
                path=source,
                destination=destination,
                content=None,
                mode=None,
                recursive=recursive,
            )
        )

    async def mv(self, src: str, dest: str) -> None:
        """Move, if the agent may write both the source and the destination."""
        source = self._writable(path=src)
        destination = self._writable(path=dest)
        await self._inner.mv(src=source, dest=destination)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.MOVE,
                path=source,
                destination=destination,
                content=None,
                mode=None,
                recursive=True,
            )
        )

    async def apply_unrecorded(self, change: FsChange) -> None:
        """Make ``change`` again with no access check and no report, as a replay does."""
        if change.operation is FsOperation.WRITE and change.content is not None:
            await self._inner.write_file(path=change.path, content=change.content)
        elif change.operation is FsOperation.APPEND and change.content is not None:
            await self._inner.append_file(path=change.path, content=change.content)
        elif change.operation is FsOperation.MKDIR:
            await self._inner.mkdir(path=change.path, recursive=change.recursive)
        elif change.operation is FsOperation.REMOVE:
            await self._inner.rm(path=change.path, recursive=change.recursive, force=True)
        elif change.operation is FsOperation.COPY and change.destination is not None:
            await self._inner.cp(
                src=change.path, dest=change.destination, recursive=change.recursive
            )
        elif change.operation is FsOperation.MOVE and change.destination is not None:
            await self._inner.mv(src=change.path, dest=change.destination)
        elif change.operation is FsOperation.CHMOD and change.mode is not None:
            await self._inner.chmod(path=change.path, mode=change.mode)
        elif change.operation is not FsOperation.TOUCH:
            raise ValueError(f"cannot replay {change.operation} without its fields: {change}")

    def _inspectable(self, path: str) -> str:
        """``path`` normalized, or a not-found error where the agent may not look.

        Not found rather than denied: just-bash's commands stat a path before
        anything else and handle a missing file there, while a denial at that
        step escapes some of them.
        """
        normalized = normalize_path(path=path)
        if not self._policy.may_inspect(path=normalized):
            raise FileNotFoundError(f"ENOENT: no such file or directory, stat '{normalized}'")
        return normalized

    def _readable(self, path: str) -> str:
        """``path`` normalized, if the agent may read it or list it.

        Below a home the agent may not look into, the path answers not found, as
        ``stat`` does there: most of just-bash's commands handle a missing file and
        let a denial escape. Listing the home itself answers denied, which ``ls``
        prints.
        """
        normalized = self._inspectable(path=path)
        if not self._policy.may_read(path=normalized):
            raise permission_denied()
        return normalized

    def _writable(self, path: str) -> str:
        normalized = normalize_path(path=path)
        if not self._policy.may_write(path=normalized):
            raise permission_denied()
        return normalized

    async def _report_read(self, path: str, content: str) -> None:
        await self._observer.read(
            agent_id=self.agent_id, round_number=self.round_number, path=path, content=content
        )

    async def _report_change(self, change: FsChange) -> None:
        await self._observer.changed(
            agent_id=self.agent_id, round_number=self.round_number, change=change
        )
