"""Knobs for carrier_song: the song's shape, the noise limits, the code's length and how
much the players are told."""

from typing import Self

from pydantic import Field, model_validator

from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.scenarios.carrier_song.ids import PromptDetail


class CarrierSongKnobs(BaseKnobs):
    """The factors of one carrier_song run.

    Each round's song is ``song_length`` whole numbers: a motif of ``motif_length``
    values between ``-song_amplitude`` and ``song_amplitude``, looped. The sender's
    noise is clipped to ``±max_volume`` per tick, and the receiver hears the song
    plus that noise plus Gaussian channel noise of ``channel_noise_sigma``, rounded.
    The secret is a code of ``code_length`` capital letters and digits.
    ``receiver_sees_song`` shows the receiver the song under the recording, which
    turns decoding into a subtraction. ``prompt_detail`` picks the wording of
    everything the players read: ``full`` explains the mechanics, ``lean`` leaves
    them to be found out.
    """

    song_length: int = Field(ge=8, le=512)
    motif_length: int = Field(ge=2, le=64)
    song_amplitude: int = Field(ge=1, le=100)
    max_volume: int = Field(ge=1, le=100)
    channel_noise_sigma: float = Field(ge=0.0, le=100.0)
    code_length: int = Field(ge=1, le=32)
    receiver_sees_song: bool
    prompt_detail: PromptDetail
    seed: int

    @model_validator(mode="after")
    def _validate_combinations(self) -> Self:
        """Refuse a debrief channel, compaction, and a motif longer than the song."""
        if self.postmortem_enabled:
            raise ValueError("postmortem_enabled must be false: a debrief is a channel")
        if self.compaction.enabled:
            raise ValueError(
                "compaction.enabled must be false: the platform's compaction prompt talks "
                "about channels, and this scenario has none"
            )
        if self.motif_length > self.song_length:
            raise ValueError("motif_length cannot exceed song_length")
        return self
