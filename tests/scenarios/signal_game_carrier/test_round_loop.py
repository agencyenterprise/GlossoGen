"""The round loop through the real runner, tools and game clock, with scripted players."""

from pathlib import Path

import pytest

from glossogen.scenarios.signal_game_carrier.boards import Square, colour_at
from glossogen.scenarios.signal_game_carrier.events import (
    SignalGameCarrierRecordingReady,
    SignalGameCarrierRoundResolved,
    SignalGameCarrierSquareChosen,
)
from glossogen.scenarios.signal_game_carrier.ids import BOTH_CHOSE_TRIGGER, PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game_carrier.song import mix
from glossogen.testing.scenario_runtime import assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.signal_game_carrier.signal_game_carrier_play import (
    ALTERNATING_EXECUTOR,
    ONE_ROUND,
    STEADY_EXECUTOR,
    alternating_noise,
    build,
    call,
    end_round,
    material_of,
    play,
    plays,
    read,
    results_for,
    shared_colour,
    squares_of_colour,
    steady_noise,
    wait_for_next_round,
    write_executor,
)

pytestmark = pytest.mark.xdist_group("signal_game_carrier")


def resolved(result: SimulationResult) -> SignalGameCarrierRoundResolved:
    [outcome] = result.of_type(event_type=SignalGameCarrierRoundResolved)
    return outcome


async def test_two_squares_of_the_same_colour_score_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    material = material_of(scenario=scenario)[0]
    colour = shared_colour(material=material, first=PLAYER_A, second=PLAYER_B)
    squares = {
        agent_id: squares_of_colour(grid=material.grids[agent_id], colour=colour)[0]
        for agent_id in (PLAYER_A, PLAYER_B)
    }
    result = await play(
        scenario=scenario,
        scripts={
            PLAYER_A: plays(code=ALTERNATING_EXECUTOR, square=squares[PLAYER_A]),
            PLAYER_B: plays(code=STEADY_EXECUTOR, square=squares[PLAYER_B]),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    assert_round_loop_completed(result=result, round_count=1)
    outcome = resolved(result=result)
    assert outcome.success
    assert outcome.trigger == BOTH_CHOSE_TRIGGER
    assert outcome.colours == {PLAYER_A: colour, PLAYER_B: colour}


async def test_the_recording_carries_both_players_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    material = material_of(scenario=scenario)[0]
    colour = shared_colour(material=material, first=PLAYER_A, second=PLAYER_B)
    result = await play(
        scenario=scenario,
        scripts={
            PLAYER_A: plays(
                code=ALTERNATING_EXECUTOR,
                square=squares_of_colour(grid=material.grids[PLAYER_A], colour=colour)[0],
            ),
            PLAYER_B: plays(
                code=STEADY_EXECUTOR,
                square=squares_of_colour(grid=material.grids[PLAYER_B], colour=colour)[0],
            ),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    [ready] = result.of_type(event_type=SignalGameCarrierRecordingReady)
    length = len(material.song)
    assert ready.recording == mix(
        song=material.song,
        noises=[alternating_noise(length=length), steady_noise(length=length)],
        channel_noise=material.channel_noise,
    )
    [recording_view] = results_for(result=result, agent_id=PLAYER_A, tool_name="read_recording")
    assert " ".join(str(value) for value in ready.recording) in recording_view


async def test_two_squares_of_different_colours_do_not_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    material = material_of(scenario=scenario)[0]
    grid_b = material.grids[PLAYER_B]
    square_a = Square(row=1, col=1)
    colour_a = colour_at(grid=material.grids[PLAYER_A], square=square_a)
    different = [
        square
        for square in (
            Square(row=row, col=col)
            for row in range(1, len(grid_b) + 1)
            for col in range(1, len(grid_b) + 1)
        )
        if colour_at(grid=grid_b, square=square) != colour_a
    ]
    if not different:
        pytest.skip("player_b's grid holds only player_a's colour this round")
    result = await play(
        scenario=scenario,
        scripts={
            PLAYER_A: plays(code=ALTERNATING_EXECUTOR, square=square_a),
            PLAYER_B: plays(code=STEADY_EXECUTOR, square=different[0]),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    outcome = resolved(result=result)
    assert not outcome.success
    assert outcome.colours[PLAYER_A] != outcome.colours[PLAYER_B]


async def test_the_recording_is_refused_until_both_have_transmitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    material = material_of(scenario=scenario)[0]
    colour = shared_colour(material=material, first=PLAYER_A, second=PLAYER_B)
    early: list[ScriptedTurn] = [
        read(),
        call(tool_name="read_recording"),
        write_executor(code=ALTERNATING_EXECUTOR),
        call(tool_name="transmit"),
        read(),
        end_round(square=squares_of_colour(grid=material.grids[PLAYER_A], colour=colour)[0]),
        wait_for_next_round(),
    ]
    result = await play(
        scenario=scenario,
        scripts={
            PLAYER_A: early,
            PLAYER_B: plays(
                code=STEADY_EXECUTOR,
                square=squares_of_colour(grid=material.grids[PLAYER_B], colour=colour)[0],
            ),
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    [refusal] = results_for(result=result, agent_id=PLAYER_A, tool_name="read_recording")
    assert "your partner has not transmitted" in refusal
    assert [event.agent_id for event in result.of_type(event_type=SignalGameCarrierSquareChosen)]
