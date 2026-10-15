"""Knobs for signal_game: grid shape, palette, move budget and colour visibility."""

from typing import Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.signal_game.ids import PALETTE


class SignalGameKnobs(BaseKnobs):
    """The factors of one embodied-signalling run.

    Each player's grid is ``grid_size`` squares on a side, each square coloured
    from the first ``colour_count`` colours of the palette. ``moves_per_round``
    caps the moves (``stay`` included) one player makes in a round.
    ``partner_colours_visible`` shows each player the partner's colours too,
    which removes the private information and is the control condition.
    ``observe_enabled`` offers the ``observe`` tool, which shows every partner
    action of the round without spending a move.
    """

    grid_size: int = Field(ge=2, le=5)
    colour_count: int = Field(ge=2, le=len(PALETTE))
    moves_per_round: int = Field(ge=1, le=1000)
    partner_colours_visible: bool
    observe_enabled: bool
    seed: int

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse a debrief channel, compaction, and a grid too small for its palette."""
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt talks "
                "about channels, and this scenario has none"
            )
        if self.colour_count > self.grid_size * self.grid_size:
            raise ValueError("colour_count cannot exceed the number of squares in a grid")
        return self
