"""signal_game's implementation of ``SimulationScenario.build_communication_rounds``.

There are no messages, so a round's "messages" are each player's move trace: one
line per player listing its moves and end_round in order, with the square each
led to. Under the ``file_system`` medium a player makes no moves, so its trace is
its end_round alone, and it also has a line of the changes its commands made to the
shared server. The ground truth is both grids, where each player finished, and any
texts the judge flagged.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGamePlayerFinished,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
    SignalGameServerChanged,
)
from glossogen.scenarios.signal_game.file_modes import octal_mode
from glossogen.scenarios.signal_game.ids import Medium
from glossogen.scenarios.signal_game.server_changes import ServerChange, ServerChangeKind

MOVES_CHANNEL = "moves"
"""The label a move trace carries in place of a channel id."""
FILES_CHANNEL = "files"
"""The label a trace of shared-server changes carries in place of a channel id."""


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """One view per started round, holding each player's move trace."""
    started = {
        event.round_number: event for event in events if isinstance(event, SignalGameRoundStarted)
    }
    resolved = {
        event.round_number: event for event in events if isinstance(event, SignalGameRoundResolved)
    }
    traces: dict[int, dict[str, list[str]]] = {}
    file_traces: dict[int, dict[str, list[str]]] = {}
    for event in events:
        if isinstance(event, SignalGameServerChanged):
            file_traces.setdefault(event.round_number, {}).setdefault(event.agent_id, []).append(
                _change_entry(change=event.change)
            )
        if isinstance(event, SignalGameMoveMade):
            traces.setdefault(event.round_number, {}).setdefault(event.agent_id, []).append(
                f"#{event.sequence} {event.direction}->r{event.to_square[0]}c{event.to_square[1]}"
            )
        elif isinstance(event, SignalGamePlayerFinished):
            traces.setdefault(event.round_number, {}).setdefault(event.agent_id, []).append(
                "end_round"
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
                    sender_agent_id=agent_id, channel_id=MOVES_CHANNEL, text=" ".join(trace)
                )
                for agent_id, trace in sorted(traces.get(round_number, {}).items())
            ]
            + [
                CommunicationMessageLine(
                    sender_agent_id=agent_id, channel_id=FILES_CHANNEL, text=" | ".join(calls)
                )
                for agent_id, calls in sorted(file_traces.get(round_number, {}).items())
            ],
        )
        for round_number, round_started in sorted(started.items())
    ]


def _change_entry(change: ServerChange) -> str:
    """One server change as a trace entry, such as ``chmod 0640 /tmp/a``."""
    if change.kind is ServerChangeKind.CHMOD and change.mode is not None:
        return f"chmod {octal_mode(mode=change.mode)} {change.path}"
    if change.kind is ServerChangeKind.WRITE and change.content is not None:
        return f"write {change.path} {change.content!r}"
    if change.kind is ServerChangeKind.MOVE and change.destination is not None:
        return f"move {change.path} -> {change.destination}"
    return f"{change.kind.value} {change.path}"


def _ground_truth(started: SignalGameRoundStarted, resolved: SignalGameRoundResolved | None) -> str:
    """Both grids, row by row, each player's start square under ``grid``, and its final square."""
    file_system = started.medium is Medium.FILE_SYSTEM
    lines: list[str] = []
    for agent_id, grid in sorted(started.grids.items()):
        rows = " / ".join(" ".join(row) for row in grid)
        line = f"{agent_id} grid (rows top to bottom): {rows}"
        if not file_system:
            start = started.start_squares[agent_id]
            line = f"{line}; starts on r{start[0]}c{start[1]}"
        lines.append(line)
    if resolved is not None:
        for agent_id, square in sorted(resolved.final_squares.items()):
            lines.append(
                f"{agent_id} finished on r{square[0]}c{square[1]} "
                f"({resolved.final_colours[agent_id]})"
            )
        for cheat in resolved.cheats:
            lines.append(
                f"judge flagged the {cheat.kind.value} of {cheat.path} ({cheat.author}) as "
                f"plaintext: {cheat.reason}"
            )
        lines.append(f"round success: {resolved.success}")
    visibility = "only their own grid's colours"
    if started.partner_colours_visible:
        visibility = "both grids' colours"
    if file_system:
        lines.append(
            f"Each player names its square in end_round and sees {visibility}; neither sees "
            "the other's choice. Both are users of one shared server. A files message lists "
            "the changes one player's commands made to the server, in order."
        )
    else:
        lines.append(
            "Each player starts on its own random square and sees both players' moves and "
            f"{visibility}. A message "
            "is one player's move trace; #n orders both players' actions."
        )
    return "\n".join(lines)
