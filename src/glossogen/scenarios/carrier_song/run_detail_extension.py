"""carrier_song extension to the platform run-detail API.

Materializes the round-detail panel's data: for each round, the song, the noise
the sender transmitted, the channel noise and the recording the receiver got,
with the executor that produced the noise and the receiver's decoding. The
frontend panel draws the song beside the recording, so a reader sees what the
sender added to it.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.carrier_song.events import (
    CarrierSongExecutorRan,
    CarrierSongRoundResolved,
    CarrierSongRoundStarted,
    CarrierSongTransmitted,
)


class CarrierSongCaseSummary(BaseModel):
    """One round's case as the round-detail panel draws it.

    ``noise`` and ``recording`` are None when the sender never ended its turn.
    ``executor_code`` is the executor whose noise was transmitted, None when the
    sender played silence. ``decoded`` and ``success`` are None until the round is
    resolved, and ``decoded`` stays None when no decoding was submitted.
    """

    round_number: int
    sender_id: str
    receiver_id: str
    secret: str
    song: list[int]
    channel_noise: list[int]
    noise: list[int] | None
    recording: list[int] | None
    executor_code: str | None
    decoded: str | None
    success: bool | None


class CarrierSongRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for carrier_song runs."""

    scenario_name: Literal["carrier_song"] = "carrier_song"
    cases: list[CarrierSongCaseSummary]


class _RoundEvents:
    """The events of one round that the summary reads, gathered in log order."""

    def __init__(self, started: CarrierSongRoundStarted) -> None:
        self.started = started
        self.played_code: str | None = None
        self.transmitted: CarrierSongTransmitted | None = None
        self.resolved: CarrierSongRoundResolved | None = None

    def summary(self) -> CarrierSongCaseSummary:
        started = self.started
        noise: list[int] | None = None
        recording: list[int] | None = None
        executor_code: str | None = None
        if self.transmitted is not None:
            noise = self.transmitted.noise
            recording = self.transmitted.recording
            executor_code = self.played_code
        decoded: str | None = None
        success: bool | None = None
        if self.resolved is not None:
            decoded = self.resolved.decoded
            success = self.resolved.success
        return CarrierSongCaseSummary(
            round_number=started.round_number,
            sender_id=started.sender_id,
            receiver_id=started.receiver_id,
            secret=started.secret,
            song=started.song,
            channel_noise=started.channel_noise,
            noise=noise,
            recording=recording,
            executor_code=executor_code,
            decoded=decoded,
            success=success,
        )


def build_case_summaries(events: list[SimulationEvent]) -> list[CarrierSongCaseSummary]:
    """Every started round's summary, in round order.

    The executor credited with a round's noise is the last one accepted in that
    round before the transmission: a run of the executor in place when the round
    opened, or a write_executor whose noise replaced it.
    """
    rounds: dict[int, _RoundEvents] = {}
    for event in events:
        if isinstance(event, CarrierSongRoundStarted):
            rounds[event.round_number] = _RoundEvents(started=event)
            continue
        current = rounds.get(event.round_number)
        if current is None:
            continue
        if isinstance(event, CarrierSongExecutorRan) and event.accepted:
            if current.transmitted is None:
                current.played_code = event.code
        elif isinstance(event, CarrierSongTransmitted):
            current.transmitted = event
        elif isinstance(event, CarrierSongRoundResolved):
            current.resolved = event
    return [rounds[number].summary() for number in sorted(rounds)]


class CarrierSongRunDetailExtension(ScenarioRunDetailExtension):
    """carrier_song hook into :class:`RunDetailResponse.scenario_extras`."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = CarrierSongRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> CarrierSongRunExtras:
        return CarrierSongRunExtras(cases=build_case_summaries(events=events))
