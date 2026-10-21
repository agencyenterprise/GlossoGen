"""One player's ``run_command`` under the ``file_system`` medium.

Each command line runs in a fresh bash in the server container as the player, under
the command timeout. Afterwards the server is snapshotted and diffed against the last
snapshot, so the changes the line made are logged and the plaintext judge learns the
texts it wrote; a line that takes a player past its quota is undone by restoring the
snapshot before it, and the player reads why. The snapshot and diff run under one
lock shared by both players, so a change is logged once, attributed to the owner of
the node it touched.
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
        self, snapshot: ServerSnapshot, container: ServerContainer, activity: ServerActivity
    ) -> None:
        self.snapshot = snapshot
        self._container = container
        self._activity = activity
        self._lock = asyncio.Lock()

    async def record(self, round_number: int) -> str | None:
        """Snapshot the server, log what changed since the last snapshot, and enforce the quota.

        Returns the note a player reads when its command was undone, else None.
        """
        async with self._lock:
            after = await self._container.snapshot()
            breach = after.quota_breach()
            if breach is not None:
                await self._container.restore(snapshot=self.snapshot)
                return (
                    f"bash: the command was undone: it left {breach.user} with {breach.reason}, "
                    "past the server's limit.\n"
                )
            await self._activity.record(
                before=self.snapshot, after=after, round_number=round_number
            )
            self.snapshot = after
            return None


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
        undone = await self._state.record(round_number=round_number)
        if not self._round_open(round_number):
            return _round_ended(round_number=round_number, char_limit=self._output_char_limit)
        stderr = output.stderr
        if output.timed_out:
            stderr += (
                f"bash: killed after {self._timeout_s:g} seconds, the most one command line "
                "may run.\n"
            )
        if undone is not None:
            stderr += undone
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
