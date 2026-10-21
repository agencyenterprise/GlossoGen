"""signal_game_server events: grids, choices, server changes, the judge's reading, results.

Squares are ``[row, col]`` pairs counted from 1, as agents read them.
"""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase
from glossogen.scenarios.signal_game_server.ids import JudgeTool, WrittenTextKind
from glossogen.scenarios.signal_game_server.server_changes import ServerChange


class SignalGameServerRoundStarted(EventBase):
    """Both players' grids for a round, and the square each gets if it does not choose.

    ``fallback_squares`` are drawn at random from the seed and never shown to the players.
    ``colour_orders`` is the order each player's system prompt lists the colours in, the
    same in every round.
    """

    event_type: Literal["signal_game_server_round_started"] = "signal_game_server_round_started"
    round_number: int
    grids: dict[str, list[list[str]]]
    fallback_squares: dict[str, tuple[int, int]]
    partner_colours_visible: bool
    colour_orders: dict[str, list[str]]


class SignalGameServerSquareChosen(EventBase):
    """A player called end_round: the square it chose, its colour, and the call's reasoning.

    ``reasoning`` is None when ``choice_reasoning`` is off.
    """

    event_type: Literal["signal_game_server_square_chosen"] = "signal_game_server_square_chosen"
    round_number: int
    agent_id: str
    square: tuple[int, int]
    colour: str
    reasoning: str | None


class SignalGameServerChanged(EventBase):
    """One change a player's command made to the shared server.

    Replaying these in order, each at its event's timestamp, rebuilds the server
    after a fork.
    """

    event_type: Literal["signal_game_server_changed"] = "signal_game_server_changed"
    round_number: int
    agent_id: str
    change: ServerChange


class SignalGameServerCheat(BaseModel):
    """A text the plaintext judge flagged, of one of the ``WrittenTextKind`` kinds."""

    kind: WrittenTextKind
    path: str
    author: str
    reason: str


class JudgeToolCall(BaseModel):
    """One call the plaintext judge made while reading a round: the tool, what it was given,
    and what it returned."""

    tool: JudgeTool
    input: str
    output: str


class SignalGameServerJudgedText(BaseModel):
    """One text the judge was shown, numbered in the order given here."""

    kind: WrittenTextKind
    path: str
    author: str
    text: str


class SignalGameServerJudged(EventBase):
    """The judge's reading of a round's writes: the texts it was shown, in the order it
    numbered them, the tool calls it made while deciding, and what it flagged."""

    event_type: Literal["signal_game_server_judged"] = "signal_game_server_judged"
    round_number: int
    texts: list[SignalGameServerJudgedText]
    tool_calls: list[JudgeToolCall]
    cheats: list[SignalGameServerCheat]


class SignalGameServerRoundResolved(EventBase):
    """Where each player ended, on which colour, and whether the round scored.

    ``success`` needs the colours to match and ``cheats`` to be empty.
    """

    event_type: Literal["signal_game_server_round_resolved"] = "signal_game_server_round_resolved"
    round_number: int
    final_squares: dict[str, tuple[int, int]]
    final_colours: dict[str, str]
    success: bool
    trigger: str
    cheats: list[SignalGameServerCheat]
