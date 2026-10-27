"""signal_game_carrier extension to the platform run-detail API.

Materializes the round-detail panel's data: for each round the song, the channel
noise and the recording, and for each player its grid, the noise it transmitted,
the executor that produced that noise and the square it picked. The frontend panel
draws the two grids beside the waveforms, so a reader sees what each player put on
the channel and which square it chose after hearing the other.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.signal_game_carrier.events import (
    SignalGameCarrierExecutorRan,
    SignalGameCarrierRecordingReady,
    SignalGameCarrierRoundResolved,
    SignalGameCarrierRoundStarted,
    SignalGameCarrierSquareChosen,
    SignalGameCarrierTransmitted,
)
from glossogen.scenarios.signal_game_carrier.ids import AGENT_IDS


class SignalGameCarrierPlayerRound(BaseModel):
    """One player's round: its private grid, what it transmitted and what it picked.

    ``noise`` and ``executor_code`` are None when the player never transmitted, and
    ``executor_code`` stays None when it transmitted silence. ``square`` is the
    picked square as ``[row, col]`` counting from 1, None when it never picked, and
    ``colour`` is that square's colour on this player's own grid.
    """

    agent_id: str
    grid: list[list[str]]
    noise: list[int] | None
    executor_code: str | None
    square: list[int] | None
    colour: str | None


class SignalGameCarrierCaseSummary(BaseModel):
    """One round as the round-detail panel draws it.

    ``recording`` is None until both players have transmitted, and ``success`` is
    None until the round is resolved.
    """

    round_number: int
    song: list[int]
    channel_noise: list[int]
    recording: list[int] | None
    players: list[SignalGameCarrierPlayerRound]
    success: bool | None


class SignalGameCarrierRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for signal_game_carrier runs."""

    scenario_name: Literal["signal_game_carrier"] = "signal_game_carrier"
    cases: list[SignalGameCarrierCaseSummary]


class _PlayerRound:
    """What one player did in one round, gathered in log order."""

    def __init__(self, agent_id: str, grid: list[list[str]]) -> None:
        self.agent_id = agent_id
        self.grid = grid
        self.played_code: str | None = None
        self.noise: list[int] | None = None
        self.square: list[int] | None = None
        self.colour: str | None = None

    def summary(self) -> SignalGameCarrierPlayerRound:
        executor_code: str | None = None
        if self.noise is not None:
            executor_code = self.played_code
        return SignalGameCarrierPlayerRound(
            agent_id=self.agent_id,
            grid=self.grid,
            noise=self.noise,
            executor_code=executor_code,
            square=self.square,
            colour=self.colour,
        )


class _RoundEvents:
    """The events of one round that the summary reads, gathered in log order."""

    def __init__(self, started: SignalGameCarrierRoundStarted) -> None:
        self.started = started
        self.players = {
            agent_id: _PlayerRound(agent_id=agent_id, grid=started.grids[agent_id])
            for agent_id in AGENT_IDS
            if agent_id in started.grids
        }
        self.recording: list[int] | None = None
        self.resolved: SignalGameCarrierRoundResolved | None = None

    def summary(self) -> SignalGameCarrierCaseSummary:
        success: bool | None = None
        if self.resolved is not None:
            success = self.resolved.success
        return SignalGameCarrierCaseSummary(
            round_number=self.started.round_number,
            song=self.started.song,
            channel_noise=self.started.channel_noise,
            recording=self.recording,
            players=[player.summary() for player in self.players.values()],
            success=success,
        )


def build_case_summaries(events: list[SimulationEvent]) -> list[SignalGameCarrierCaseSummary]:
    """Every started round's summary, in round order.

    The executor credited with a player's noise is the last one it had accepted in
    that round before it transmitted: a run of the executor in place when the round
    opened, or a write_executor whose noise replaced it.
    """
    rounds: dict[int, _RoundEvents] = {}
    for event in events:
        if isinstance(event, SignalGameCarrierRoundStarted):
            rounds[event.round_number] = _RoundEvents(started=event)
            continue
        current = rounds.get(event.round_number)
        if current is None:
            continue
        if isinstance(event, SignalGameCarrierRecordingReady):
            current.recording = event.recording
            continue
        if isinstance(event, SignalGameCarrierRoundResolved):
            current.resolved = event
            continue
        if not isinstance(
            event,
            SignalGameCarrierExecutorRan
            | SignalGameCarrierTransmitted
            | SignalGameCarrierSquareChosen,
        ):
            continue
        player = current.players.get(event.agent_id)
        if player is None:
            continue
        if isinstance(event, SignalGameCarrierExecutorRan):
            if event.accepted and player.noise is None:
                player.played_code = event.code
        elif isinstance(event, SignalGameCarrierTransmitted):
            player.noise = event.noise
        else:
            player.square = [event.row, event.col]
            player.colour = event.colour
    return [rounds[number].summary() for number in sorted(rounds)]


class SignalGameCarrierRunDetailExtension(ScenarioRunDetailExtension):
    """signal_game_carrier hook into :class:`RunDetailResponse.scenario_extras`."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = SignalGameCarrierRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> SignalGameCarrierRunExtras:
        return SignalGameCarrierRunExtras(cases=build_case_summaries(events=events))
