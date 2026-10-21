"""signal_game_server's ``longest_streak`` over its round verdicts.

signal_game's metric of the same name is covered by ``tests/metrics/test_longest_streak.py``.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game_server.evaluation.longest_streak_metric import (
    LongestStreakMetric,
)
from glossogen.scenarios.signal_game_server.events import SignalGameServerRoundResolved
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.signal_game_server.signal_game_server_play import ONE_ROUND, build


def verdict(round_number: int, success: bool) -> SignalGameServerRoundResolved:
    return SignalGameServerRoundResolved(
        round_number=round_number,
        final_squares={PLAYER_A: (1, 1), PLAYER_B: (1, 1)},
        final_colours={PLAYER_A: "red", PLAYER_B: "red"},
        success=success,
        trigger="both_chose",
        cheats=[],
    )


async def measure(events: list[SimulationEvent], tmp_path: Path) -> list[Measurement]:
    scenario = build(overrides=ONE_ROUND)
    return await LongestStreakMetric().compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def test_a_run_with_no_resolved_round_has_no_measurement(tmp_path: Path) -> None:
    assert await measure(events=[], tmp_path=tmp_path) == []


async def test_the_streak_is_the_longest_run_of_wins_and_a_gap_breaks_it(
    tmp_path: Path,
) -> None:
    wins = {1: True, 2: True, 3: False, 4: True, 6: True}
    events: list[SimulationEvent] = [
        verdict(round_number=number, success=won) for number, won in wins.items()
    ]

    [measurement] = await measure(events=events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(2.0)
    assert [observation.value for observation in measurement.per_round] == [
        1.0,
        2.0,
        0.0,
        1.0,
        1.0,
    ]
