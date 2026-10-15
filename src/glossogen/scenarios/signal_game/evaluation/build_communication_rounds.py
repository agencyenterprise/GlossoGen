"""signal_game's implementation of ``SimulationScenario.build_communication_rounds``.

There are no messages, so a round's "messages" are each player's move trace: one
line per player listing its moves and end_round in order, with the square each
led to. The ground truth is both grids and where each player finished.
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
)

MOVES_CHANNEL = "moves"
"""The label a move trace carries in place of a channel id."""


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """One view per started round, holding each player's move trace."""
    started = {
        event.round_number: event for event in events if isinstance(event, SignalGameRoundStarted)
    }
    resolved = {
        event.round_number: event for event in events if isinstance(event, SignalGameRoundResolved)
    }
    traces: dict[int, dict[str, list[str]]] = {}
    for event in events:
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
            ],
        )
        for round_number, round_started in sorted(started.items())
    ]


def _ground_truth(started: SignalGameRoundStarted, resolved: SignalGameRoundResolved | None) -> str:
    """Both grids, row by row, and each player's start and final square."""
    lines: list[str] = []
    for agent_id, grid in sorted(started.grids.items()):
        rows = " / ".join(" ".join(row) for row in grid)
        start = started.start_squares[agent_id]
        lines.append(
            f"{agent_id} grid (rows top to bottom): {rows}; starts on r{start[0]}c{start[1]}"
        )
    if resolved is not None:
        for agent_id, square in sorted(resolved.final_squares.items()):
            lines.append(
                f"{agent_id} finished on r{square[0]}c{square[1]} "
                f"({resolved.final_colours[agent_id]})"
            )
        lines.append(f"round success: {resolved.success}")
    visibility = "only their own grid's colours"
    if started.partner_colours_visible:
        visibility = "both grids' colours"
    lines.append(
        "Each player starts on its own random square and sees both players' moves and "
        f"{visibility}. A message "
        "is one player's move trace; #n orders both players' actions."
    )
    return "\n".join(lines)
