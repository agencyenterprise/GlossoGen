"""The round loop through the real runner, tools and game clock, with scripted players."""

from pathlib import Path

import pytest
from pydantic_ai.settings import ModelSettings

from glossogen.model_catalog import Provider
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered, ToolResultReceived
from glossogen.runners.pydantic_ai_model_factory import agent_model_settings
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGamePlayerFinished,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)
from glossogen.scenarios.signal_game.ids import (
    BOTH_FINISHED_TRIGGER,
    MAX_MOVES_PER_CALL,
    PLAYER_A,
    PLAYER_B,
)
from glossogen.testing.scenario_runtime import assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult
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


def resolved(result: SimulationResult) -> SignalGameRoundResolved:
    [outcome] = result.of_type(event_type=SignalGameRoundResolved)
    return outcome


def resolved_rounds(result: SimulationResult) -> dict[int, tuple[int, int]]:
    """player_a's final square per round."""
    return {
        outcome.round_number: outcome.final_squares[PLAYER_A]
        for outcome in result.of_type(event_type=SignalGameRoundResolved)
    }


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]


async def test_finishing_on_the_same_colour_wins_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["up"]), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=1)
    outcome = resolved(result=result)
    assert outcome.success
    assert outcome.trigger == BOTH_FINISHED_TRIGGER
    assert outcome.final_colours == {PLAYER_A: "red", PLAYER_B: "red"}
    assert outcome.moves_used == {PLAYER_A: 1, PLAYER_B: 0}


async def test_different_colours_lose_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert not outcome.success
    assert outcome.final_colours == {PLAYER_A: "blue", PLAYER_B: "red"}


async def test_the_briefing_gives_each_players_own_random_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    one_round: list[ScriptedTurn] = [end_round(), wait_for_next_round()]
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), *one_round, *one_round],
        PLAYER_B: [read(), *one_round, *one_round],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    starts = {
        started.round_number: started.start_squares
        for started in result.of_type(event_type=SignalGameRoundStarted)
    }
    assert starts == {
        1: {PLAYER_A: (2, 2), PLAYER_B: (2, 2)},
        2: {PLAYER_A: (1, 1), PLAYER_B: (2, 1)},
    }
    second_briefing = next(
        text
        for text in results_for(result=result, agent_id=PLAYER_B, tool_name="read_notifications")
        if "ROUND 2" in text
    )
    assert "You start on row 2, col 1. Your partner starts on row 1, col 1." in second_briefing
    assert resolved_rounds(result=result) == {1: (2, 2), 2: (1, 1)}


async def test_the_partner_sees_every_move_once_and_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_b learns of player_a's moves through its wakes, whenever it parks.

    player_b either wakes on each of player_a's actions or, once player_a has
    finished, is released; both paths show each action exactly once.
    """
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["left"]),
            move(directions=["right"]),
            move(directions=["up"]),
            end_round(),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), read(), read(), read(), read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    seen = "\n".join(
        results_for(result=result, agent_id=PLAYER_B, tool_name="read_notifications")
        + results_for(result=result, agent_id=PLAYER_B, tool_name="end_round")
    )
    for line in ("#1 left", "#2 right", "#3 up", "#4 end_round"):
        assert seen.count(line) == 1, line
    assert seen.index("#1 left") < seen.index("#2 right") < seen.index("#3 up")
    assert [move.direction for move in result.of_type(event_type=SignalGameMoveMade)] == [
        "left",
        "right",
        "up",
    ]


async def test_the_reasoning_is_logged_and_never_shown_to_the_partner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A move's reasoning lands on each of its steps, and end_round's on the finish."""
    reasoning = "Bouncing left and right to mark my colour."
    end_reasoning = "Back on my start square, which is the colour I signalled."
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            ToolTurn(
                tool_name="move", args={"directions": ["left", "right"], "reasoning": reasoning}
            ),
            ToolTurn(tool_name="end_round", args={"reasoning": end_reasoning}),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), read(), read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert [move.reasoning for move in result.of_type(event_type=SignalGameMoveMade)] == [
        reasoning,
        reasoning,
    ]
    finishes = {
        finish.agent_id: finish.reasoning
        for finish in result.of_type(event_type=SignalGamePlayerFinished)
    }
    assert finishes[PLAYER_A] == end_reasoning
    seen = "\n".join(
        results_for(result=result, agent_id=PLAYER_B, tool_name="read_notifications")
        + results_for(result=result, agent_id=PLAYER_B, tool_name="end_round")
    )
    assert "#3 end_round" in seen
    assert reasoning not in seen
    assert end_reasoning not in seen


async def test_a_move_without_reasoning_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            ToolTurn(tool_name="move", args={"directions": ["left"], "reasoning": " "}),
            end_round(),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [refusal] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "reasoning" in refusal
    assert result.of_type(event_type=SignalGameMoveMade) == []


async def test_an_end_round_without_reasoning_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            ToolTurn(tool_name="end_round", args={"reasoning": " "}),
            end_round(),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    refusal, finished = results_for(result=result, agent_id=PLAYER_A, tool_name="end_round")
    assert "reasoning" in refusal
    assert "You finished round 1" in finished


async def test_without_move_reasoning_neither_tool_takes_a_reasoning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, "move_reasoning": False})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            ToolTurn(tool_name="move", args={"directions": ["left"]}),
            ToolTurn(tool_name="end_round", args={}),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), ToolTurn(tool_name="end_round", args={}), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [step] = result.of_type(event_type=SignalGameMoveMade)
    assert step.direction == "left"
    assert step.reasoning is None
    finishes = result.of_type(event_type=SignalGamePlayerFinished)
    assert [finish.reasoning for finish in finishes] == [None, None]


async def test_a_move_off_the_grid_is_refused_and_spends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["down"]), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [refusal] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "leaves the grid" in refusal
    assert result.of_type(event_type=SignalGameMoveMade) == []
    assert resolved(result=result).moves_used[PLAYER_A] == 0


async def test_a_player_out_of_moves_counts_as_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, "moves_per_round": 1})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["up"]), wait_for_next_round()],
        PLAYER_B: [read(), move(directions=["left"]), wait_for_next_round()],
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
    one_round: list[ScriptedTurn] = [end_round(), wait_for_next_round()]
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), *one_round, *one_round],
        PLAYER_B: [read(), *one_round, *one_round],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=2)
    assert len(result.of_type(event_type=SignalGameRoundStarted)) == 2
    second_briefing = next(
        text
        for text in results_for(result=result, agent_id=PLAYER_A, tool_name="read_notifications")
        if "ROUND 2" in text
    )
    assert "Round 1 result: no point" in second_briefing
    assert "blue | blue" in second_briefing


async def test_the_control_shows_the_partner_colours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_shared_colours_control", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
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
            assert agent.tool_names == ["move", "end_round"]
            assert "send_message" in scenario.hidden_base_tools(agent_id=agent.agent_id)


async def test_a_batch_is_applied_in_order_and_the_partner_sees_each_step_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """player_b waits once; player_a's whole burst reaches it as separate numbered steps."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["left", "right", "left", "right", "up"]),
            end_round(),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), read(), read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    moves = result.of_type(event_type=SignalGameMoveMade)
    assert [(m.sequence, m.direction) for m in moves] == [
        (1, "left"),
        (2, "right"),
        (3, "left"),
        (4, "right"),
        (5, "up"),
    ]
    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "You moved: left (#1), right (#2), left (#3), right (#4), up (#5)." in a_result
    seen = "\n".join(
        results_for(result=result, agent_id=PLAYER_B, tool_name="read_notifications")
        + results_for(result=result, agent_id=PLAYER_B, tool_name="end_round")
    )
    for line in ("#1 left", "#2 right", "#3 left", "#4 right", "#5 up"):
        assert seen.count(line) == 1, line
    assert resolved(result=result).moves_used[PLAYER_A] == 5


async def test_a_step_off_the_grid_stops_the_batch_and_the_steps_before_it_stand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            move(directions=["left", "left", "up"]),
            end_round(),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "Stopped after 1 of 3 steps: Moving left from row 2, col 1 leaves the grid" in a_result
    assert [m.direction for m in result.of_type(event_type=SignalGameMoveMade)] == ["left"]
    assert resolved(result=result).final_squares[PLAYER_A] == (2, 1)


async def test_there_is_no_stay_move(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["stay"]), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert result.of_type(event_type=SignalGameMoveMade) == []
    assert resolved(result=result).moves_used[PLAYER_A] == 0


async def test_a_batch_longer_than_the_moves_left_stops_at_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, "moves_per_round": 2})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["up", "down", "up"]), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "Stopped after 2 of 3 steps: You have no moves left" in a_result
    assert resolved(result=result).moves_used[PLAYER_A] == 2


@pytest.mark.parametrize("directions", [[], ["up"] * (MAX_MOVES_PER_CALL + 1)])
async def test_an_empty_or_overlong_batch_moves_nothing(
    directions: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=directions), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [a_result] = results_for(result=result, agent_id=PLAYER_A, tool_name="move")
    assert "Nothing was moved" in a_result
    assert result.of_type(event_type=SignalGameMoveMade) == []


def recording_runner_settings(monkeypatch: pytest.MonkeyPatch) -> list[ModelSettings]:
    """Record the settings the runner builds for each agent, in registration order."""
    requested: list[ModelSettings] = []

    def recording_settings(
        provider: Provider, model: str, settings: AgentModelSettings
    ) -> ModelSettings:
        built = agent_model_settings(provider=provider, model=model, settings=settings)
        requested.append(built)
        return built

    monkeypatch.setattr(
        "glossogen.runners.pydantic_ai_runner.agent_model_settings", recording_settings
    )
    return requested


@pytest.mark.parametrize("preset_name", ["knobs_default", "knobs_shared_colours_control"])
async def test_the_runner_asks_the_provider_for_one_tool_call_per_response(
    preset_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With parallel calls a model can move, end the round and wait in one response.

    The presets say so through the knob, so the run records it.
    """
    requested = recording_runner_settings(monkeypatch=monkeypatch)
    scenario = build(preset_name=preset_name, overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert [sent.get("parallel_tool_calls") for sent in requested] == [False, False]
    assert [
        event.model_settings.parallel_tool_calls
        for event in result.of_type(event_type=AgentRegistered)
    ] == [False, False]


async def test_the_settings_a_run_starts_with_win_over_the_presets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scenario never reads the knob: the supervisor fills each agent in from it."""
    requested = recording_runner_settings(monkeypatch=monkeypatch)
    run_settings = {"max_tokens": 2048, "thinking": "low", "parallel_tool_calls": True}
    scenario = build(
        preset_name="knobs_default",
        overrides={**ONE_ROUND, "agent_model_settings": run_settings},
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    sent = [
        (each.get("max_tokens"), each.get("thinking"), each.get("parallel_tool_calls"))
        for each in requested
    ]
    assert sent == [(2048, "low", True), (2048, "low", True)]
    expected = AgentModelSettings.model_validate(run_settings)
    assert [event.model_settings for event in result.of_type(event_type=AgentRegistered)] == [
        expected,
        expected,
    ]


def test_each_player_reads_the_colours_in_its_own_order_and_is_told_so() -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    prompts = {
        agent.agent_id: agent.system_prompt
        for agent in scenario.get_agents(default_model="test", default_provider="anthropic")
    }
    assert "these colours: green, yellow, red, blue." in prompts[PLAYER_A]
    assert "these colours: blue, green, red, yellow." in prompts[PLAYER_B]
    for prompt in prompts.values():
        assert "drawn at random for you alone, and it stays the same in every round" in prompt
        assert "your partner's instructions list the same colours in an order drawn" in prompt


async def test_every_round_logs_the_order_each_player_reads_the_colours_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    one_round: list[ScriptedTurn] = [end_round(), wait_for_next_round()]
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), *one_round, *one_round],
        PLAYER_B: [read(), *one_round, *one_round],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    expected = {
        PLAYER_A: ["green", "yellow", "red", "blue"],
        PLAYER_B: ["blue", "green", "red", "yellow"],
    }
    started_rounds = result.of_type(event_type=SignalGameRoundStarted)
    assert [started.colour_orders for started in started_rounds] == [expected, expected]


def test_no_prompt_or_briefing_states_how_many_rounds_the_game_has() -> None:
    """Players learn the game is over only when it ends, as the paper's did."""
    scenario = build(preset_name="knobs_default", overrides={"round_count": 7})
    for agent in scenario.get_agents(default_model="test", default_provider="anthropic"):
        assert "7" not in agent.system_prompt
    briefing = scenario.get_injection(round_number=1, agent_id=PLAYER_A)
    assert briefing.startswith("ROUND 1\n")
    assert "7" not in briefing
