"""signal_game's events: each round's grids, every move, each player's finish and the verdict.

Squares are ``[row, col]`` pairs counted from 1, as agents read them.
"""

from typing import Literal

from glossogen.models.event_base import EventBase


class SignalGameRoundStarted(EventBase):
    """Both grids of a round, which no agent sees whole unless colours are shared."""

    event_type: Literal["signal_game_round_started"] = "signal_game_round_started"
    round_number: int
    grids: dict[str, list[list[str]]]
    start_square: tuple[int, int]
    moves_per_round: int
    partner_colours_visible: bool


class SignalGameMoveMade(EventBase):
    """One accepted move. ``sequence`` orders both players' moves within the round."""

    event_type: Literal["signal_game_move_made"] = "signal_game_move_made"
    round_number: int
    agent_id: str
    sequence: int
    direction: str
    from_square: tuple[int, int]
    to_square: tuple[int, int]
    moves_used: int


class SignalGamePlayerFinished(EventBase):
    """A player waited for the next round, so its square is final for the round."""

    event_type: Literal["signal_game_player_finished"] = "signal_game_player_finished"
    round_number: int
    agent_id: str
    square: tuple[int, int]
    colour: str
    moves_used: int


class SignalGameTurnPassed(EventBase):
    """Under ``turn_based``, a player waited on its own turn and handed it to its partner.

    ``turn_number`` counts the player's own turns in the round, the pass included.
    """

    event_type: Literal["signal_game_turn_passed"] = "signal_game_turn_passed"
    round_number: int
    agent_id: str
    turn_number: int
    square: tuple[int, int]


class SignalGameRoundResolved(EventBase):
    """Where each player ended, on which colour, and whether the colours matched."""

    event_type: Literal["signal_game_round_resolved"] = "signal_game_round_resolved"
    round_number: int
    final_squares: dict[str, tuple[int, int]]
    final_colours: dict[str, str]
    moves_used: dict[str, int]
    success: bool
    trigger: str
