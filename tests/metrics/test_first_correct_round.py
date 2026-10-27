"""``first_correct_round`` over carrier_song round verdicts."""

from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent, ToolCallInvoked
from glossogen.scenarios.carrier_song.evaluation.first_correct_round_metric import (
    FirstCorrectRoundMetric,
)
from glossogen.scenarios.carrier_song.evaluation.sandbox_reach_metric import (
    SandboxReachMetric,
)
from glossogen.scenarios.carrier_song.events import CarrierSongRoundResolved
from glossogen.scenarios.carrier_song.ids import DECODED_TRIGGER, PLAYER_A, PLAYER_B
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.carrier_song.carrier_song_play import build


def decoded_for(success: bool) -> str:
    if success:
        return "ABC123"
    return "ZZZZZZ"


def resolved(round_number: int, success: bool) -> CarrierSongRoundResolved:
    return CarrierSongRoundResolved(
        round_number=round_number,
        sender_id=PLAYER_A,
        receiver_id=PLAYER_B,
        secret="ABC123",
        decoded=decoded_for(success=success),
        success=success,
        trigger=DECODED_TRIGGER,
    )


def program(round_number: int, agent_id: str, tool_name: str, code: str) -> ToolCallInvoked:
    return ToolCallInvoked(
        round_number=round_number,
        agent_id=agent_id,
        call_id=f"{agent_id}-{round_number}-{tool_name}",
        tool_name=tool_name,
        arguments={"code": code},
    )


async def compute(
    metric: FirstCorrectRoundMetric | SandboxReachMetric,
    events: list[SimulationEvent],
    tmp_path: Path,
) -> list[Measurement]:
    scenario = build(overrides={})
    return await metric.compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def test_the_first_correct_round_is_the_score(tmp_path: Path) -> None:
    events: list[SimulationEvent] = [resolved(1, False), resolved(2, False), resolved(3, True)]

    [measurement] = await compute(
        metric=FirstCorrectRoundMetric(), events=events, tmp_path=tmp_path
    )

    assert measurement.score == 3.0
    assert [o.value for o in measurement.per_round] == [0.0, 0.0, 1.0]


async def test_a_run_without_a_correct_decoding_has_no_first_correct_round(tmp_path: Path) -> None:
    events: list[SimulationEvent] = [resolved(n, False) for n in range(1, 11)]

    assert await compute(metric=FirstCorrectRoundMetric(), events=events, tmp_path=tmp_path) == []
