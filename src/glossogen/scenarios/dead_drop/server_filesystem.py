"""The in-memory server both agents use: its volumes, each agent's view, and its log.

The server is one ``InMemoryFs`` holding ``/home`` and ``/etc/passwd``, with ``/tmp``
mounted from a second one: shared by both agents, or one per agent under
``fs_isolated``. Each agent reaches it through its own ``RecordingFs``, and this
module is the observer those views report to. It keeps the authorship ledger, logs
every change, read and listing as a scenario event, and wakes agents waiting in
``inotifywait``.

Replaying the logged changes in order through ``replay`` rebuilds the files after
a fork or resume.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import NamedTuple

from just_bash import InMemoryFs
from just_bash.fs import MountableFs, MountableFsOptions, MountConfig

from glossogen.models.event_base import EventBase
from glossogen.scenarios.dead_drop.authorship import AuthorshipLedger, Location
from glossogen.scenarios.dead_drop.events import (
    DeadDropBlockedCommand,
    DeadDropFsChanged,
    DeadDropFsListed,
    DeadDropFsRead,
    DeadDropUsersListed,
)
from glossogen.scenarios.dead_drop.ids import (
    AGENT_IDS,
    PARTNER_OF,
    PASSWD_PATH,
    ROOT_USER,
    ROOT_USER_ID,
    SYSTEM_AUTHOR,
    TMP_PATH,
    FsOperation,
    home_of,
    user_id_of,
)
from glossogen.scenarios.dead_drop.recording_fs import FsChange, RecordingFs
from glossogen.scenarios.dead_drop.server_paths import (
    AccessPolicy,
    is_within,
    normalize_path,
    partner_can_read,
)

SERVER_VOLUME = "server"
SHARED_TMP_VOLUME = "tmp"

_SKELETON_DIRECTORIES = ("/home", "/tmp", "/bin", "/usr")
"""What a new ``InMemoryFs`` creates at its root, removed from a ``/tmp`` volume."""

_DEFAULT_HOME = "/home/user"

_INOTIFY_EVENT: dict[FsOperation, str] = {
    FsOperation.WRITE: "MODIFY",
    FsOperation.APPEND: "MODIFY",
    FsOperation.MKDIR: "CREATE,ISDIR",
    FsOperation.REMOVE: "DELETE",
    FsOperation.COPY: "CREATE",
    FsOperation.MOVE: "MOVED_TO",
    FsOperation.TOUCH: "ATTRIB",
}

EventLog = Callable[[EventBase], Awaitable[None]]
Sleeper = Callable[[float], Awaitable[None]]


def _passwd() -> str:
    """``/etc/passwd`` naming root and both users."""
    lines = [f"{ROOT_USER}:x:{ROOT_USER_ID}:{ROOT_USER_ID}:{ROOT_USER}:/root:/bin/bash"]
    for agent_id in AGENT_IDS:
        user_id = user_id_of(agent_id=agent_id)
        lines.append(f"{agent_id}:x:{user_id}:{user_id}::{home_of(agent_id=agent_id)}:/bin/bash")
    return "\n".join(lines) + "\n"


class _Volumes(NamedTuple):
    """The server volume, and the ``/tmp`` volume each agent sees."""

    server: InMemoryFs
    tmp_by_agent: dict[str, InMemoryFs]


class _ChangeWatcher(NamedTuple):
    """An agent in ``inotifywait``, and the future its first matching change resolves."""

    agent_id: str
    location: Location
    future: asyncio.Future[str]


class ServerFilesystem:
    """Both agents' filesystem, and the observer of everything they do to it."""

    def __init__(self, fs_isolated: bool, home_dirs_readable: bool, log_event: EventLog) -> None:
        self._fs_isolated = fs_isolated
        self._home_dirs_readable = home_dirs_readable
        self._log_event = log_event
        self._ledger = AuthorshipLedger()
        self._watchers: list[_ChangeWatcher] = []
        volumes = self._new_volumes()
        self._views = {
            agent_id: RecordingFs(
                inner=self._mount_for(volumes=volumes, agent_id=agent_id),
                policy=AccessPolicy(
                    agent_id=agent_id,
                    partner_id=PARTNER_OF[agent_id],
                    home_dirs_readable=home_dirs_readable,
                ),
                observer=self,
            )
            for agent_id in AGENT_IDS
        }
        self._volumes = volumes

    def view_for(self, agent_id: str) -> RecordingFs:
        """The filesystem ``agent_id``'s shell runs on."""
        return self._views[agent_id]

    async def reset(self) -> None:
        """Rebuild every volume empty, with only the home directories in place.

        Called before the first round as well: the volumes built at construction
        are not laid out until then, since laying them out awaits.
        """
        volumes = self._new_volumes()
        for agent_id, view in self._views.items():
            view.rebind(inner=self._mount_for(volumes=volumes, agent_id=agent_id))
        self._volumes = volumes
        self._ledger.clear()
        await self._lay_out(volumes=volumes)

    async def write_system_file(self, path: str, content: str) -> None:
        """Write a file the scenario owns, such as a case file, unlogged and authored by root.

        ``path`` is outside ``/tmp``, so it names the same file for both agents.
        """
        parent = normalize_path(path=path).rpartition("/")[0]
        await self._volumes.server.mkdir(path=parent, recursive=True)
        await self._volumes.server.write_file(path=path, content=content)
        self._ledger.record_write(
            location=Location(volume=SERVER_VOLUME, path=normalize_path(path=path)),
            author=SYSTEM_AUTHOR,
        )

    def location(self, agent_id: str, path: str) -> Location:
        """Where ``path``, as ``agent_id`` names it, is stored."""
        normalized = normalize_path(path=path)
        if not is_within(path=normalized, root=TMP_PATH):
            return Location(volume=SERVER_VOLUME, path=normalized)
        if self._fs_isolated:
            return Location(volume=f"{SHARED_TMP_VOLUME}:{agent_id}", path=normalized)
        return Location(volume=SHARED_TMP_VOLUME, path=normalized)

    def is_shared(self, agent_id: str, path: str) -> bool:
        """Whether the partner of ``agent_id`` can read ``path``, as ``agent_id`` names it."""
        return partner_can_read(
            agent_id=agent_id,
            path=path,
            fs_isolated=self._fs_isolated,
            home_dirs_readable=self._home_dirs_readable,
        )

    async def changed(self, agent_id: str, round_number: int, change: FsChange) -> None:
        """Record a change: authorship, the log, and any partner waiting on it."""
        self._apply_to_ledger(agent_id=agent_id, change=change)
        landed_at = change.path
        if change.destination is not None:
            landed_at = change.destination
        await self._log_event(
            DeadDropFsChanged(
                round_number=round_number,
                agent_id=agent_id,
                operation=change.operation,
                path=change.path,
                destination=change.destination,
                content=change.content,
                recursive=change.recursive,
                shared=self.is_shared(agent_id=agent_id, path=landed_at),
            )
        )
        self._wake_watchers(agent_id=agent_id, operation=change.operation, path=landed_at)

    async def read(self, agent_id: str, round_number: int, path: str, content: str) -> None:
        """Log a read with the authors of what was read."""
        await self._log_event(
            DeadDropFsRead(
                round_number=round_number,
                agent_id=agent_id,
                path=path,
                authors=self._ledger.authors_of(
                    location=self.location(agent_id=agent_id, path=path)
                ),
                content=content,
                shared=self.is_shared(agent_id=agent_id, path=path),
            )
        )

    async def listed(self, agent_id: str, round_number: int, path: str) -> None:
        """Log a directory listing."""
        await self._log_event(
            DeadDropFsListed(round_number=round_number, agent_id=agent_id, path=path)
        )

    async def record_users_listed(
        self, agent_id: str, round_number: int, command_name: str
    ) -> None:
        """Log that ``agent_id`` ran a command that named the other user."""
        await self._log_event(
            DeadDropUsersListed(
                round_number=round_number, agent_id=agent_id, command_name=command_name
            )
        )

    async def record_blocked_command(
        self, agent_id: str, round_number: int, command_name: str, arguments: list[str]
    ) -> None:
        """Log that ``agent_id`` ran a command that reaches another user or the network."""
        await self._log_event(
            DeadDropBlockedCommand(
                round_number=round_number,
                agent_id=agent_id,
                command_name=command_name,
                arguments=arguments,
            )
        )

    async def replay(self, event: DeadDropFsChanged) -> None:
        """Apply a logged change again, without access checks or logging."""
        change = FsChange(
            operation=event.operation,
            path=event.path,
            destination=event.destination,
            content=event.content,
            recursive=event.recursive,
        )
        await self._views[event.agent_id].apply_unrecorded(change=change)
        self._apply_to_ledger(agent_id=event.agent_id, change=change)

    async def wait_for_change(
        self, agent_id: str, path: str, timeout_s: float, sleeper: Sleeper
    ) -> str | None:
        """The first change the partner makes at or below ``path``, or None at the timeout.

        The answer is one ``inotifywait`` line: the directory, the event, the name.
        A change where ``agent_id`` may not look, such as inside the partner's
        private home, does not answer, since the line would name it.
        """
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        watcher = _ChangeWatcher(
            agent_id=agent_id, location=self.location(agent_id=agent_id, path=path), future=future
        )
        self._watchers.append(watcher)
        timeout = asyncio.ensure_future(sleeper(timeout_s))
        try:
            await asyncio.wait({future, timeout}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            timeout.cancel()
            self._watchers.remove(watcher)
        if future.done():
            return future.result()
        future.cancel()
        return None

    def _apply_to_ledger(self, agent_id: str, change: FsChange) -> None:
        location = self.location(agent_id=agent_id, path=change.path)
        if change.operation is FsOperation.WRITE:
            self._ledger.record_write(location=location, author=agent_id)
        elif change.operation is FsOperation.APPEND:
            self._ledger.record_append(location=location, author=agent_id)
        elif change.operation is FsOperation.REMOVE:
            self._ledger.record_remove(location=location)
        elif change.operation is FsOperation.COPY and change.destination is not None:
            self._ledger.record_copy(
                source=location,
                destination=self.location(agent_id=agent_id, path=change.destination),
                actor=agent_id,
            )
        elif change.operation is FsOperation.MOVE and change.destination is not None:
            self._ledger.record_move(
                source=location,
                destination=self.location(agent_id=agent_id, path=change.destination),
                actor=agent_id,
            )

    def _wake_watchers(self, agent_id: str, operation: FsOperation, path: str) -> None:
        changed_at = self.location(agent_id=agent_id, path=path)
        normalized = normalize_path(path=path)
        parent, _, name = normalized.rpartition("/")
        line = f"{parent}/ {_INOTIFY_EVENT[operation]} {name}"
        for watcher in self._watchers:
            if watcher.agent_id == agent_id or watcher.future.done():
                continue
            if watcher.location.volume != changed_at.volume:
                continue
            if not self._views[watcher.agent_id].may_inspect(path=normalized):
                continue
            if is_within(path=changed_at.path, root=watcher.location.path):
                watcher.future.set_result(line)

    def _new_volumes(self) -> _Volumes:
        shared_tmp = InMemoryFs()
        tmp_by_agent = {agent_id: shared_tmp for agent_id in AGENT_IDS}
        if self._fs_isolated:
            tmp_by_agent = {agent_id: InMemoryFs() for agent_id in AGENT_IDS}
        return _Volumes(server=InMemoryFs(), tmp_by_agent=tmp_by_agent)

    async def _lay_out(self, volumes: _Volumes) -> None:
        """Strip the library's default layout, create the two homes and ``/etc/passwd``."""
        await volumes.server.rm(path=_DEFAULT_HOME, recursive=True, force=True)
        for agent_id in AGENT_IDS:
            await volumes.server.mkdir(path=home_of(agent_id=agent_id), recursive=True)
        await self.write_system_file(path=PASSWD_PATH, content=_passwd())
        distinct_tmp_volumes = {id(volume): volume for volume in volumes.tmp_by_agent.values()}
        for tmp in distinct_tmp_volumes.values():
            for directory in _SKELETON_DIRECTORIES:
                await tmp.rm(path=directory, recursive=True, force=True)

    @staticmethod
    def _mount_for(volumes: _Volumes, agent_id: str) -> MountableFs:
        return MountableFs(
            options=MountableFsOptions(
                base=volumes.server,
                mounts=[
                    MountConfig(mount_point=TMP_PATH, filesystem=volumes.tmp_by_agent[agent_id])
                ],
            )
        )
