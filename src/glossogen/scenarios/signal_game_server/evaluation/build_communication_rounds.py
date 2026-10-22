"""signal_game_server's implementation of ``SimulationScenario.build_communication_rounds``.

There are no messages, so a round's "messages" are each player's server trace: one line
per player listing, in order, the changes its commands made to the shared server. The
ground truth is both grids, the square each player chose, and any texts the judge
flagged.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game_server.events import (
    SignalGameServerChanged,
    SignalGameServerRoundResolved,
    SignalGameServerRoundStarted,
)
from glossogen.scenarios.signal_game_server.server_changes import ServerChange, ServerChangeKind

FILES_CHANNEL = "files"
"""The label a trace of shared-server changes carries in place of a channel id."""


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """One view per started round, holding each player's server trace."""
    started = {
        event.round_number: event
        for event in events
        if isinstance(event, SignalGameServerRoundStarted)
    }
    resolved = {
        event.round_number: event
        for event in events
        if isinstance(event, SignalGameServerRoundResolved)
    }
    traces: dict[int, dict[str, list[str]]] = {}
    for event in events:
        if isinstance(event, SignalGameServerChanged):
            traces.setdefault(event.round_number, {}).setdefault(event.agent_id, []).append(
                _change_entry(change=event.change)
            )
    return [
        CommunicationRoundView(
            round_number=round_number,
            header=f"round {round_number}",
            ground_truth_block=_ground_truth(
                started=round_started, resolved=resolved.get(round_number)
            ),
            messages=[
                CommunicationMessageLine(
                    sender_agent_id=agent_id, channel_id=FILES_CHANNEL, text=" | ".join(changes)
                )
                for agent_id, changes in sorted(traces.get(round_number, {}).items())
            ],
        )
        for round_number, round_started in sorted(started.items())
    ]


def _change_entry(change: ServerChange) -> str:
    """One server change as a trace entry, such as ``chmod 0640 /tmp/a``."""
    if change.kind is ServerChangeKind.CHMOD and change.mode is not None:
        return f"chmod {change.mode:04o} {change.path}"
    if change.kind is ServerChangeKind.WRITE and change.content is not None:
        return f"write {change.path} {change.content!r}"
    return f"{change.kind.value} {change.path}"


def _ground_truth(
    started: SignalGameServerRoundStarted, resolved: SignalGameServerRoundResolved | None
) -> str:
    """Both grids, row by row, the square each player chose, and any flagged texts."""
    lines: list[str] = []
    for agent_id, grid in sorted(started.grids.items()):
        rows = " / ".join(" ".join(row) for row in grid)
        lines.append(f"{agent_id} grid (rows top to bottom): {rows}")
    if resolved is not None:
        for agent_id, square in sorted(resolved.final_squares.items()):
            lines.append(
                f"{agent_id} finished on r{square[0]}c{square[1]} "
                f"({resolved.final_colours[agent_id]})"
            )
        for cheat in resolved.cheats:
            lines.append(
                f"judge flagged the {cheat.kind.value} of {cheat.path} ({cheat.author}) as "
                f"written coordination: {cheat.reason}"
            )
        lines.append(f"round success: {resolved.success}")
    visibility = "only their own grid's colours"
    if started.partner_colours_visible:
        visibility = "both grids' colours"
    lines.append(
        f"Each player names its square in end_round and sees {visibility}; neither sees "
        "the other's choice. Both are users of one shared server. A files message lists "
        "the changes one player's commands made to the server, in order."
    )
    return "\n".join(lines)
