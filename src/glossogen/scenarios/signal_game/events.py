"""signal_game's events: each round's grids, every move, each player's finish and the verdict.

Squares are ``[row, col]`` pairs counted from 1, as agents read them.
"""

from typing import Any, Literal, cast

from pydantic import model_validator

from glossogen.models.event_base import EventBase


class SignalGameRoundStarted(EventBase):
    """A round's grids and start squares; no agent sees both grids unless colours are shared."""

    event_type: Literal["signal_game_round_started"] = "signal_game_round_started"
    round_number: int
    grids: dict[str, list[list[str]]]
    start_squares: dict[str, tuple[int, int]]
    moves_per_round: int
    partner_colours_visible: bool

    @model_validator(mode="before")
    @classmethod
    def _backfill_start_squares(cls, data: Any) -> Any:
        """Runs from before random starts logged one ``start_square`` shared by both players."""
        if not isinstance(data, dict):
            return data
        typed = cast(dict[str, Any], data)
        if "start_squares" in typed or "start_square" not in typed:
            return typed
        grids = cast(dict[str, Any], typed.get("grids", {}))
        return {**typed, "start_squares": dict.fromkeys(grids, typed["start_square"])}


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
    """A player called end_round; its square is final for the round."""

    event_type: Literal["signal_game_player_finished"] = "signal_game_player_finished"
    round_number: int
    agent_id: str
    square: tuple[int, int]
    colour: str
    moves_used: int


class SignalGameRoundResolved(EventBase):
    """Where each player ended, on which colour, and whether the colours matched."""

    event_type: Literal["signal_game_round_resolved"] = "signal_game_round_resolved"
    round_number: int
    final_squares: dict[str, tuple[int, int]]
    final_colours: dict[str, str]
    moves_used: dict[str, int]
    success: bool
    trigger: str
