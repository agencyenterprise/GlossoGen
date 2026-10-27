"""signal_game_carrier's events: each round's material, every executor run, each
transmission, the recording, the squares picked and the verdict."""

from typing import Literal

from glossogen.models.event_base import EventBase


class SignalGameCarrierRoundStarted(EventBase):
    """A round's grids, song and channel noise. Each grid is private to its player."""

    event_type: Literal["signal_game_carrier_round_started"] = "signal_game_carrier_round_started"
    round_number: int
    grids: dict[str, list[list[str]]]
    song: list[int]
    channel_noise: list[int]


class SignalGameCarrierExecutorRan(EventBase):
    """One run of a player's executor on the round's song.

    ``written`` is true when the run tested code just passed to write_executor, and false
    when the executor in place ran on a new song. ``accepted`` says whether the run
    returned usable noise; a written executor that is not accepted does not replace the
    one in place. ``noise`` is the noise after clipping, None when not accepted, and
    ``error`` says why not.
    """

    event_type: Literal["signal_game_carrier_executor_ran"] = "signal_game_carrier_executor_ran"
    round_number: int
    agent_id: str
    code: str
    written: bool
    accepted: bool
    noise: list[int] | None
    clipped_ticks: int
    error: str | None


class SignalGameCarrierTransmitted(EventBase):
    """One player fixed its noise for the round."""

    event_type: Literal["signal_game_carrier_transmitted"] = "signal_game_carrier_transmitted"
    round_number: int
    agent_id: str
    noise: list[int]


class SignalGameCarrierRecordingReady(EventBase):
    """Both players had transmitted, so the channel's recording is fixed."""

    event_type: Literal["signal_game_carrier_recording_ready"] = (
        "signal_game_carrier_recording_ready"
    )
    round_number: int
    recording: list[int]


class SignalGameCarrierSquareChosen(EventBase):
    """One player's pick, and the colour that square holds on its own grid."""

    event_type: Literal["signal_game_carrier_square_chosen"] = "signal_game_carrier_square_chosen"
    round_number: int
    agent_id: str
    row: int
    col: int
    colour: str


class SignalGameCarrierRoundResolved(EventBase):
    """Whether both players' squares held the same colour. A player that did not pick is
    missing from ``squares`` and ``colours``."""

    event_type: Literal["signal_game_carrier_round_resolved"] = "signal_game_carrier_round_resolved"
    round_number: int
    squares: dict[str, list[int]]
    colours: dict[str, str]
    success: bool
    trigger: str
