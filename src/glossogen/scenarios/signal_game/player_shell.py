"""One player's ``run_command`` under the ``file_system`` medium.

Each command line runs in a fresh bash in the server container as the player, under
the command timeout, and whatever it left running is killed when it returns.
Afterwards the server is snapshotted and diffed against the last snapshot, so the
changes the line made are logged and the plaintext judge learns the texts it wrote.
A line that leaves a player past its quota, or with a FIFO, socket or device, is
undone for that player alone: that player's nodes go back to the last snapshot, the
other player's changes stand, and the player reads why on its next result. The
snapshot and diff run under one lock shared by both players, so a change is logged
once, attributed to the owner of the node it touched. Nothing is recorded once the
round is closing, except by the round end itself.
"""

import asyncio
from collections.abc import Callable

from glossogen.scenarios.signal_game.server_activity import ServerActivity
from glossogen.scenarios.signal_game.server_container import ExecOutput, ServerContainer
from glossogen.scenarios.signal_game.server_snapshot import ServerSnapshot

ROUND_ENDED_EXIT_STATUS = 1


class ServerState:
    """The last snapshot the shells diff against, and how a new one is taken and recorded."""

    def __init__(
        self,
        snapshot: ServerSnapshot,
        container: ServerContainer,
        activity: ServerActivity,
        round_open: Callable[[int], bool],
    ) -> None:
        self.snapshot = snapshot
        self._container = container
        self._activity = activity
        self._round_open = round_open
        self._lock = asyncio.Lock()
        self._notices: dict[str, str] = {}

    async def record(self, round_number: int) -> None:
        """Snapshot the server, log what changed since the last snapshot, enforce the quota.

        Nothing happens once ``round_number`` is closing. A breach undoes the
        breaching player's changes, keeps the other's, and leaves that player a
        notice for ``take_notice``.
        """
        async with self._lock:
            if not self._round_open(round_number):
                return
            await self._record_locked(round_number=round_number)

    async def record_closing(self, round_number: int) -> None:
        """What the round end calls once the players' processes are killed: record the last
        changes of ``round_number`` although it is closing."""
        async with self._lock:
            await self._record_locked(round_number=round_number)

    async def _record_locked(self, round_number: int) -> None:
        after = await self._container.snapshot()
        breach = after.quota_breach()
        if breach is not None:
            after = _without_changes_by(before=self.snapshot, after=after, user=breach.user)
            await self._container.restore(snapshot=after)
            self._notices[breach.user] = (
                f"bash: your command was undone: it left you with {breach.reason}, past "
                "the server's limit.\n"
            )
        await self._activity.record(before=self.snapshot, after=after, round_number=round_number)
        self.snapshot = after

    def take_notice(self, user: str) -> str:
        """The notice waiting for ``user``, once; empty when there is none."""
        return self._notices.pop(user, "")


def _without_changes_by(before: ServerSnapshot, after: ServerSnapshot, user: str) -> ServerSnapshot:
    """``after`` with every node ``user`` owns put back as it was in ``before``."""
    nodes = {path: node for path, node in after.nodes.items() if node.owner != user}
    nodes.update({path: node for path, node in before.nodes.items() if node.owner == user})
    return ServerSnapshot(users=after.users, nodes=nodes, specials=[])


class PlayerShell:
    """``user``'s commands on ``container``, recorded through ``state``."""

    def __init__(
        self,
        container: ServerContainer,
        user: str,
        state: ServerState,
        round_open: Callable[[int], bool],
        timeout_s: float,
        output_char_limit: int,
    ) -> None:
        self._container = container
        self._user = user
        self._state = state
        self._round_open = round_open
        self._timeout_s = timeout_s
        self._output_char_limit = output_char_limit

    async def run(self, command: str, round_number: int) -> str:
        """Run ``command`` as part of ``round_number`` and return what the player reads."""
        if not self._round_open(round_number):
            return _round_ended(round_number=round_number, char_limit=self._output_char_limit)
        output = await self._container.exec_as(
            user=self._user,
            command=command,
            timeout_s=self._timeout_s,
            output_bytes=self._output_char_limit,
        )
        if not self._round_open(round_number):
            return _round_ended(round_number=round_number, char_limit=self._output_char_limit)
        await self._state.record(round_number=round_number)
        stderr = output.stderr
        if output.timed_out:
            stderr += (
                f"bash: killed after {self._timeout_s:g} seconds, the most one command line "
                "may run.\n"
            )
        stderr += self._state.take_notice(user=self._user)
        return format_output(
            output=ExecOutput(
                stdout=output.stdout,
                stderr=stderr,
                exit_status=output.exit_status,
                timed_out=output.timed_out,
            ),
            char_limit=self._output_char_limit,
        )


def _round_ended(round_number: int, char_limit: int) -> str:
    return format_output(
        output=ExecOutput(
            stdout="",
            stderr=(
                f"bash: round {round_number} ended while this command line ran, so it was "
                "stopped and its output was discarded. Call "
                "read_notifications(wait_for='next_round').\n"
            ),
            exit_status=ROUND_ENDED_EXIT_STATUS,
            timed_out=False,
        ),
        char_limit=char_limit,
    )


def format_output(output: ExecOutput, char_limit: int) -> str:
    """What the player reads: stdout, stderr, a non-zero exit status, within ``char_limit``.

    Past the limit stdout is cut and marked as cut. Stderr and the status are kept
    whole when they fit, so an error printed after a long output stays visible.
    """
    trailer = output.stderr
    if output.exit_status != 0:
        trailer += f"[exit status {output.exit_status}]\n"
    text = output.stdout + trailer
    if text == "":
        return "(no output)"
    if len(text) <= char_limit:
        return text
    cut_note = f"\n[output cut at {char_limit} characters]"
    room = char_limit - len(trailer)
    if trailer == "" or room <= 0:
        return text[:char_limit] + cut_note
    return output.stdout[:room] + cut_note + "\n" + trailer
