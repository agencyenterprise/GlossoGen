"""``longest_streak`` over signal_game round verdicts."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game.evaluation.longest_streak_metric import LongestStreakMetric
from glossogen.scenarios.signal_game.events import SignalGameRoundResolved
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.signal_game.signal_game_play import ONE_ROUND, build


def verdict(round_number: int, success: bool) -> SignalGameRoundResolved:
    return SignalGameRoundResolved(
        round_number=round_number,
        final_squares={PLAYER_A: (1, 1), PLAYER_B: (1, 1)},
        final_colours={PLAYER_A: "red", PLAYER_B: "red"},
        moves_used={PLAYER_A: 0, PLAYER_B: 0},
        success=success,
        trigger="both_finished",
    )


async def measure(events: list[SimulationEvent], tmp_path: Path) -> list[Measurement]:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    return await LongestStreakMetric().compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def test_the_score_is_the_longest_run_of_wins_not_the_total(tmp_path: Path) -> None:
    wins = [True, True, False, True, True, True, False, True]
    events: list[SimulationEvent] = [
        verdict(round_number=number, success=won) for number, won in enumerate(wins, start=1)
    ]

    [measurement] = await measure(events=events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(3.0)
    assert [observation.value for observation in measurement.per_round] == [
        1.0,
        2.0,
        0.0,
        1.0,
        2.0,
        3.0,
        0.0,
        1.0,
    ]
    assert "6 won in all" in measurement.summary


async def test_a_round_missing_from_the_log_breaks_the_streak(tmp_path: Path) -> None:
    events: list[SimulationEvent] = [
        verdict(round_number=1, success=True),
        verdict(round_number=2, success=True),
        verdict(round_number=4, success=True),
    ]

    [measurement] = await measure(events=events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(2.0)
    assert [observation.value for observation in measurement.per_round] == [1.0, 2.0, 1.0]


async def test_a_run_with_no_signal_game_rounds_gets_no_measurement(tmp_path: Path) -> None:
    assert await measure(events=[], tmp_path=tmp_path) == []
