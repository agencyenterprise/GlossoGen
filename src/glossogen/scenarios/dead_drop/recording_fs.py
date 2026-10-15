"""One agent's view of the server filesystem: access rules, and a report of what it did.

``RecordingFs`` implements just-bash's ``IFileSystem`` over a ``MountableFs``,
plus the copy, move and ``lstat`` methods its commands also call. Every path is
normalized before the access rules see it. A refused access raises the errors a
real filesystem would, which the commands render as ``Permission denied``.

Each completed change, read and listing is reported to an ``FsObserver`` with the
agent and the round of the command that made it. Once that round has its verdict,
the command's next access raises ``RoundEnded``, so a command that outlasts its
round, such as one waiting in ``sleep``, neither reaches the next round's files nor
logs under the round that ended. Symbolic and hard links are
refused, since a link would let a path inside ``/tmp`` reach a file the rules
keep out of reach. File modes are not modelled, so ``chmod`` is refused as well.

The interpreter runs ``>>`` as a read of the file followed by a write of the old
content plus the new, and ``tee -a`` does the same; the agent is shown nothing of
that read. ``shell_session`` runs both inside an ``appending`` span. A read made
there is held, and dropped when a write to the same file extends what was read.
Every other read made there, such as one in a command substitution that names a
redirection's target, is reported when the span closes.

A ``globbing`` span covers just-bash's expansion of a glob pattern. A directory the
agent may not list reads as empty there, so a pattern such as ``/home/*/x`` skips
the partner's home as bash does, instead of the denial ending the command line.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import NamedTuple, Protocol

from just_bash.fs import MountableFs
from just_bash.types import FsStat

from glossogen.scenarios.dead_drop.ids import FsOperation
from glossogen.scenarios.dead_drop.server_paths import (
    AccessPolicy,
    is_strictly_within,
    normalize_path,
    permission_denied,
)

MAX_FILE_CHARACTERS = 100_000
"""The longest file an agent can write. It bounds what one logged write or read holds."""


class FileTooLargeError(OSError):
    """A write that would leave a file longer than ``MAX_FILE_CHARACTERS``."""


class RoundEnded(BaseException):
    """Raised when a command acts after the round it was run in got its verdict.

    A ``BaseException``, so the interpreter's ``except Exception`` handlers let it
    through and the command line stops where it was raised.
    """

    def __init__(self, round_number: int) -> None:
        super().__init__(f"round {round_number} ended")
        self.round_number = round_number


class FsChange(NamedTuple):
    """One change, as reported to the observer and logged for replay."""

    operation: FsOperation
    path: str
    destination: str | None
    content: str | None
    recursive: bool


class FsObserver(Protocol):
    """Receives what an agent did to the filesystem, after it succeeded."""

    async def changed(self, agent_id: str, round_number: int, change: FsChange) -> None: ...

    def round_ended(self, round_number: int) -> bool: ...

    def authors_of(self, agent_id: str, path: str) -> list[str]: ...

    async def read(
        self, agent_id: str, round_number: int, path: str, content: str, authors: list[str]
    ) -> None: ...

    async def listed(self, agent_id: str, round_number: int, path: str) -> None: ...


class _HeldRead(NamedTuple):
    """A read made inside an ``appending`` span, with the authors it had when made."""

    path: str
    content: str
    authors: list[str]


def _text(content: str | bytes) -> str:
    """``content`` as text, for the log; bytes that are not UTF-8 are replaced."""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


def _rewrite(path: str, previous: str | None, written: str) -> FsChange:
    """What replacing ``previous`` with ``written`` at ``path`` amounts to.

    A rewrite that extends the old content is an append of the added part, which
    keeps the earlier author on the file. One that leaves the content as it was
    changes nothing but the file's time, so the rewriter does not become an author.
    """
    operation = FsOperation.WRITE
    content: str | None = written
    if previous == written:
        operation = FsOperation.TOUCH
        content = None
    elif previous is not None and previous != "" and written.startswith(previous):
        operation = FsOperation.APPEND
        content = written.removeprefix(previous)
    return FsChange(
        operation=operation, path=path, destination=None, content=content, recursive=False
    )


class RecordingFs:
    """``agent_id``'s filesystem: ``inner`` behind ``policy``, reported to ``observer``.

    ``round_number`` is the round of the command running now; the shell session
    sets it before each command, and every report carries it.
    """

    def __init__(self, inner: MountableFs, policy: AccessPolicy, observer: FsObserver) -> None:
        self._inner = inner
        self._policy = policy
        self._observer = observer
        self._appending_depth = 0
        self._globbing_depth = 0
        self._held_reads: list[_HeldRead] = []
        self.round_number = 0

    @property
    def agent_id(self) -> str:
        """The agent whose view this is."""
        return self._policy.agent_id

    def resolve_path(self, base: str, path: str) -> str:
        """Resolve ``path`` against ``base`` the way the inner filesystem does."""
        return self._inner.resolve_path(base=base, path=path)

    def may_inspect(self, path: str) -> bool:
        """Whether the agent may learn that ``path`` exists."""
        return self._policy.may_inspect(path=normalize_path(path=path))

    def may_read(self, path: str) -> bool:
        """Whether the agent may read ``path`` or list it."""
        return self._policy.may_read(path=normalize_path(path=path))

    def require_open_round(self) -> None:
        """Raise ``RoundEnded`` when the round of the command running now has its verdict.

        Every access calls it first. The scenario's own commands that wait or log
        call it too.
        """
        if self._observer.round_ended(round_number=self.round_number):
            raise RoundEnded(round_number=self.round_number)

    @asynccontextmanager
    async def appending(self) -> AsyncGenerator[None]:
        """A span whose reads may be the first half of an append.

        A read made inside it is held. A write to the same file that extends what
        was read completes an append, and the read is dropped. The reads still held
        when the outermost span closes are reported then.
        """
        self._appending_depth += 1
        try:
            yield
        finally:
            self._appending_depth -= 1
            if self._appending_depth == 0:
                await self._report_held_reads()

    @asynccontextmanager
    async def globbing(self) -> AsyncGenerator[None]:
        """A span in which a directory the agent may not list reads as empty."""
        self._globbing_depth += 1
        try:
            yield
        finally:
            self._globbing_depth -= 1

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

        A held read this write completes an append from is dropped first, so it is
        dropped as well when the write is refused.
        """
        written = _text(content=content)
        self._drop_append_read(path=normalize_path(path=path), written=written)
        normalized = self._writable(path=path)
        self._check_size(length=len(written))
        previous: str | None = None
        if await self._inner.is_file(path=normalized):
            previous = await self._inner.read_file(path=normalized)
        await self._inner.write_file(path=normalized, content=content, encoding=encoding)
        await self._report_change(
            change=_rewrite(path=normalized, previous=previous, written=written)
        )

    async def append_file(self, path: str, content: str | bytes) -> None:
        """Add to a file's content, if the agent may write there."""
        normalized = self._writable(path=path)
        added = _text(content=content)
        existing = 0
        if await self._inner.is_file(path=normalized):
            existing = len(await self._inner.read_file(path=normalized))
        self._check_size(length=existing + len(added))
        await self._inner.append_file(path=normalized, content=content)
        operation = FsOperation.APPEND
        logged: str | None = added
        if added == "":
            operation = FsOperation.TOUCH
            logged = None
        await self._report_change(
            change=FsChange(
                operation=operation,
                path=normalized,
                destination=None,
                content=logged,
                recursive=False,
            )
        )

    async def exists(self, path: str) -> bool:
        """Whether ``path`` exists; false where the agent may not look."""
        normalized = self._visible(path=path)
        if normalized is None:
            return False
        return await self._inner.exists(path=normalized)

    async def is_file(self, path: str) -> bool:
        """Whether ``path`` is a file; false where the agent may not look."""
        normalized = self._visible(path=path)
        if normalized is None:
            return False
        return await self._inner.is_file(path=normalized)

    async def is_directory(self, path: str) -> bool:
        """Whether ``path`` is a directory; false where the agent may not look."""
        normalized = self._visible(path=path)
        if normalized is None:
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
                recursive=recursive,
            )
        )

    async def readdir(self, path: str) -> list[str]:
        """List a directory, if the agent may read it; empty if not, while globbing."""
        if self._globbing_depth > 0 and not self.may_read(path=path):
            self.require_open_round()
            return []
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
        """Refused: the access rules ignore file modes, so changing one would mislead."""
        raise PermissionError(f"EPERM: operation not permitted, chmod {mode:o} '{path}'")

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
        """Copy, if the agent may read all of the source and write the destination.

        A directory holding a path the agent may not read, such as ``/home`` with
        the partner's home in it, is refused whole rather than copied in part.
        """
        source = self._readable(path=src)
        destination = self._writable(path=dest)
        self._refuse_onto_itself(source=source, destination=destination, participle="copied")
        if not self._policy.may_read_tree(path=source):
            raise permission_denied()
        content = await self._file_content(path=source)
        await self._inner.cp(src=source, dest=destination, recursive=recursive)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.COPY,
                path=source,
                destination=destination,
                content=content,
                recursive=recursive,
            )
        )

    async def mv(self, src: str, dest: str) -> None:
        """Move, if the agent may write both the source and the destination."""
        source = self._writable(path=src)
        destination = self._writable(path=dest)
        self._refuse_onto_itself(source=source, destination=destination, participle="moved")
        content = await self._file_content(path=source)
        await self._inner.mv(src=source, dest=destination)
        await self._report_change(
            change=FsChange(
                operation=FsOperation.MOVE,
                path=source,
                destination=destination,
                content=content,
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
        elif change.operation is not FsOperation.TOUCH:
            raise ValueError(f"cannot replay {change.operation} without its fields: {change}")

    async def _report_read(self, path: str, content: str) -> None:
        """Report a read, or hold it while an ``appending`` span is open."""
        read = _HeldRead(
            path=path,
            content=content,
            authors=self._observer.authors_of(agent_id=self.agent_id, path=path),
        )
        if self._appending_depth > 0:
            self._held_reads.append(read)
            return
        await self._report(read=read)

    def _drop_append_read(self, path: str, written: str) -> None:
        """Drop the latest held read of ``path`` whose content ``written`` extends."""
        for index in range(len(self._held_reads) - 1, -1, -1):
            held = self._held_reads[index]
            if held.path == path and written.startswith(held.content):
                del self._held_reads[index]
                return

    async def _report_held_reads(self) -> None:
        held = self._held_reads
        self._held_reads = []
        for read in held:
            await self._report(read=read)

    async def _report(self, read: _HeldRead) -> None:
        await self._observer.read(
            agent_id=self.agent_id,
            round_number=self.round_number,
            path=read.path,
            content=read.content,
            authors=read.authors,
        )

    async def _file_content(self, path: str) -> str | None:
        """The text of the file at ``path``, unreported; None for a directory."""
        if not await self._inner.is_file(path=path):
            return None
        return await self._inner.read_file(path=path)

    @staticmethod
    def _refuse_onto_itself(source: str, destination: str, participle: str) -> None:
        """Refuse a copy or move onto its own source or into a directory below it.

        The command prints the message after ``cannot copy 'SOURCE':``, so it
        does not repeat the source.
        """
        if source == destination:
            raise OSError(f"'{source}' and '{destination}' are the same file")
        if is_strictly_within(path=destination, root=source):
            raise OSError(f"a directory cannot be {participle} into itself, '{destination}'")

    @staticmethod
    def _check_size(length: int) -> None:
        if length > MAX_FILE_CHARACTERS:
            raise FileTooLargeError(
                f"File too large: {length} characters, the limit is {MAX_FILE_CHARACTERS}"
            )

    def _visible(self, path: str) -> str | None:
        """``path`` normalized, or None where the agent may not look."""
        self.require_open_round()
        normalized = normalize_path(path=path)
        if not self._policy.may_inspect(path=normalized):
            return None
        return normalized

    def _inspectable(self, path: str) -> str:
        """``path`` normalized, or a not-found error where the agent may not look.

        Not found rather than denied: just-bash's commands stat a path before
        anything else and handle a missing file there, while a denial at that
        step escapes some of them.
        """
        normalized = self._visible(path=path)
        if normalized is None:
            raise FileNotFoundError(
                f"ENOENT: no such file or directory, stat '{normalize_path(path=path)}'"
            )
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
        self.require_open_round()
        normalized = normalize_path(path=path)
        if not self._policy.may_write(path=normalized):
            raise permission_denied()
        return normalized

    async def _report_change(self, change: FsChange) -> None:
        await self._observer.changed(
            agent_id=self.agent_id, round_number=self.round_number, change=change
        )
