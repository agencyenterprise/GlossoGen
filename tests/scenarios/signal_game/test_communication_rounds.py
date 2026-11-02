"""The move traces ``build_communication_rounds`` hands the communication metrics."""

from pathlib import Path

import pytest

from glossogen.scenarios.signal_game.evaluation.build_communication_rounds import (
    MOVES_CHANNEL,
    build_communication_rounds,
)
from glossogen.scenarios.signal_game.events import SignalGameMoveMade, SignalGameRoundStarted
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.testing.scripted_agent import ScriptedTurn
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


async def test_each_round_holds_each_players_trace_and_both_grids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["left"]), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [view] = scenario.build_communication_rounds(events=result.events)

    traces = {line.sender_agent_id: line.text for line in view.messages}
    assert all(line.channel_id == MOVES_CHANNEL for line in view.messages)
    assert "left->r2c1" in traces[PLAYER_A]
    assert traces[PLAYER_A].endswith("end_round")
    assert traces[PLAYER_B] == "end_round"
    assert (
        "player_a grid (rows top to bottom): red red / green blue; starts on r2c2"
        in view.ground_truth_block
    )
    assert "round success: False" in view.ground_truth_block


def test_a_resumed_round_keeps_only_the_moves_after_its_last_start() -> None:
    """``--resume`` logs a second round_started for the unfinished round and numbers its
    actions from 1 again; the moves made before the crash are not part of the round."""
    grid = [["red", "blue"], ["blue", "red"]]
    started = SignalGameRoundStarted(
        round_number=1,
        grids={PLAYER_A: grid, PLAYER_B: grid},
        start_squares={PLAYER_A: (1, 1), PLAYER_B: (1, 1)},
        moves_per_round=10,
        partner_colours_visible=False,
    )

    def moved(direction: str, to_square: tuple[int, int]) -> SignalGameMoveMade:
        return SignalGameMoveMade(
            round_number=1,
            agent_id=PLAYER_A,
            sequence=1,
            direction=direction,
            from_square=(1, 1),
            to_square=to_square,
            moves_used=1,
        )

    [round_view] = build_communication_rounds(
        events=[started, moved("right", (1, 2)), started.model_copy(), moved("down", (2, 1))]
    )

    assert [line.text for line in round_view.messages] == ["#1 down->r2c1"]
