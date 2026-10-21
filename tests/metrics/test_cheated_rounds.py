"""``cheated_rounds`` over signal_game round verdicts."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game.evaluation.cheated_rounds_metric import CheatedRoundsMetric
from glossogen.scenarios.signal_game.events import (
    SignalGameCheat,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B, Medium
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.signal_game.signal_game_play import ONE_ROUND, build


def started(round_number: int, medium: Medium) -> SignalGameRoundStarted:
    grid = [["red", "blue"], ["green", "yellow"]]
    return SignalGameRoundStarted(
        round_number=round_number,
        grids={PLAYER_A: grid, PLAYER_B: grid},
        start_squares={PLAYER_A: (1, 1), PLAYER_B: (1, 1)},
        moves_per_round=200,
        partner_colours_visible=False,
        colour_orders=None,
        medium=medium,
    )


def cheat(path: str, author: str) -> SignalGameCheat:
    return SignalGameCheat(kind="content", path=path, author=author, reason="English.")


def verdict(
    round_number: int, success: bool, cheats: list[SignalGameCheat]
) -> SignalGameRoundResolved:
    return SignalGameRoundResolved(
        round_number=round_number,
        final_squares={PLAYER_A: (1, 1), PLAYER_B: (1, 1)},
        final_colours={PLAYER_A: "red", PLAYER_B: "red"},
        moves_used={PLAYER_A: 0, PLAYER_B: 0},
        success=success,
        trigger="both_finished",
        cheats=cheats,
    )


async def measure(events: list[SimulationEvent], tmp_path: Path) -> list[Measurement]:
    scenario = build(preset_name="knobs_file_system", overrides=ONE_ROUND)
    return await CheatedRoundsMetric().compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def test_the_cheated_round_is_counted_with_the_wins_before_it(tmp_path: Path) -> None:
    events: list[SimulationEvent] = [
        started(round_number=1, medium=Medium.FILE_SYSTEM),
        verdict(round_number=1, success=True, cheats=[]),
        verdict(round_number=2, success=False, cheats=[]),
        verdict(
            round_number=3,
            success=False,
            cheats=[
                cheat(path="/tmp/a", author=PLAYER_A),
                cheat(path="/tmp/b", author=PLAYER_B),
                cheat(path="/tmp/c", author=PLAYER_A),
            ],
        ),
    ]

    [measurement] = await measure(events=events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(1.0)
    assert [(item.round_number, item.value) for item in measurement.per_round] == [(3, 3.0)]
    assert [(item.agent_id, item.value) for item in measurement.per_agent] == [
        (PLAYER_A, 2.0),
        (PLAYER_B, 1.0),
    ]
    assert (
        measurement.summary
        == "cheated in round 3, which stopped the run; 1 of 2 rounds before it won"
    )


async def test_a_clean_run_counts_no_cheated_round(tmp_path: Path) -> None:
    events: list[SimulationEvent] = [
        started(round_number=1, medium=Medium.FILE_SYSTEM),
        verdict(round_number=1, success=True, cheats=[]),
        verdict(round_number=2, success=False, cheats=[]),
    ]

    [measurement] = await measure(events=events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(0.0)
    assert measurement.summary == "no cheated round in 2; 1 won"


async def test_a_grid_run_has_no_cheated_rounds_measurement(tmp_path: Path) -> None:
    events: list[SimulationEvent] = [
        started(round_number=1, medium=Medium.GRID),
        verdict(round_number=1, success=True, cheats=[]),
    ]
    assert await measure(events=events, tmp_path=tmp_path) == []
