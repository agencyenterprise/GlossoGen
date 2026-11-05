"""A run summary lists each model an agent played, at its reasoning effort, from its first round."""

from pathlib import Path

import orjson
from pydantic_ai.settings import ThinkingLevel

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    AgentSwappedMidRun,
    InjectionDelivered,
    RoundAdvanced,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
)
from glossogen.server.runs.discovery import build_summary
from glossogen.server.runs.models import PlayedModel, RunSummary


def _registered(
    agent_id: str, model: str, provider: str, thinking: ThinkingLevel | None
) -> AgentRegistered:
    return AgentRegistered(
        round_number=0,
        agent_id=agent_id,
        role_name=agent_id,
        model=model,
        provider=provider,
        system_prompt="",
        channel_ids=["link"],
        tool_names=["read_channel"],
        model_settings=AgentModelSettings(max_tokens=16384, thinking=thinking),
    )


def _advanced(round_number: int) -> RoundAdvanced:
    return RoundAdvanced(round_number=round_number, trigger="all_agents_idle")


def _swapped(
    agent_id: str,
    model: str,
    provider: str,
    model_settings: AgentModelSettings | None,
    round_number: int,
) -> AgentSwappedMidRun:
    return AgentSwappedMidRun(
        round_number=round_number,
        agent_id=agent_id,
        new_model=model,
        new_provider=provider,
        channel_visibility={},
        model_settings=model_settings,
    )


def _write_run(run_dir: Path, events: list[SimulationEvent]) -> None:
    run_dir.mkdir(parents=True)
    logged: list[SimulationEvent] = [
        SimulationStarted(
            round_number=0,
            run_id=run_dir.name,
            scenario_name="smoke",
            scenario_description="played models run",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={"round_count": 4},
        ),
        *events,
        SimulationEnded(
            round_number=4,
            reason=RunStatus.SCENARIO_COMPLETE,
            total_messages=0,
            total_cost_usd=0.0,
        ),
    ]
    (run_dir / "smoke.jsonl").write_bytes(
        b"\n".join(event.model_dump_json().encode() for event in logged) + b"\n"
    )


async def _summary(run_dir: Path) -> RunSummary:
    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )
    assert summary is not None
    return summary


async def _played(run_dir: Path) -> dict[str, list[PlayedModel]]:
    summary = await _summary(run_dir=run_dir)
    return {agent.agent_id: agent.played for agent in summary.agent_models}


def _model(
    model: str, provider: str, thinking: ThinkingLevel | None, from_round: int
) -> PlayedModel:
    return PlayedModel(model=model, provider=provider, thinking=thinking, from_round=from_round)


async def test_an_agent_that_kept_its_model_played_it_from_round_one(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="left", model="claude-opus-5-5", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _advanced(round_number=2),
        ],
    )

    assert await _played(run_dir=run_dir) == {
        "left": [_model(model="claude-opus-5-5", provider="anthropic", thinking=None, from_round=1)]
    }


async def test_a_mid_run_swap_to_another_model_starts_in_its_round(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="left", model="claude-opus-5-5", provider="anthropic", thinking=None
            ),
            _registered(
                agent_id="right", model="claude-opus-5-5", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _advanced(round_number=2),
            _advanced(round_number=3),
            _swapped(
                agent_id="left",
                model="gpt-5.6-luna",
                provider="openai",
                model_settings=None,
                round_number=3,
            ),
        ],
    )

    played = await _played(run_dir=run_dir)

    assert played["left"] == [
        _model(model="claude-opus-5-5", provider="anthropic", thinking=None, from_round=1),
        _model(model="gpt-5.6-luna", provider="openai", thinking=None, from_round=3),
    ]
    assert played["right"] == [
        _model(model="claude-opus-5-5", provider="anthropic", thinking=None, from_round=1)
    ]
    # The second listing reads the cache the first one wrote.
    assert await _played(run_dir=run_dir) == played


async def test_a_swap_to_the_same_model_adds_nothing(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="left", model="claude-sonnet-4-6", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _advanced(round_number=2),
            _swapped(
                agent_id="left",
                model="claude-sonnet-4-6",
                provider="anthropic",
                model_settings=None,
                round_number=2,
            ),
        ],
    )

    assert await _played(run_dir=run_dir) == {
        "left": [
            _model(model="claude-sonnet-4-6", provider="anthropic", thinking=None, from_round=1)
        ]
    }


async def test_a_replacement_registered_after_the_entry_round_opened_starts_there(
    tmp_path: Path,
) -> None:
    # A replace-agent fork whose source played past the boundary: the copied
    # prefix ends with the entry round's RoundAdvanced, then the agents re-register.
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="observer", model="claude-sonnet-4-6", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _advanced(round_number=2),
            _advanced(round_number=3),
            _registered(
                agent_id="observer",
                model="meta-llama/Llama-3.3-70B-Instruct",
                provider="self-hosted",
                thinking=None,
            ),
            InjectionDelivered(round_number=3, agent_id="observer", text="Round 3 begins."),
            _advanced(round_number=4),
        ],
    )

    assert await _played(run_dir=run_dir) == {
        "observer": [
            _model(model="claude-sonnet-4-6", provider="anthropic", thinking=None, from_round=1),
            _model(
                model="meta-llama/Llama-3.3-70B-Instruct",
                provider="self-hosted",
                thinking=None,
                from_round=3,
            ),
        ]
    }


async def test_a_replacement_registered_before_the_entry_round_opened_starts_there(
    tmp_path: Path,
) -> None:
    # A replace-agent fork whose source finished at the boundary: the agents
    # re-register before the resumed clock advances into the entry round.
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="observer", model="claude-sonnet-4-6", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _advanced(round_number=2),
            _registered(
                agent_id="observer",
                model="meta-llama/Llama-3.3-70B-Instruct",
                provider="self-hosted",
                thinking=None,
            ),
            _advanced(round_number=3),
        ],
    )

    assert await _played(run_dir=run_dir) == {
        "observer": [
            _model(model="claude-sonnet-4-6", provider="anthropic", thinking=None, from_round=1),
            _model(
                model="meta-llama/Llama-3.3-70B-Instruct",
                provider="self-hosted",
                thinking=None,
                from_round=3,
            ),
        ]
    }


async def test_a_cache_written_before_played_models_is_rescanned(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="left", model="claude-opus-5-5", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _swapped(
                agent_id="left",
                model="gpt-5.6-luna",
                provider="openai",
                model_settings=None,
                round_number=1,
            ),
        ],
    )
    await _summary(run_dir=run_dir)
    cache_path = run_dir / "run_summary_cache.json"
    old_cache = orjson.loads(cache_path.read_bytes())
    for agent in old_cache["agent_models"]:
        del agent["played"]
    cache_path.write_bytes(orjson.dumps(old_cache))

    assert await _played(run_dir=run_dir) == {
        "left": [
            _model(model="claude-opus-5-5", provider="anthropic", thinking=None, from_round=1),
            _model(model="gpt-5.6-luna", provider="openai", thinking=None, from_round=1),
        ]
    }
    rewritten = orjson.loads(cache_path.read_bytes())
    assert all("played" in agent for agent in rewritten["agent_models"])


async def test_each_model_played_carries_the_reasoning_effort_it_was_sent(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="left", model="claude-opus-5-5", provider="anthropic", thinking="high"
            ),
            _registered(
                agent_id="right", model="claude-opus-5-5", provider="anthropic", thinking=None
            ),
            _advanced(round_number=1),
            _advanced(round_number=2),
            _swapped(
                agent_id="left",
                model="gpt-6.1-sol",
                provider="openai",
                model_settings=AgentModelSettings(max_tokens=16384, thinking="low"),
                round_number=2,
            ),
        ],
    )

    assert await _played(run_dir=run_dir) == {
        "left": [
            _model(model="claude-opus-5-5", provider="anthropic", thinking="high", from_round=1),
            _model(model="gpt-6.1-sol", provider="openai", thinking="low", from_round=2),
        ],
        "right": [
            _model(model="claude-opus-5-5", provider="anthropic", thinking=None, from_round=1)
        ],
    }


async def test_a_swap_that_changes_only_the_reasoning_effort_starts_in_its_round(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(agent_id="left", model="gpt-6.1-sol", provider="openai", thinking="low"),
            _advanced(round_number=1),
            _advanced(round_number=2),
            _advanced(round_number=3),
            _swapped(
                agent_id="left",
                model="gpt-6.1-sol",
                provider="openai",
                model_settings=AgentModelSettings(max_tokens=16384, thinking="high"),
                round_number=3,
            ),
        ],
    )

    assert await _played(run_dir=run_dir) == {
        "left": [
            _model(model="gpt-6.1-sol", provider="openai", thinking="low", from_round=1),
            _model(model="gpt-6.1-sol", provider="openai", thinking="high", from_round=3),
        ]
    }


async def test_a_cache_written_before_reasoning_effort_is_rescanned(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    _write_run(
        run_dir=run_dir,
        events=[
            _registered(
                agent_id="left", model="claude-opus-5-5", provider="anthropic", thinking="high"
            ),
            _advanced(round_number=1),
        ],
    )
    await _summary(run_dir=run_dir)
    cache_path = run_dir / "run_summary_cache.json"
    old_cache = orjson.loads(cache_path.read_bytes())
    for agent in old_cache["agent_models"]:
        for played in agent["played"]:
            del played["thinking"]
    cache_path.write_bytes(orjson.dumps(old_cache))

    assert await _played(run_dir=run_dir) == {
        "left": [
            _model(model="claude-opus-5-5", provider="anthropic", thinking="high", from_round=1)
        ]
    }
    rewritten = orjson.loads(cache_path.read_bytes())
    assert all(
        "thinking" in played for agent in rewritten["agent_models"] for played in agent["played"]
    )
