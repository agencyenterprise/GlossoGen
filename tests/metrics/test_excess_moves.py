"""``excess_moves`` over a signal_game run played by scripted players."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game.evaluation.excess_moves_metric import ExcessMovesMetric
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.signal_game.signal_game_play import (
    ONE_ROUND,
    build,
    finish,
    move,
    play,
    read,
)

pytestmark = pytest.mark.xdist_group("signal_game")


async def measure(
    scenario: SignalGameScenario, events: list[SimulationEvent], tmp_path: Path
) -> list[Measurement]:
    return await ExcessMovesMetric().compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def test_a_detour_counts_and_a_straight_path_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_a oscillates right-left-right-left-right: five moves to a square one away."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["right"]),
            move(directions=["left"]),
            move(directions=["right"]),
            move(directions=["left"]),
            move(directions=["right"]),
            finish(),
        ],
        PLAYER_B: [read(), move(directions=["down"]), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [measurement] = await measure(scenario=scenario, events=result.events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(2.0)
    [round_one] = measurement.per_round
    assert round_one.value == pytest.approx(2.0)
    assert "player_a: 4 excess [right left right left right]" in round_one.note
    assert "player_b: 0 excess [down]" in round_one.note
    assert [(agent.agent_id, agent.value) for agent in measurement.per_agent] == [
        (PLAYER_A, 4.0),
        (PLAYER_B, 0.0),
    ]


async def test_a_run_with_no_signal_game_rounds_gets_no_measurement(tmp_path: Path) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    assert await measure(scenario=scenario, events=[], tmp_path=tmp_path) == []
