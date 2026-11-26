"""signal_game games as platoon episodes, on CPU with scripted players: each seat that platoon
serves gets a trajectory with one span per round, and a seat outside platoon is neither minted nor
recorded."""

from types import SimpleNamespace
from typing import Any

import pytest
from episodes import play_episode, seat_trajectories
from glossogen_platoon.game_process import SeatModel, game_config, self_hosted_urls
from glossogen_platoon.game_scores import PlayedGame
from glossogen_platoon.program import call_ids
from partner_stub import partner_stub
from platoon.testing import EpisodeRun, ScriptedPolicy
from scripted_player import signal_game_player

EXTERNAL_SEED = 1004


def played_game(*, run: EpisodeRun) -> PlayedGame:
    """What the harness recorded on the episode's root."""
    return PlayedGame.model_validate(run.root.misc["glossogen"])


def test_each_platoon_seat_has_one_span_per_round(first_item_group: list[EpisodeRun]) -> None:
    for run in first_item_group:
        game = played_game(run=run)
        seats = seat_trajectories(run=run)
        assert set(seats) == {"player_a", "player_b"}
        for seat, trajectory in seats.items():
            spans = trajectory.misc["spans"]
            assert len(spans) == len(game.scores.rounds)
            calls_in_spans = sum(len(span["calls"]) for span in spans)
            outside = trajectory.misc["calls_outside_rounds"] + trajectory.misc["empty_calls"]
            assert calls_in_spans + outside == len(trajectory.steps)
            seat_scores = game.scores.seats[seat].scores["first_item"]
            assert [span["reward"] for span in spans] == [
                float(seat_scores[round_number]) for round_number in game.scores.rounds
            ]
            assert trajectory.reward == sum(seat_scores.values())


def test_the_outcome_is_the_trained_reward_per_player_round(
    first_item_group: list[EpisodeRun],
) -> None:
    for run in first_item_group:
        game = played_game(run=run)
        rewards: dict[str, Any] = run.outcome["rewards"]
        finishes = sum(
            sum(seat.scores["first_item"].values()) for seat in game.scores.seats.values()
        )
        assert rewards["reward"] == rewards["first_item"]
        assert rewards["first_item"] == finishes / (2 * len(game.scores.rounds))


async def test_an_external_seat_is_neither_minted_nor_recorded(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "stub-key")
    policy = ScriptedPolicy(script=signal_game_player)
    async with partner_stub() as stub:
        external = {"model": "frozen-partner", "provider": "self-hosted", "base_url": stub.url}
        run = await play_episode(
            seed=EXTERNAL_SEED,
            runs_dir=tmp_path,
            policy=policy,
            external_seats={"player_b": external},
            reward="first_item",
        )
    game = played_game(run=run)
    assert run.outcome["status"] == "scored"
    assert set(game.seat_agents) == {"player_a"}
    assert set(seat_trajectories(run=run)) == {"player_a"}
    assert len(policy.calls) == len(game.scores.seats["player_a"].answer_rounds)
    assert len(stub.calls) == len(game.scores.seats["player_b"].answer_rounds)


def test_a_game_config_that_records_token_ids_is_refused() -> None:
    partner = SeatModel(model="m", provider="self-hosted", base_url="http://x/v1")
    with pytest.raises(ValueError, match="record_token_ids"):
        game_config(base={"record_token_ids": True}, seed=1, player_b=partner)


def test_a_self_hosted_seat_needs_a_url_and_one_url_per_model() -> None:
    without_url = SeatModel(model="m", provider="self-hosted", base_url=None)
    with pytest.raises(ValueError, match="no base_url"):
        self_hosted_urls(seats={"player_b": without_url})
    first = SeatModel(model="m", provider="self-hosted", base_url="http://a/v1")
    second = SeatModel(model="m", provider="self-hosted", base_url="http://b/v1")
    with pytest.raises(ValueError, match="two URLs"):
        self_hosted_urls(seats={"player_a": first, "player_b": second})
    other_provider = SeatModel(model="gpt", provider="openai", base_url=None)
    assert self_hosted_urls(seats={"player_a": first, "player_b": other_provider}) == {
        "m": "http://a/v1"
    }


def recorded_step(*, completion_id: str, content: str | None, tool_calls: list[Any]) -> Any:
    """A trajectory step as platoon's gateway records it, with only the fields the program reads."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return SimpleNamespace(
        misc={"action_misc": {"completion_id": completion_id}, "message": message}
    )


def test_an_empty_answer_matches_no_logged_response() -> None:
    tool_call = {"id": "call-1", "type": "function", "function": {"name": "move", "arguments": "{}"}}
    trajectory = SimpleNamespace(
        steps=[
            recorded_step(completion_id="text", content="I see a blue star.", tool_calls=[]),
            recorded_step(completion_id="empty", content="", tool_calls=[]),
            recorded_step(completion_id="none", content=None, tool_calls=[]),
            recorded_step(completion_id="tool", content=None, tool_calls=[tool_call]),
        ]
    )
    assert call_ids(trajectory=trajectory) == ["text", "tool"]
