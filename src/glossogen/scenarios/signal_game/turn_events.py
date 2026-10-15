"""The events one turn of signal_game's log produces."""

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.board import Square, colour_at
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGamePlayerFinished,
    SignalGameTurnPassed,
)
from glossogen.scenarios.signal_game.ids import TurnKind
from glossogen.scenarios.signal_game.world import Turn


def _pair(square: Square) -> tuple[int, int]:
    return (square.row, square.col)


def turn_events(
    round_number: int, turn: Turn, moves_used: int, grid: list[list[str]]
) -> list[EventBase]:
    """One ``SignalGameMoveMade`` per step of a move, or the finish or pass event.

    ``moves_used`` is the player's count after the turn, and ``grid`` its grid,
    from which a finish reads its colour.
    """
    if turn.kind is TurnKind.FINISH:
        return [
            SignalGamePlayerFinished(
                round_number=round_number,
                agent_id=turn.agent_id,
                square=_pair(square=turn.square),
                colour=colour_at(grid=grid, square=turn.square),
                moves_used=moves_used,
            )
        ]
    if turn.kind is TurnKind.WAIT:
        return [
            SignalGameTurnPassed(
                round_number=round_number,
                agent_id=turn.agent_id,
                turn_number=turn.number,
                square=_pair(square=turn.square),
            )
        ]
    first_move = moves_used - len(turn.steps) + 1
    return [
        SignalGameMoveMade(
            round_number=round_number,
            agent_id=turn.agent_id,
            sequence=applied.sequence,
            direction=applied.direction.value,
            from_square=_pair(square=applied.from_square),
            to_square=_pair(square=applied.square),
            moves_used=first_move + index,
        )
        for index, applied in enumerate(turn.steps)
    ]
