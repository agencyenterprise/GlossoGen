"""What a resumed ``read_notifications`` call returns to a move_a_box operator."""

from typing import Literal

from pydantic import BaseModel


class MoveABoxWake(BaseModel):
    """One wake: why it happened, any briefing, the depot readout, and any notice.

    ``type`` is ``done`` once the run is over. ``readout`` is the readout as it
    stands, or None between rounds. ``notice`` is the scenario's text when it
    released the operator from a wait.
    """

    type: Literal["wake", "done"]
    round: int
    wake_reasons: list[str]
    briefings: list[str]
    readout: str | None
    notice: str | None
