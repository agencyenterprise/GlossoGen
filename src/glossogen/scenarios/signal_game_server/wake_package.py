"""What a resumed ``read_notifications`` call returns to a signal_game_server player."""

from typing import Literal

from pydantic import BaseModel


class SignalGameServerWake(BaseModel):
    """One wake: why it happened, any briefing, the board, and any notice.

    ``type`` is ``done`` once the game is over. ``board`` is the player's own board,
    or None between rounds. ``notice`` is the scenario's text when it cut a wait short.
    """

    type: Literal["wake", "done"]
    round: int
    wake_reasons: list[str]
    briefings: list[str]
    board: str | None
    notice: str | None
