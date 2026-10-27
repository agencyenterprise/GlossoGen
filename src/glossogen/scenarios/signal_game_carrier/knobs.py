"""Knobs for signal_game_carrier: the grids, the song's shape, the channel's limits and
how much the players are told."""

from typing import Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.signal_game_carrier.ids import PALETTE, PromptDetail


class SignalGameCarrierKnobs(BaseKnobs):
    """The factors of one signal_game_carrier run.

    Each player's grid is ``grid_size`` squares on a side, each square coloured from the
    first ``colour_count`` colours of the palette. Each round's song is ``song_length``
    whole numbers: a motif of ``motif_length`` values between ``-song_amplitude`` and
    ``song_amplitude``, looped. A player's noise is clipped to ``±max_volume`` per tick,
    and the recording is the song plus both players' noise plus Gaussian channel noise of
    ``channel_noise_sigma``, rounded. Both players read the song, so a player separates
    its partner's noise from the recording by subtracting the song and its own noise.
    ``prompt_detail`` picks the wording of everything the players read: ``full``
    explains the mechanics, ``lean`` leaves them to be found out.
    """

    grid_size: int = Field(ge=2, le=5)
    colour_count: int = Field(ge=2, le=len(PALETTE))
    song_length: int = Field(ge=8, le=512)
    motif_length: int = Field(ge=2, le=64)
    song_amplitude: int = Field(ge=1, le=100)
    max_volume: int = Field(ge=1, le=100)
    channel_noise_sigma: float = Field(ge=0.0, le=100.0)
    prompt_detail: PromptDetail
    seed: int

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse a debrief channel, compaction, a motif longer than the song and a
        palette larger than a grid."""
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt talks "
                "about channels, and this scenario has none"
            )
        if self.motif_length > self.song_length:
            raise ValueError("motif_length cannot exceed song_length")
        if self.colour_count > self.grid_size * self.grid_size:
            raise ValueError("colour_count cannot exceed the number of squares in a grid")
        return self
