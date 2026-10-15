"""What a resumed ``read_notifications`` call returns to a signal_game player."""

from typing import Literal

from pydantic import BaseModel


class SignalGameWake(BaseModel):
    """One wake: why it happened, any briefing, the board, and any notice.

    ``type`` is ``done`` once the game is over. ``board`` is the current board
    with the partner's actions since the player last looked, or None between
    rounds. ``notice`` is the scenario's text when it released the player from a
    wait.
    """

    type: Literal["wake", "done"]
    round: int
    wake_reasons: list[str]
    briefings: list[str]
    board: str | None
    notice: str | None
