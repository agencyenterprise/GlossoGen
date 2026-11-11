"""The spend a run's log records, and the runs list agreeing with the detail page on it.

Priced at a flat $1 per token, so each response below costs its input plus
output tokens.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
    StopReason,
)
from glossogen.models.event_base import TokenUsage
from glossogen.run_replay.recorded_run_spend import recorded_run_spend_usd
from glossogen.run_storage.run_discovery import build_summary
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.token_pricing import TokenPricing

STARTED_AT = datetime.fromtimestamp(1_700_000_000, tz=UTC)
RUN_DIR_NAME = "1700000000"
AGENT_ID = "first_agent"

DOLLAR_PER_TOKEN = TokenPricing(
    input_per_mtok=1_000_000.0,
    output_per_mtok=1_000_000.0,
    cache_read_per_mtok=1_000_000.0,
    cache_write_per_mtok=1_000_000.0,
)


def flat_pricing(model: str, provider: str, at: datetime) -> TokenPricing:
    """Price every model at a dollar a token."""
    _ = model, provider, at
    return DOLLAR_PER_TOKEN


@pytest.fixture(autouse=True)
def priced_at_a_dollar_per_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every reading of a log prices through ``token_pricing.find_pricing``."""
    monkeypatch.setattr("glossogen.token_pricing.find_pricing", flat_pricing)


def at(seconds: int) -> datetime:
    """A moment ``seconds`` after the run started."""
    return STARTED_AT + timedelta(seconds=seconds)


def started() -> SimulationStarted:
    return SimulationStarted(
        round_number=0,
        run_id=f"smoke/{RUN_DIR_NAME}",
        scenario_name="smoke",
        scenario_description="",
        channel_ids=["link"],
        provider="anthropic",
        scenario_config={},
    ).model_copy(update={"timestamp": STARTED_AT})


def registered() -> AgentRegistered:
    return AgentRegistered(
        round_number=0,
        agent_id=AGENT_ID,
        role_name=AGENT_ID,
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        system_prompt="",
        channel_ids=["link"],
        tool_names=["read_channel"],
        model_settings=AgentModelSettings(max_tokens=16384),
    ).model_copy(update={"timestamp": STARTED_AT})


def response(*, tokens: int, seconds: int) -> LLMResponseReceived:
    """A response whose input and output come to ``tokens``, so it costs ``tokens`` dollars."""
    return LLMResponseReceived(
        round_number=1,
        agent_id=AGENT_ID,
        text="sent",
        tool_calls=[],
        stop_reason=StopReason.END_TURN,
        usage=TokenUsage(
            input_tokens=tokens - 1,
            output_tokens=1,
            reasoning_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    ).model_copy(update={"timestamp": at(seconds=seconds)})


def ended(*, reason: RunStatus, total_cost_usd: float, seconds: int) -> SimulationEnded:
    return SimulationEnded(
        round_number=1,
        reason=reason,
        total_messages=0,
        total_cost_usd=total_cost_usd,
    ).model_copy(update={"timestamp": at(seconds=seconds)})


def test_the_last_end_carries_the_spend_before_it() -> None:
    """An end's total covers everything before it; only the usage after it is added."""
    events: list[SimulationEvent] = [
        started(),
        registered(),
        response(tokens=10, seconds=1),
        ended(reason=RunStatus.ERROR, total_cost_usd=12.0, seconds=2),
        response(tokens=5, seconds=3),
    ]

    assert recorded_run_spend_usd(events=events, own_events_from=None) == pytest.approx(17.0)


def test_an_end_that_recorded_nothing_falls_back_to_the_usage_before_it() -> None:
    """A failed process logged by an older build wrote ``0.0`` though its agents spent."""
    events: list[SimulationEvent] = [
        started(),
        registered(),
        response(tokens=10, seconds=1),
        ended(reason=RunStatus.ERROR, total_cost_usd=0.0, seconds=2),
        response(tokens=5, seconds=3),
    ]

    assert recorded_run_spend_usd(events=events, own_events_from=None) == pytest.approx(15.0)


def test_responses_cloned_from_a_source_are_not_the_derived_runs_spend() -> None:
    events: list[SimulationEvent] = [
        started(),
        registered(),
        response(tokens=10, seconds=1),
        response(tokens=5, seconds=30),
    ]

    assert recorded_run_spend_usd(events=events, own_events_from=at(seconds=20)) == (
        pytest.approx(5.0)
    )


async def test_a_failed_run_from_an_older_build_costs_the_same_in_the_list_and_the_detail(
    tmp_path: Path,
) -> None:
    """Both fall back to the token usage when the end recorded no spend.

    The detail page always did. The runs list showed the ``0.0``.
    """
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    events: list[SimulationEvent] = [
        started(),
        registered(),
        response(tokens=10, seconds=1),
        ended(reason=RunStatus.ERROR, total_cost_usd=0.0, seconds=2),
    ]
    log_path = run_dir / "smoke.jsonl"
    log_path.write_bytes(b"\n".join(event.model_dump_json().encode() for event in events) + b"\n")

    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )
    detail = await load_run_detail(log_path=log_path, children=[])

    assert summary is not None
    assert summary.total_cost_usd == pytest.approx(10.0)
    assert detail.total_cost_usd == pytest.approx(10.0)


def _cached_summary(*, total_cost_usd: float, cost_basis: str | None) -> dict[str, Any]:
    """A finished run's summary cache in the current shape, ``cost_basis`` left out when None."""
    cache: dict[str, Any] = {
        "scenario_name": "smoke",
        "scenario_description": "",
        "scenario_config": {},
        "provider": "anthropic",
        "total_messages": 0,
        "total_cost_usd": total_cost_usd,
        "duration_seconds": 2.0,
        "status": "error",
        "models": ["claude-haiku-4-5-20251001"],
        "agent_models": [],
        "current_round": 1,
        "round_results": [],
        "fork_source": None,
        "replace_agent_source": None,
        "cross_run_replace_agent_source": None,
        "fork_at_round_source": None,
    }
    if cost_basis is not None:
        cache["cost_basis"] = cost_basis
    return cache


async def test_a_zero_cost_summary_cached_before_the_fallback_is_rescanned(
    tmp_path: Path,
) -> None:
    """A run listed once at ``0.0`` by an older build gets its token cost on the next listing."""
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    events: list[SimulationEvent] = [
        started(),
        registered(),
        response(tokens=10, seconds=1),
        ended(reason=RunStatus.ERROR, total_cost_usd=0.0, seconds=2),
    ]
    (run_dir / "smoke.jsonl").write_bytes(
        b"\n".join(event.model_dump_json().encode() for event in events) + b"\n"
    )
    (run_dir / "run_summary_cache.json").write_bytes(
        orjson.dumps(_cached_summary(total_cost_usd=0.0, cost_basis=None))
    )

    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )

    assert summary is not None
    assert summary.total_cost_usd == pytest.approx(10.0)


async def test_a_zero_cost_summary_cached_under_the_fallback_is_not_rescanned(
    tmp_path: Path,
) -> None:
    """A run that costs nothing, such as a self-hosted one, is read from its cache.

    The log is unparseable, so an answer can only come from the cache.
    """
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    run_dir.mkdir(parents=True)
    (run_dir / "smoke.jsonl").write_text("this is not json\n")
    (run_dir / "run_summary_cache.json").write_bytes(
        orjson.dumps(_cached_summary(total_cost_usd=0.0, cost_basis="own_events"))
    )

    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )

    assert summary is not None
    assert summary.total_cost_usd == 0.0
