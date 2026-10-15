"""``excess_moves`` over a signal_game run played by scripted players."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.signal_game.evaluation.excess_moves_metric import (
    ExcessMovesMetric,
    excess_moves_by_agent,
)
from glossogen.scenarios.signal_game.events import SignalGameRoundResolved, SignalGameRoundStarted
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.signal_game.signal_game_play import (
    ONE_ROUND,
    build,
    end_round,
    move,
    play,
    read,
    wait_for_next_round,
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
    """From row 2, col 2, player_a oscillates left-right-left: three moves to a square one away."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["left"]),
            move(directions=["right"]),
            move(directions=["left"]),
            end_round(),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), move(directions=["up"]), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [measurement] = await measure(scenario=scenario, events=result.events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(1.0)
    [round_one] = measurement.per_round
    assert round_one.value == pytest.approx(1.0)
    assert "player_a: 2 excess [left right left]" in round_one.note
    assert "player_b: 0 excess [up]" in round_one.note
    assert [(agent.agent_id, agent.value) for agent in measurement.per_agent] == [
        (PLAYER_A, 2.0),
        (PLAYER_B, 0.0),
    ]


async def test_a_run_with_no_signal_game_rounds_gets_no_measurement(tmp_path: Path) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    assert await measure(scenario=scenario, events=[], tmp_path=tmp_path) == []


GRIDS = {
    PLAYER_A: [["red", "blue"], ["green", "red"]],
    PLAYER_B: [["red", "red"], ["blue", "green"]],
}


def resolved_on(
    final_squares: dict[str, tuple[int, int]], moves_used: dict[str, int]
) -> SignalGameRoundResolved:
    return SignalGameRoundResolved(
        round_number=1,
        final_squares=final_squares,
        final_colours={PLAYER_A: "red", PLAYER_B: "red"},
        moves_used=moves_used,
        success=True,
        trigger="both_finished",
    )


def test_each_player_is_measured_from_its_own_start() -> None:
    started = SignalGameRoundStarted(
        round_number=1,
        grids=GRIDS,
        start_squares={PLAYER_A: (1, 1), PLAYER_B: (2, 2)},
        moves_per_round=200,
        partner_colours_visible=False,
    )
    outcome = resolved_on(
        final_squares={PLAYER_A: (2, 2), PLAYER_B: (2, 2)}, moves_used={PLAYER_A: 2, PLAYER_B: 2}
    )
    assert excess_moves_by_agent(started=started, resolved=outcome) == {PLAYER_A: 0, PLAYER_B: 2}


def test_a_log_from_before_random_starts_reads_its_shared_start_square() -> None:
    started = SignalGameRoundStarted.model_validate(
        {
            "event_type": "signal_game_round_started",
            "round_number": 1,
            "grids": GRIDS,
            "start_square": [1, 1],
            "moves_per_round": 200,
            "partner_colours_visible": False,
        }
    )
    assert started.start_squares == {PLAYER_A: (1, 1), PLAYER_B: (1, 1)}
