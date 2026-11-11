"""What the run-detail panel is handed for a signal_game run."""

from pathlib import Path

import pytest

from glossogen.models.event import WaitRegistered
from glossogen.models.wait_for import WaitFor
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)
from glossogen.scenarios.signal_game.ids import BOTH_FINISHED_TRIGGER, PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game.run_detail_extension import (
    SignalGameCell,
    SignalGameItem,
    SignalGameRunDetailExtension,
    SignalGameRunExtras,
    SignalGameWait,
)
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
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


def extras_of(result: SimulationResult) -> SignalGameRunExtras:
    return SignalGameRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )


async def played_with_shapes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    """Round 1 of ``knobs_coloured_shapes``: player_a bounces right and back, player_b
    steps down. Both start on row 2, col 2."""
    scenario = build(preset_name="knobs_coloured_shapes", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), move(directions=["right", "left"]), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), move(directions=["down"]), end_round(), wait_for_next_round()],
    }
    return await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )


def test_the_scenario_offers_the_extension() -> None:
    assert isinstance(SignalGameScenario.run_detail_extension(), SignalGameRunDetailExtension)


async def test_each_square_reaches_the_panel_as_a_colour_and_a_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played_with_shapes(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_view] = extras.cases
    assert round_view.grid_size == 3
    assert [side.agent_id for side in round_view.players] == [PLAYER_A, PLAYER_B]
    side_a, side_b = round_view.players
    assert side_a.grid[1] == [
        SignalGameItem(colour="blue", shape="circle", fill=None, word=None),
        SignalGameItem(colour="blue", shape="circle", fill=None, word=None),
        SignalGameItem(colour="red", shape="star", fill=None, word=None),
    ]
    assert side_a.shape_order == ["triangle", "star", "circle"]
    assert side_b.shape_order == ["circle", "triangle", "star"]
    assert side_a.fill_order == []
    assert (
        SignalGameItem(colour="blue", shape="circle", fill=None, word=None)
        in round_view.shared_items
    )
    assert round_view.chance == pytest.approx(12 / 81)


async def test_both_players_actions_keep_one_numbering_and_end_round_takes_its_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played_with_shapes(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_view] = extras.cases
    side_a, side_b = round_view.players
    numbers = sorted(
        [step.sequence for step in side_a.steps]
        + [step.sequence for step in side_b.steps]
        + [side.end_sequence for side in round_view.players if side.end_sequence is not None]
    )
    assert numbers == [1, 2, 3, 4, 5]
    assert [step.direction for step in side_a.steps] == ["right", "left"]
    assert [step.cell for step in side_a.steps] == [
        SignalGameCell(row=2, col=3),
        SignalGameCell(row=2, col=2),
    ]
    assert side_a.steps[0].reasoning == "Scripted move."
    assert side_a.end_reasoning == "Scripted end."
    assert side_a.end_sequence is not None
    assert side_a.end_sequence > side_a.steps[-1].sequence


async def test_the_outcome_names_each_players_final_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played_with_shapes(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_view] = extras.cases
    side_a, side_b = round_view.players
    assert round_view.success is False
    assert round_view.trigger == BOTH_FINISHED_TRIGGER
    assert side_a.final_cell == SignalGameCell(row=2, col=2)
    assert side_a.final_item == SignalGameItem(colour="blue", shape="circle", fill=None, word=None)
    assert side_b.final_cell == SignalGameCell(row=3, col=2)
    assert side_b.final_item == SignalGameItem(colour="red", shape="circle", fill=None, word=None)


async def test_a_colour_only_run_has_no_shapes(
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

    [round_view] = extras_of(result=result).cases
    side_a, _ = round_view.players
    assert side_a.grid[0] == [
        SignalGameItem(colour="red", shape=None, fill=None, word=None),
        SignalGameItem(colour="red", shape=None, fill=None, word=None),
    ]
    assert side_a.shape_order == []
    assert side_a.steps == []
    assert round_view.chance == pytest.approx(6 / 16)


async def test_with_fills_each_square_reaches_the_panel_with_its_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_coloured_shapes_fill", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [round_view] = extras_of(result=result).cases
    side_a, side_b = round_view.players
    assert round_view.grid_size == 5
    assert side_a.grid[0][0] == SignalGameItem(colour="red", shape="star", fill="hollow", word=None)
    assert sorted(side_a.fill_order) == ["hollow", "solid", "striped"]
    assert side_a.fill_order != side_b.fill_order


def test_a_resumed_round_shows_only_the_attempt_that_resolved() -> None:
    """``--resume`` reopens the unfinished round: the log gets a second round_started for
    it, the players restart on their start squares and the sequence starts again at 1."""
    grid = [["red", "blue"], ["blue", "red"]]
    started = SignalGameRoundStarted(
        round_number=1,
        grids={PLAYER_A: grid, PLAYER_B: grid},
        start_squares={PLAYER_A: (1, 1), PLAYER_B: (1, 1)},
        moves_per_round=10,
        partner_colours_visible=False,
    )
    before_crash = SignalGameMoveMade(
        round_number=1,
        agent_id=PLAYER_A,
        sequence=1,
        direction="right",
        from_square=(1, 1),
        to_square=(1, 2),
        moves_used=1,
    )
    after_resume = SignalGameMoveMade(
        round_number=1,
        agent_id=PLAYER_A,
        sequence=1,
        direction="down",
        from_square=(1, 1),
        to_square=(2, 1),
        moves_used=1,
    )
    resolved = SignalGameRoundResolved(
        round_number=1,
        final_squares={PLAYER_A: (2, 1), PLAYER_B: (1, 1)},
        final_colours={PLAYER_A: "blue", PLAYER_B: "red"},
        moves_used={PLAYER_A: 1, PLAYER_B: 0},
        success=False,
        trigger=BOTH_FINISHED_TRIGGER,
    )
    extras = SignalGameRunDetailExtension().build_extras(
        events=[started, before_crash, started.model_copy(), after_resume, resolved],
        agents_by_id={},
        messages=[],
    )

    [round_view] = extras.cases
    side_a = round_view.players[0]
    assert [step.direction for step in side_a.steps] == ["down"]


async def test_with_words_each_square_reaches_the_panel_as_its_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_words", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [round_view] = extras_of(result=result).cases
    side_a, _ = round_view.players
    assert round_view.grid_size == 3
    assert side_a.grid[0][0] == SignalGameItem(colour=None, shape=None, fill=None, word="frog")
    assert (
        SignalGameItem(colour=None, shape=None, fill=None, word="knife") in round_view.shared_items
    )
    assert side_a.colour_order == []
    assert round_view.chance == pytest.approx(1 / 81)


def reasoned_wait(wait_for: str, reasoning: str) -> ToolTurn:
    return ToolTurn(
        tool_name="read_notifications", args={"wait_for": wait_for, "reasoning": reasoning}
    )


async def test_each_wait_reaches_the_panel_after_the_action_it_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(
        preset_name="knobs_coloured_shapes", overrides={**ONE_ROUND, "wait_reasoning": True}
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            reasoned_wait(wait_for="any", reasoning="Taking the briefing."),
            move(directions=["right", "left"]),
            end_round(),
            reasoned_wait(wait_for="next_round", reasoning="My square is final."),
        ],
        PLAYER_B: [
            reasoned_wait(wait_for="any", reasoning="Taking the briefing."),
            move(directions=["down"]),
            end_round(),
            reasoned_wait(wait_for="next_round", reasoning="My square is final."),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    [round_view] = extras_of(result=result).cases
    side_a, _ = round_view.players
    assert side_a.waits[0] == SignalGameWait(
        after_sequence=0, wait_for="any", timeout_s=None, reasoning="Taking the briefing."
    )
    [final_wait] = [wait for wait in side_a.waits if wait.wait_for == "next_round"]
    assert final_wait.reasoning == "My square is final."
    # Both players had ended by then, so the wait follows the round's last action.
    assert final_wait.after_sequence == max(
        side.end_sequence for side in round_view.players if side.end_sequence is not None
    )


async def test_a_wait_without_the_knob_reaches_the_panel_without_a_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played_with_shapes(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_view] = extras.cases
    side_a, _ = round_view.players
    assert "next_round" in [wait.wait_for for wait in side_a.waits]
    assert all(wait.reasoning is None for wait in side_a.waits)


def round_two_started(result: SimulationResult) -> SignalGameRoundStarted:
    """Round 1's start event, renumbered as round 2's."""
    started = next(e for e in result.events if isinstance(e, SignalGameRoundStarted))
    return started.model_copy(update={"round_number": 2})


def closing_wait(result: SimulationResult, agent_id: str) -> WaitRegistered:
    """``agent_id``'s ``next_round`` wait in round 1."""
    return next(
        e
        for e in result.events
        if isinstance(e, WaitRegistered)
        and e.agent_id == agent_id
        and e.wait_for == WaitFor.NEXT_ROUND
        and e.round_number == 1
    )


async def test_a_closing_wait_logged_after_the_clock_advanced_is_filed_under_its_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await played_with_shapes(tmp_path=tmp_path, monkeypatch=monkeypatch)
    late = closing_wait(result=result, agent_id=PLAYER_B)
    # The race: player_b's closing wait registers once round 2 has started.
    events = [e for e in result.events if e is not late]
    events += [round_two_started(result=result), late.model_copy(update={"round_number": 2})]

    extras = SignalGameRunDetailExtension().build_extras(
        events=events, agents_by_id={}, messages=[]
    )

    round_one, round_two = extras.cases
    side_b = next(side for side in round_one.players if side.agent_id == PLAYER_B)
    assert "next_round" in [wait.wait_for for wait in side_b.waits]
    last_action = max(side.end_sequence or 0 for side in round_one.players)
    assert side_b.waits[-1].after_sequence == last_action
    round_two_b = next(side for side in round_two.players if side.agent_id == PLAYER_B)
    assert round_two_b.waits == []


async def test_a_next_round_wait_stays_in_its_round_when_the_round_before_has_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await played_with_shapes(tmp_path=tmp_path, monkeypatch=monkeypatch)
    # player_b closed round 1 normally, then waits out round 2 without acting.
    gives_up = closing_wait(result=result, agent_id=PLAYER_B).model_copy(update={"round_number": 2})
    events = [*result.events, round_two_started(result=result), gives_up]

    extras = SignalGameRunDetailExtension().build_extras(
        events=events, agents_by_id={}, messages=[]
    )

    _, round_two = extras.cases
    round_two_b = next(side for side in round_two.players if side.agent_id == PLAYER_B)
    assert [wait.wait_for for wait in round_two_b.waits] == ["next_round"]
