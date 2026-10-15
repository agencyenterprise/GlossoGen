"""The move traces ``build_communication_rounds`` hands the communication metrics."""

from pathlib import Path

import pytest

from glossogen.scenarios.signal_game.evaluation.build_communication_rounds import MOVES_CHANNEL
from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.signal_game.signal_game_play import (
    ONE_ROUND,
    build,
    finish,
    move,
    play,
    read,
)

pytestmark = pytest.mark.xdist_group("signal_game")


async def test_each_round_holds_each_players_trace_and_both_grids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["right"]), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [view] = scenario.build_communication_rounds(events=result.events)

    traces = {line.sender_agent_id: line.text for line in view.messages}
    assert all(line.channel_id == MOVES_CHANNEL for line in view.messages)
    assert "right->r1c2" in traces[PLAYER_A]
    assert traces[PLAYER_A].endswith("finish")
    assert traces[PLAYER_B] == "finish"
    assert "player_a grid (rows top to bottom): red red / green blue" in view.ground_truth_block
    assert "round success: False" in view.ground_truth_block
