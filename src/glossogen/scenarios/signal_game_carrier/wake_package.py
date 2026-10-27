"""What a resumed ``read_notifications`` call returns to a signal_game_carrier player."""

from typing import Literal

from pydantic import BaseModel


class SignalGameCarrierWake(BaseModel):
    """One wake: why it happened, any briefing, and any notice.

    ``type`` is ``done`` once the game is over. ``notice`` is the scenario's text when it
    released the player from a wait: the recording is ready, or nothing will arrive until
    the player transmits.
    """

    type: Literal["wake", "done"]
    round: int
    wake_reasons: list[str]
    briefings: list[str]
    notice: str | None
