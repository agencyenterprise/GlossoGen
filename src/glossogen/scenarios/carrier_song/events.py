"""carrier_song's events: each round's material, every executor run, the transmission,
the decoding and the verdict."""

from typing import Literal

from glossogen.models.event_base import EventBase


class CarrierSongRoundStarted(EventBase):
    """A round's roles, secret, song and channel noise. Only the sender is told the secret."""

    event_type: Literal["carrier_song_round_started"] = "carrier_song_round_started"
    round_number: int
    sender_id: str
    receiver_id: str
    secret: str
    song: list[int]
    channel_noise: list[int]


class CarrierSongExecutorRan(EventBase):
    """One run of a sender's executor on the round's song.

    ``written`` is true when the run tested code just passed to write_executor, and
    false when the executor in place ran on a new song. ``accepted`` says whether the
    run returned usable noise; a written executor that is not accepted does not
    replace the one in place. ``noise`` is the noise after clipping, None when not
    accepted, and ``error`` says why not.
    """

    event_type: Literal["carrier_song_executor_ran"] = "carrier_song_executor_ran"
    round_number: int
    agent_id: str
    code: str
    written: bool
    accepted: bool
    noise: list[int] | None
    clipped_ticks: int
    error: str | None


class CarrierSongTransmitted(EventBase):
    """The sender ended its turn: the noise it played and the recording the receiver gets."""

    event_type: Literal["carrier_song_transmitted"] = "carrier_song_transmitted"
    round_number: int
    sender_id: str
    noise: list[int]
    recording: list[int]


class CarrierSongDecodingSubmitted(EventBase):
    """The receiver's reading of the secret."""

    event_type: Literal["carrier_song_decoding_submitted"] = "carrier_song_decoding_submitted"
    round_number: int
    receiver_id: str
    decoded: str


class CarrierSongRoundResolved(EventBase):
    """Whether the receiver's decoding matched the secret. ``decoded`` is None when the
    round ended without one."""

    event_type: Literal["carrier_song_round_resolved"] = "carrier_song_round_resolved"
    round_number: int
    sender_id: str
    receiver_id: str
    secret: str
    decoded: str | None
    success: bool
    trigger: str
