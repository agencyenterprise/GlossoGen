"""The round loop through the real runner, tools and game clock, with scripted players."""

from pathlib import Path

import pytest
from pydantic_ai.settings import ModelSettings

from glossogen.model_catalog import Provider
from glossogen.models.event import ToolResultReceived
from glossogen.runners.pydantic_ai_model_factory import agent_model_settings
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
    SignalGameTurnPassed,
)
from glossogen.scenarios.signal_game.ids import (
    BOTH_FINISHED_TRIGGER,
    MAX_MOVES_PER_CALL,
    PLAYER_A,
    PLAYER_B,
)
from glossogen.testing.scenario_runtime import assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.signal_game.signal_game_play import (
    ONE_ROUND,
    build,
    finish,
    move,
    play,
    read,
)

pytestmark = pytest.mark.xdist_group("signal_game")

TURN_BASED = {**ONE_ROUND, "turn_based": True}


def resolved(result: SimulationResult) -> SignalGameRoundResolved:
    [outcome] = result.of_type(event_type=SignalGameRoundResolved)
    return outcome


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]


def wakes_of(result: SimulationResult, agent_id: str) -> str:
    return "\n".join(results_for(result=result, agent_id=agent_id, tool_name="read_notifications"))


async def test_finishing_on_the_same_colour_wins_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish()],
        PLAYER_B: [read(), move(directions=["down"]), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=1)
    outcome = resolved(result=result)
    assert outcome.success
    assert outcome.trigger == BOTH_FINISHED_TRIGGER
    assert outcome.final_colours == {PLAYER_A: "red", PLAYER_B: "red"}
    assert outcome.moves_used == {PLAYER_A: 0, PLAYER_B: 1}


async def test_different_colours_lose_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert not outcome.success
    assert outcome.final_colours == {PLAYER_A: "red", PLAYER_B: "blue"}


async def test_the_partner_sees_every_action_once_numbered_and_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_b learns of player_a's calls through its wakes, whenever it parks.

    player_b either wakes on each of player_a's actions or, once player_a has
    finished, is released; both paths show each action exactly once.
    """
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["right"]),
            move(directions=["left"]),
            move(directions=["down"]),
            finish(),
        ],
        PLAYER_B: [read(), read(), read(), read(), read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    seen = wakes_of(result=result, agent_id=PLAYER_B)
    lines = (
        "1 - [right] -> row 1, col 2",
        "2 - [left] -> row 1, col 1",
        "3 - [down] -> row 2, col 1",
        "4 - finished the round",
    )
    for line in lines:
        assert seen.count(line) == 1, line
    assert seen.index(lines[0]) < seen.index(lines[1]) < seen.index(lines[2])
    assert [move.direction for move in result.of_type(event_type=SignalGameMoveMade)] == [
        "right",
        "left",
        "down",
    ]


async def test_a_move_off_the_grid_is_refused_and_spends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["up"]), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [refusal] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "leaves the grid. Nothing was moved." in refusal
    assert result.of_type(event_type=SignalGameMoveMade) == []
    assert resolved(result=result).moves_used[PLAYER_A] == 0


async def test_a_player_out_of_moves_counts_as_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, "moves_per_round": 1})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["right"]), finish()],
        PLAYER_B: [read(), move(directions=["down"]), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.trigger == BOTH_FINISHED_TRIGGER
    assert outcome.success


async def test_two_players_waiting_on_each_other_are_released_then_the_round_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    waits: list[ScriptedTurn] = [read(), read(), read(), read()]
    scripts: dict[str, list[ScriptedTurn]] = {PLAYER_A: list(waits), PLAYER_B: list(waits)}
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=1)
    assert resolved(result=result).trigger == "all_agents_waiting"
    notices = [
        text
        for agent_id in (PLAYER_A, PLAYER_B)
        for text in results_for(result=result, agent_id=agent_id, tool_name="read_notifications")
        if "is waiting too" in text
    ]
    assert notices


async def test_two_rounds_brief_the_previous_result_and_reveal_the_partner_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish(), finish()],
        PLAYER_B: [read(), finish(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=2)
    assert len(result.of_type(event_type=SignalGameRoundStarted)) == 2
    second_briefing = next(
        text
        for text in results_for(result=result, agent_id=PLAYER_A, tool_name="read_notifications")
        if "ROUND 2 OF 2" in text
    )
    assert "Round 1 result: no point" in second_briefing
    assert "blue | blue" in second_briefing


async def test_the_control_shows_the_partner_colours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_shared_colours_control", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [briefing] = [
        text
        for text in results_for(result=result, agent_id=PLAYER_A, tool_name="read_notifications")
        if "ROUND 1" in text
    ]
    assert "Your partner's grid this round" in briefing


def test_no_preset_offers_a_channel_or_free_text() -> None:
    for preset_name in (
        "knobs_default",
        "knobs_shared_colours_control",
    ):
        scenario = build(preset_name=preset_name, overrides={})
        assert scenario.get_channels() == []
        assert scenario.get_primary_channels() == []
        for agent in scenario.get_agents(default_model="test", default_provider="anthropic"):
            assert agent.channel_ids == []
            assert agent.tool_names == ["move"]
            assert "send_message" in scenario.hidden_base_tools(agent_id=agent.agent_id)


async def test_a_batch_is_applied_in_order_and_the_partner_sees_it_as_one_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_b waits once; player_a's whole burst reaches it as one numbered action."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["right", "left", "right", "left", "down"]),
            finish(),
        ],
        PLAYER_B: [read(), read(), read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    moves = result.of_type(event_type=SignalGameMoveMade)
    assert [(m.sequence, m.direction) for m in moves] == [
        (1, "right"),
        (2, "left"),
        (3, "right"),
        (4, "left"),
        (5, "down"),
    ]
    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert (
        "You moved (your action 1): [right, left, right, left, down] -> row 2, col 1." in a_result
    )
    seen = wakes_of(result=result, agent_id=PLAYER_B)
    assert seen.count("1 - [right, left, right, left, down] -> row 2, col 1") == 1
    assert resolved(result=result).moves_used[PLAYER_A] == 5


async def test_a_step_off_the_grid_stops_the_batch_and_the_steps_before_it_stand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["right", "right", "down"]), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "Stopped after 1 of 3 steps: Moving right from row 1, col 2 leaves the grid" in a_result
    assert [m.direction for m in result.of_type(event_type=SignalGameMoveMade)] == ["right"]
    assert resolved(result=result).final_squares[PLAYER_A] == (1, 2)


async def test_a_batch_longer_than_the_moves_left_stops_at_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, "moves_per_round": 2})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["right", "left", "right"]), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "Stopped after 2 of 3 steps: You have no moves left" in a_result
    assert resolved(result=result).moves_used[PLAYER_A] == 2


@pytest.mark.parametrize(
    ("directions", "refusal"),
    [
        ([], "too_short"),
        (["right", "left"] * (MAX_MOVES_PER_CALL // 2) + ["right"], "too_long"),
        (["stay"], "enum"),
    ],
)
async def test_the_schema_refuses_an_empty_overlong_or_unknown_batch(
    directions: list[str], refusal: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=directions), finish()],
        PLAYER_B: [read(), finish()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert refusal in a_result
    assert result.of_type(event_type=SignalGameMoveMade) == []


async def test_the_runner_asks_the_provider_for_one_tool_call_per_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With parallel calls a model can move and finish the round in one response."""
    requested: list[bool] = []

    def recording_settings(
        provider: Provider, model: str, parallel_tool_calls: bool
    ) -> ModelSettings:
        requested.append(parallel_tool_calls)
        return agent_model_settings(
            provider=provider, model=model, parallel_tool_calls=parallel_tool_calls
        )

    monkeypatch.setattr(
        "glossogen.runners.pydantic_ai_runner.agent_model_settings", recording_settings
    )
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish()],
        PLAYER_B: [read(), finish()],
    }
    await play(scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert requested == [False, False]


async def test_a_wait_on_your_turn_passes_it_and_two_passes_in_a_row_end_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_a moves; player_b waits on its turn, passing it; player_a passes back.

    Neither second pass wakes anyone, so both are parked and the round ends.
    """
    scenario = build(preset_name="knobs_default", overrides=TURN_BASED)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["right"]), read(), read()],
        PLAYER_B: [read(), read(), read()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.trigger == "all_agents_waiting"
    assert outcome.final_squares == {PLAYER_A: (1, 2), PLAYER_B: (1, 1)}
    passes = result.of_type(event_type=SignalGameTurnPassed)
    assert [(p.agent_id, p.turn_number) for p in passes] == [(PLAYER_B, 1), (PLAYER_A, 2)]
    a_seen = wakes_of(result=result, agent_id=PLAYER_A)
    assert "1 - waited for notification" in a_seen
    assert "It is your turn." in a_seen
    assert "1 - [right] -> row 1, col 2" in wakes_of(result=result, agent_id=PLAYER_B)


async def test_finishing_is_allowed_on_the_partners_turn_and_frees_the_partner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_a finishes at once; player_b then makes two moves in a row."""
    scenario = build(preset_name="knobs_default", overrides=TURN_BASED)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), finish()],
        PLAYER_B: [
            read(),
            read(),
            move(directions=["down"]),
            move(directions=["right"]),
            finish(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    b_moves = results_for(result=result, agent_id=PLAYER_B, tool_name="move")
    assert all("You moved" in text for text in b_moves)
    assert "you move without waiting for turns" in b_moves[-1]
    outcome = resolved(result=result)
    assert outcome.success
    assert outcome.final_squares == {PLAYER_A: (1, 1), PLAYER_B: (2, 2)}
