"""What the players do to the shared server, as the scenario keeps track of it.

``ServerActivity`` is the observer every player's shell reports to. It logs each
change as a ``signal_game_server_changed`` event, keeps the texts the round's changes
put on the server and the texts the plaintext judge already passed, wakes a partner
waiting in ``inotifywait`` on a change below the path it watches, and answers whether
a command line's round may still act. Replaying the logged changes in order rebuilds
the server after a fork.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import NamedTuple

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.events import SignalGameServerChanged
from glossogen.scenarios.signal_game.ids import WrittenTextKind
from glossogen.scenarios.signal_game.plaintext_judge import WrittenText
from glossogen.scenarios.signal_game.server_changes import ServerChange, ServerChangeKind
from glossogen.scenarios.signal_game.shared_server import (
    NodeKind,
    SharedServer,
    home_of,
    is_within,
    name_of,
    parent_of,
)

EventLog = Callable[[EventBase], Awaitable[None]]
Sleeper = Callable[[float], Awaitable[None]]

_INOTIFY_EVENT: dict[ServerChangeKind, str] = {
    ServerChangeKind.WRITE: "MODIFY",
    ServerChangeKind.MKDIR: "CREATE,ISDIR",
    ServerChangeKind.REMOVE: "DELETE",
    ServerChangeKind.CHMOD: "ATTRIB",
    ServerChangeKind.TOUCH: "ATTRIB",
    ServerChangeKind.MOVE: "MOVED_TO",
}


class _ChangeWatcher(NamedTuple):
    """A player in ``inotifywait``, and the future the first matching change resolves."""

    agent_id: str
    path: str
    future: asyncio.Future[str]


def name_text(path: str, author: str) -> WrittenText:
    """The name a node at ``path`` has, as a text the judge reads."""
    return WrittenText(kind=WrittenTextKind.NAME, path=path, author=author, text=name_of(path=path))


def _made_part(path: str, users: tuple[str, ...]) -> str:
    """``path`` below the home or ``/tmp`` it was made in, so the judge reads only names a
    player chose: ``/tmp/r/e/d`` reads ``r/e/d``."""
    for base in ("/tmp", *(home_of(user=user) for user in users)):
        if is_within(path=path, root=base) and path != base:
            return path.removeprefix(base + "/")
    return path.lstrip("/")


def _texts_of(change: ServerChange) -> list[WrittenText]:
    """The texts ``change`` puts on the server: names it creates and content it writes."""
    if change.kind is ServerChangeKind.WRITE:
        texts = [name_text(path=change.path, author=change.actor)]
        if change.content is not None and change.content.strip():
            texts.append(
                WrittenText(
                    kind=WrittenTextKind.CONTENT,
                    path=change.path,
                    author=change.actor,
                    text=change.content,
                )
            )
        return texts
    if change.kind is ServerChangeKind.MKDIR:
        return [name_text(path=change.path, author=change.actor)]
    if change.kind is ServerChangeKind.MOVE and change.destination is not None:
        return [name_text(path=change.destination, author=change.actor)]
    return []


class ServerActivity:
    """The scenario's side of every player's shell."""

    def __init__(
        self, server: SharedServer, log_event: EventLog, round_open: Callable[[int], bool]
    ) -> None:
        self._server = server
        self._log_event = log_event
        self._round_open = round_open
        self._round_texts: list[WrittenText] = []
        self._passed: set[WrittenText] = set()
        self._watchers: list[_ChangeWatcher] = []

    def round_open(self, round_number: int) -> bool:
        """Whether a command line run in ``round_number`` may still act."""
        return self._round_open(round_number)

    def start_round(self) -> None:
        """Forget the texts the previous round's changes put on the server."""
        self._round_texts = []

    def note_changes(self, agent_id: str, changes: list[ServerChange]) -> None:
        """Keep the texts ``changes`` put on the server and wake the partner on them."""
        for change in changes:
            for text in _texts_of(change=change):
                if text not in self._round_texts:
                    self._round_texts.append(text)
            self._wake_watchers(agent_id=agent_id, change=change)

    async def log_changes(
        self, agent_id: str, round_number: int, changes: list[ServerChange]
    ) -> None:
        """Log each change as a ``signal_game_server_changed`` event."""
        for change in changes:
            await self._log_event(
                SignalGameServerChanged(round_number=round_number, agent_id=agent_id, change=change)
            )

    def texts_to_judge(self) -> list[WrittenText]:
        """The round's written texts, then what is on the server, less what the judge passed."""
        texts: list[WrittenText] = []
        for text in [*self._round_texts, *self.texts_on_server()]:
            if text not in texts and text not in self._passed:
                texts.append(text)
        return texts

    def texts_on_server(self) -> list[WrittenText]:
        """Every name and content players have on the server, and each player's paths in
        the order it made them when it has more than one, each below its home or ``/tmp``."""
        texts: list[WrittenText] = []
        for node in self._server.player_nodes():
            texts.append(name_text(path=node.path, author=node.owner))
            if node.kind is NodeKind.FILE and node.content.strip():
                texts.append(
                    WrittenText(
                        kind=WrittenTextKind.CONTENT,
                        path=node.path,
                        author=node.owner,
                        text=node.content,
                    )
                )
        for user in self._server.users:
            paths = [
                _made_part(path=path, users=self._server.users)
                for path in self._server.paths_made_by(user=user)
            ]
            if len(paths) > 1:
                texts.append(
                    WrittenText(
                        kind=WrittenTextKind.NAMES, path="/", author=user, text="\n".join(paths)
                    )
                )
        return texts

    def pass_texts(self, texts: list[WrittenText]) -> None:
        """Remember ``texts`` as passed by the judge, so it is not asked about them again."""
        self._passed.update(texts)

    def replay(self, event: SignalGameServerChanged) -> None:
        """Make a logged change again at the time it was made."""
        self._server.apply(change=event.change, at=event.timestamp)

    async def wait_for_change(
        self, agent_id: str, path: str, timeout_s: float, sleeper: Sleeper
    ) -> str | None:
        """The partner's first change at or below ``path``, or None at the timeout.

        The answer is one ``inotifywait`` line: the directory, the event, the name. A
        change in a directory ``agent_id`` cannot reach does not answer, since the line
        would name it.
        """
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        watcher = _ChangeWatcher(agent_id=agent_id, path=path, future=future)
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

    def _wake_watchers(self, agent_id: str, change: ServerChange) -> None:
        changed_at = change.path
        if change.kind is ServerChangeKind.MOVE and change.destination is not None:
            changed_at = change.destination
        directory = parent_of(path=changed_at)
        line = f"{directory.rstrip('/')}/ {_INOTIFY_EVENT[change.kind]} {name_of(path=changed_at)}"
        for watcher in self._watchers:
            if watcher.agent_id == agent_id or watcher.future.done():
                continue
            if not is_within(path=changed_at, root=watcher.path):
                continue
            if not self._server.exists(user=watcher.agent_id, path=directory):
                continue
            watcher.future.set_result(line)
