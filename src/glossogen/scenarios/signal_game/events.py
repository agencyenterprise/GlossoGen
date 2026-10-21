"""signal_game's events: each round's grids, every move, each player's finish and the verdict.

Squares are ``[row, col]`` pairs counted from 1, as agents read them.
"""

from typing import Any, Literal, cast

from pydantic import BaseModel, model_validator

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game.ids import Medium, WrittenTextKind
from glossogen.scenarios.signal_game.server_changes import ServerChange


class SignalGameRoundStarted(EventBase):
    """A round's grids and start squares; no agent sees both grids unless colours are shared.

    ``colour_orders`` is the order each player's system prompt lists the colours in, the
    same in every round. None in a log whose players both read the palette's order.
    ``medium`` is what each player perceives of the other; ``grid`` in a log that does
    not record it.
    """

    event_type: Literal["signal_game_round_started"] = "signal_game_round_started"
    round_number: int
    grids: dict[str, list[list[str]]]
    start_squares: dict[str, tuple[int, int]]
    moves_per_round: int
    partner_colours_visible: bool
    colour_orders: dict[str, list[str]] | None = None
    medium: Medium = Medium.GRID

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
    """One accepted move. ``sequence`` orders both players' moves within the round.

    ``reasoning`` is the sentence the player gave with the move call, the same on
    every step of that call, and never shown to the partner. None when the run's
    ``move_reasoning`` is off, and in runs recorded before ``move`` took one.
    """

    event_type: Literal["signal_game_move_made"] = "signal_game_move_made"
    round_number: int
    agent_id: str
    sequence: int
    direction: str
    from_square: tuple[int, int]
    to_square: tuple[int, int]
    moves_used: int
    reasoning: str | None = None


class SignalGamePlayerFinished(EventBase):
    """A player called end_round; its square is final for the round.

    ``reasoning`` is the sentence the player gave with end_round, never shown to the
    partner. None when the run's ``move_reasoning`` is off, and in runs recorded
    before end_round took one.
    """

    event_type: Literal["signal_game_player_finished"] = "signal_game_player_finished"
    round_number: int
    agent_id: str
    square: tuple[int, int]
    colour: str
    moves_used: int
    reasoning: str | None = None


class SignalGameServerChanged(EventBase):
    """One change a player's command made to the shared server under the ``file_system`` medium.

    Replaying these in order, each at its event's timestamp, rebuilds the server
    after a fork.
    """

    event_type: Literal["signal_game_server_changed"] = "signal_game_server_changed"
    round_number: int
    agent_id: str
    change: ServerChange


class SignalGameCheat(BaseModel):
    """A text the plaintext judge flagged, of one of the ``WrittenTextKind`` kinds."""

    kind: WrittenTextKind
    path: str
    author: str
    reason: str


class SignalGamePlaintextJudged(EventBase):
    """The judge's reading of a round's writes: how many texts it read and what it flagged."""

    event_type: Literal["signal_game_plaintext_judged"] = "signal_game_plaintext_judged"
    round_number: int
    texts_judged: int
    cheats: list[SignalGameCheat]


class SignalGameRoundResolved(EventBase):
    """Where each player ended, on which colour, and whether the round scored.

    ``success`` needs the colours to match and ``cheats`` to be empty. ``cheats`` is
    empty in a log that does not record it.
    """

    event_type: Literal["signal_game_round_resolved"] = "signal_game_round_resolved"
    round_number: int
    final_squares: dict[str, tuple[int, int]]
    final_colours: dict[str, str]
    moves_used: dict[str, int]
    success: bool
    trigger: str
    cheats: list[SignalGameCheat] = []
