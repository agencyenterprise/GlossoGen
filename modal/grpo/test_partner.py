"""Tests of the frozen partner: its file, its game config, its URLs and the seats that train.

Run from the repository root:

    VIRTUAL_ENV= uv run --no-sync pytest modal/grpo/test_partner.py
"""

import json
from pathlib import Path

import pytest
from grpo_loop import (
    FinishedGame,
    Game,
    LoopSettings,
    batch,
    first_item_by_seat,
    seed_config,
    step_advantages,
)
from grpo_records import BASE_MODEL
from partner import Partner, load_partner, partner_labels, self_hosted_urls, trained_seats
from pydantic import ValidationError
from signal_game_rewards import Reward, game_outcome

from glossogen.model_catalog.provider_catalog import Provider
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
from glossogen.scenario_contract.base_knobs import AgentModelOverride
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)
from glossogen.scenarios.signal_game.events import SignalGameRoundResolved, SignalGameRoundStarted

HERE = Path(__file__).resolve().parent
GRID = [["blue-circle", "red-star"], ["green-star", "red-circle"]]


def base_partner(*, seat: str) -> Partner:
    """The base model, served by the policy server, in ``seat``."""
    return Partner(
        seat=seat,
        model_override=AgentModelOverride(
            model=BASE_MODEL, provider=Provider.SELF_HOSTED, model_settings=None
        ),
        base_url=None,
    )


def settings(*, tmp_path: Path) -> LoopSettings:
    """Loop settings with the shipped game config and folders under ``tmp_path``."""
    return LoopSettings(
        app_name="app",
        run_name="run",
        runs_dir=tmp_path / "runs",
        records_dir=tmp_path / "records",
        game_config=HERE / "signal_game_shapes.json",
        concurrency=1,
    )


def test_the_shipped_partner_file_is_the_base_model_in_player_b() -> None:
    partner = load_partner(path=HERE / "base_model_partner.json")
    assert partner == base_partner(seat="player_b")
    assert partner.self_hosted()


def test_a_self_hosted_partner_other_than_the_base_model_needs_a_base_url() -> None:
    override = AgentModelOverride(model="other-model", provider=None, model_settings=None)
    with pytest.raises(ValidationError, match="needs a base_url"):
        Partner(seat="player_b", model_override=override, base_url=None)
    served = Partner(seat="player_b", model_override=override, base_url="http://other/v1")
    assert self_hosted_urls(policy_model="run-step3", url="http://policy/v1", partner=served) == {
        "run-step3": "http://policy/v1",
        "other-model": "http://other/v1",
    }


def test_the_base_model_and_a_hosted_partner_take_no_base_url() -> None:
    hosted = AgentModelOverride.model_validate({"model": "claude-x", "provider": "anthropic"})
    with pytest.raises(ValidationError, match="only for a self-hosted partner"):
        Partner(seat="player_b", model_override=hosted, base_url="http://other/v1")
    partner = Partner(seat="player_b", model_override=hosted, base_url=None)
    assert self_hosted_urls(policy_model="run-step3", url="http://policy/v1", partner=partner) == {
        "run-step3": "http://policy/v1"
    }
    on_policy_server = base_partner(seat="player_a")
    assert self_hosted_urls(
        policy_model="run-step3", url="http://policy/v1", partner=on_policy_server
    ) == {"run-step3": "http://policy/v1", BASE_MODEL: "http://policy/v1"}


def test_the_partner_seat_does_not_train_and_is_labelled() -> None:
    players = ("player_a", "player_b")
    assert trained_seats(players=players, partner=None) == players
    assert trained_seats(players=players, partner=base_partner(seat="player_b")) == ("player_a",)
    assert partner_labels(partner=base_partner(seat="player_b")) == [
        "partner_seat=player_b",
        f"partner={BASE_MODEL}",
    ]


def test_a_seed_config_gives_the_partner_its_seat_and_keeps_a_run_on_one_config(
    tmp_path: Path,
) -> None:
    load_configured_scenario_catalog_unless_loaded()
    loop = settings(tmp_path=tmp_path)
    partner = base_partner(seat="player_b")
    path = seed_config(settings=loop, seed=1000, partner=partner)
    assert path.name == "seed_1000_vs_player_b-Qwen-Qwen3.8-27B.json"
    config = json.loads(path.read_text())
    assert config["seed"] == 1000
    assert config["model_overrides"] == {
        "player_b": {"model": BASE_MODEL, "provider": "self-hosted"}
    }
    alone = json.loads(seed_config(settings=loop, seed=1000, partner=None).read_text())
    assert alone["model_overrides"] == {}
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps({**config, "model_overrides": {}, "round_count": 3}))
    with pytest.raises(ValueError, match="differs from the config"):
        seed_config(settings=loop._replace(game_config=changed), seed=1000, partner=partner)


def test_a_partner_seat_that_the_scenario_lacks_is_refused(tmp_path: Path) -> None:
    load_configured_scenario_catalog_unless_loaded()
    with pytest.raises(ValueError, match="is not one of"):
        seed_config(settings=settings(tmp_path=tmp_path), seed=1000, partner=base_partner(seat="x"))


def registered(*, player: str) -> AgentRegistered:
    """The registration of one player."""
    return AgentRegistered(
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


def answered(*, player: str, call_id: str) -> list[SimulationEvent]:
    """One recorded answer of ``player`` in round 1: a tool call of two tokens."""
    return [
        LLMResponseReceived(
            round_number=1,
            agent_id=player,
            text=None,
            tool_calls=[ToolCallRequest(call_id=call_id, tool_name="move", arguments={})],
            stop_reason=StopReason.TOOL_USE,
            usage=TokenUsage(
                input_tokens=1,
                output_tokens=2,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
            token_ids_index=0,
            prompt_prefix_tokens=0,
            prompt_tail_ids=[1, 2],
            token_ids=[3, 4],
            token_logprobs=[-0.5, -0.25],
        ),
        ToolCallInvoked(
            round_number=1, agent_id=player, call_id=call_id, tool_name="move", arguments={}
        ),
    ]


def finished_game(*, game: int, final_square_a: tuple[int, int]) -> FinishedGame:
    """A one-round game on seed 1000 in which both players answered once."""
    events: list[SimulationEvent] = [
        registered(player="player_a"),
        registered(player="player_b"),
        SignalGameRoundStarted(
            round_number=1,
            grids={"player_a": GRID, "player_b": GRID},
            start_squares={"player_a": (2, 2), "player_b": (2, 2)},
            moves_per_round=10,
            partner_colours_visible=False,
        ),
        *answered(player="player_a", call_id=f"a{game}"),
        *answered(player="player_b", call_id=f"b{game}"),
        SignalGameRoundResolved(
            round_number=1,
            final_squares={"player_a": final_square_a, "player_b": (1, 1)},
            final_colours={"player_a": "blue", "player_b": "blue"},
            moves_used={"player_a": 1, "player_b": 1},
            success=False,
            trigger="both_finished",
        ),
        SimulationEnded(
            round_number=1,
            reason=RunStatus.SCENARIO_COMPLETE,
            total_messages=0,
            total_cost_usd=0.0,
        ),
    ]
    return FinishedGame(
        game=Game(seed=1000, game=game, run_id=f"signal_game/{game}", returncode=0),
        events=events,
        outcome=game_outcome(events=events),
    )


def test_only_the_trained_seat_builds_sequences_and_its_advantage_is_its_own() -> None:
    finished = [
        finished_game(game=1, final_square_a=(1, 1)),
        finished_game(game=2, final_square_a=(2, 2)),
    ]
    advantages = step_advantages(finished=finished, reward=Reward.FIRST_ITEM)
    both = batch(finished=finished, advantages=advantages, partner=None)
    alone = batch(finished=finished, advantages=advantages, partner=base_partner(seat="player_b"))
    assert (both.answers, alone.answers) == (4, 2)
    assert [sequence.advantages for sequence in alone.sequences] == [
        [0.0, 0.0, 0.5, 0.5],
        [0.0, 0.0, -0.5, -0.5],
    ]
    assert first_item_by_seat(finished=finished) == {"player_a": 1, "player_b": 2}
