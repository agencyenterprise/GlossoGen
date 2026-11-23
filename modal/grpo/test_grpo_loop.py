"""Tests of the rewards, the advantages, the sequences and the game config, on hand-built events.

A last test checks that the modules that run on Modal parse as Python 3.12.

Run from the repository root:

    VIRTUAL_ENV= uv run --no-sync pytest modal/grpo/test_grpo_loop.py
"""

import ast
import json
from pathlib import Path

from grpo_loop import FinishedGame, Game, seed_advantages
from signal_game_rewards import PlayerRound, Reward, game_outcome, player_score
from token_sequences import answer_rounds, game_sequences

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    StopReason,
    ToolCallInvoked,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)

GRID_A = [["circle-blue", "square-red"], ["triangle-green", "circle-red"]]
GRID_B = [["square-red", "circle-blue"], ["circle-red", "triangle-green"]]


def response(
    *, round_number: int, index: int, prefix: int, tail: list[int], answer: list[int], call_id: str
) -> LLMResponseReceived:
    """A recorded response of player_a; ``call_id`` empty means a text answer."""
    tool_calls: list[ToolCallRequest] = []
    if call_id:
        tool_calls = [ToolCallRequest(call_id=call_id, tool_name="move", arguments={})]
    return LLMResponseReceived(
        round_number=round_number,
        agent_id="player_a",
        text=None,
        tool_calls=tool_calls,
        stop_reason=StopReason.TOOL_USE,
        usage=TokenUsage(
            input_tokens=1,
            output_tokens=1,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
        token_ids_index=index,
        prompt_prefix_tokens=prefix,
        prompt_tail_ids=tail,
        token_ids=answer,
    )


def invoked(*, round_number: int, call_id: str) -> ToolCallInvoked:
    """The invocation of player_a's tool call ``call_id`` in ``round_number``."""
    return ToolCallInvoked(
        round_number=round_number,
        agent_id="player_a",
        call_id=call_id,
        tool_name="move",
        arguments={},
    )


def test_answers_chain_into_one_sequence_with_only_answers_marked() -> None:
    events: list[SimulationEvent] = [
        response(round_number=1, index=0, prefix=0, tail=[1, 2, 3], answer=[4, 5], call_id="c1"),
        invoked(round_number=1, call_id="c1"),
        response(round_number=2, index=1, prefix=5, tail=[6], answer=[7], call_id="c2"),
        invoked(round_number=2, call_id="c2"),
    ]
    built = game_sequences(events=events, agent_id="player_a", advantages={1: 0.5, 2: -0.5})
    assert built.chain_breaks == 0
    [sequence] = built.sequences
    assert sequence.input_ids == [1, 2, 3, 4, 5, 6, 7]
    assert sequence.kl_mask == [0, 0, 0, 1, 1, 0, 1]
    assert sequence.advantages == [0.0, 0.0, 0.0, 0.5, 0.5, 0.0, -0.5]
    assert (built.answers, built.answer_tokens, built.sequence_tokens) == (2, 3, 7)


def test_a_prompt_that_does_not_extend_the_sequence_starts_a_new_one() -> None:
    events: list[SimulationEvent] = [
        response(round_number=1, index=0, prefix=0, tail=[1, 2], answer=[3], call_id="c1"),
        invoked(round_number=1, call_id="c1"),
        response(round_number=1, index=1, prefix=1, tail=[9], answer=[8], call_id="c2"),
        invoked(round_number=1, call_id="c2"),
    ]
    built = game_sequences(events=events, agent_id="player_a", advantages={1: 1.0})
    assert built.chain_breaks == 1
    assert [sequence.input_ids for sequence in built.sequences] == [[1, 2, 3], [1, 9, 8]]
    assert [sequence.kl_mask for sequence in built.sequences] == [[0, 0, 1], [0, 0, 1]]


def test_an_answer_takes_the_round_of_its_tool_call_and_a_text_answer_keeps_the_last() -> None:
    events: list[SimulationEvent] = [
        response(round_number=3, index=0, prefix=0, tail=[1], answer=[2], call_id="c1"),
        invoked(round_number=2, call_id="c1"),
        response(round_number=3, index=1, prefix=2, tail=[3], answer=[4], call_id=""),
    ]
    assert answer_rounds(events=events, agent_id="player_a") == [2, 2]


def signal_game_events(*, final_square_a: tuple[int, int], success: bool) -> list[SimulationEvent]:
    """One resolved round of a two-player game. player_b always ends on (1, 1)."""
    registered = [
        AgentRegistered(
            round_number=0,
            agent_id=player,
            role_name=player,
            system_prompt="",
            channel_ids=[],
            tool_names=["move"],
            model="m",
            provider="self-hosted",
            model_settings=AgentModelSettings(),
        )
        for player in ("player_a", "player_b")
    ]
    return [
        *registered,
        SignalGameRoundStarted(
            round_number=1,
            grids={"player_a": GRID_A, "player_b": GRID_B},
            start_squares={"player_a": (2, 2), "player_b": (2, 2)},
            moves_per_round=10,
            partner_colours_visible=False,
        ),
        SignalGameMoveMade(
            round_number=1,
            agent_id="player_a",
            sequence=1,
            direction="up",
            from_square=(2, 2),
            to_square=(1, 2),
            moves_used=1,
        ),
        SignalGameRoundResolved(
            round_number=1,
            final_squares={"player_a": final_square_a, "player_b": (1, 1)},
            final_colours={"player_a": "blue", "player_b": "red"},
            moves_used={"player_a": 1, "player_b": 0},
            success=success,
            trigger="both_finished",
        ),
        SimulationEnded(
            round_number=1,
            reason=RunStatus.SCENARIO_COMPLETE,
            total_messages=0,
            total_cost_usd=0.0,
        ),
    ]


def test_the_outcome_scores_a_finish_on_the_first_item_and_the_round_result() -> None:
    outcome = game_outcome(events=signal_game_events(final_square_a=(1, 1), success=False))
    assert outcome.finished
    assert outcome.players == ("player_a", "player_b")
    assert outcome.first_item_finishes == {PlayerRound(player="player_a", round_number=1)}
    assert outcome.moves == 1
    assert outcome.player_rounds_without_move == 1
    first_item = PlayerRound(player="player_a", round_number=1)
    assert player_score(outcome=outcome, player_round=first_item, reward=Reward.FIRST_ITEM) == 1
    assert player_score(outcome=outcome, player_round=first_item, reward=Reward.WIN) == 0


def finished_game(*, run_id: str, final_square_a: tuple[int, int]) -> FinishedGame:
    """A finished one-round game on seed 1000."""
    events = signal_game_events(final_square_a=final_square_a, success=False)
    return FinishedGame(
        game=Game(seed=1000, game=1, run_id=run_id, returncode=0),
        events=events,
        outcome=game_outcome(events=events),
    )


def test_an_advantage_is_the_score_minus_the_mean_of_the_seed() -> None:
    group = [
        finished_game(run_id="signal_game/1", final_square_a=(1, 1)),
        finished_game(run_id="signal_game/2", final_square_a=(2, 2)),
    ]
    advantages = {
        (advantage.run_id, advantage.player_round.player): advantage.advantage
        for advantage in seed_advantages(group=group, reward=Reward.FIRST_ITEM)
    }
    assert advantages == {
        ("signal_game/1", "player_a"): 0.5,
        ("signal_game/2", "player_a"): -0.5,
        ("signal_game/1", "player_b"): 0.0,
        ("signal_game/2", "player_b"): 0.0,
    }


def test_a_seed_with_one_finished_game_gives_no_advantage() -> None:
    group = [finished_game(run_id="signal_game/1", final_square_a=(1, 1))]
    assert seed_advantages(group=group, reward=Reward.FIRST_ITEM) == []


def test_the_shipped_game_config_records_token_ids() -> None:
    config = json.loads((Path(__file__).parent / "signal_game_shapes.json").read_text())
    assert config["record_token_ids"] is True


def test_the_modules_that_run_on_modal_parse_as_python_3_12() -> None:
    # The Modal images run Python 3.12, and black formats this repository for 3.14.
    for name in ("grpo_app.py", "grpo_training.py", "grpo_records.py"):
        source = (Path(__file__).parent / name).read_text()
        ast.parse(source, filename=name, feature_version=(3, 12))
