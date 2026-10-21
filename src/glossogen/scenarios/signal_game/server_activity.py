"""What the players do to the shared server, as the scenario keeps track of it.

``ServerActivity`` turns each snapshot diff into ``signal_game_server_changed`` events,
keeps the texts the round's changes put on the server and the texts the plaintext
judge already passed, and reads the texts a snapshot holds.
"""

from collections.abc import Awaitable, Callable

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.events import SignalGameServerChanged
from glossogen.scenarios.signal_game.ids import WrittenTextKind
from glossogen.scenarios.signal_game.judged_text import WrittenText
from glossogen.scenarios.signal_game.server_changes import ServerChange, ServerChangeKind
from glossogen.scenarios.signal_game.server_snapshot import (
    NodeKind,
    ServerSnapshot,
    diff_snapshots,
    name_of,
)

EventLog = Callable[[EventBase], Awaitable[None]]


def name_text(path: str, author: str) -> WrittenText:
    """The name a node at ``path`` has, as a text the judge reads."""
    return WrittenText(kind=WrittenTextKind.NAME, path=path, author=author, text=name_of(path=path))


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
    return []


def texts_on(snapshot: ServerSnapshot) -> list[WrittenText]:
    """Every name and content players have on the server, in path order."""
    texts: list[WrittenText] = []
    for path, node in snapshot.player_nodes():
        texts.append(name_text(path=path, author=node.owner))
        if node.kind is NodeKind.FILE and node.content.strip():
            texts.append(
                WrittenText(
                    kind=WrittenTextKind.CONTENT, path=path, author=node.owner, text=node.content
                )
            )
    return texts


class ServerActivity:
    """The scenario's record of what the players changed and what the judge has read."""

    def __init__(self, log_event: EventLog) -> None:
        self._log_event = log_event
        self._round_texts: list[WrittenText] = []
        self._passed: set[WrittenText] = set()

    def start_round(self) -> None:
        """Forget the texts the previous round's changes put on the server."""
        self._round_texts = []

    async def record(
        self, before: ServerSnapshot, after: ServerSnapshot, round_number: int
    ) -> None:
        """Log the changes from ``before`` to ``after`` and keep the texts they wrote."""
        for change in diff_snapshots(before=before, after=after):
            for text in _texts_of(change=change):
                if text not in self._round_texts:
                    self._round_texts.append(text)
            await self._log_event(
                SignalGameServerChanged(
                    round_number=round_number, agent_id=change.actor, change=change
                )
            )

    def texts_to_judge(self, snapshot: ServerSnapshot) -> list[WrittenText]:
        """The round's written texts, then what ``snapshot`` holds, less what the judge passed."""
        texts: list[WrittenText] = []
        for text in [*self._round_texts, *texts_on(snapshot=snapshot)]:
            if text not in texts and text not in self._passed:
                texts.append(text)
        return texts

    def pass_texts(self, texts: list[WrittenText]) -> None:
        """Remember ``texts`` as passed by the judge, so it is not asked about them again."""
        self._passed.update(texts)
