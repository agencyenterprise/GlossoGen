"""The closing exchanges on the run page, read back through ``load_run_detail``.

A closing prompt is sent once a run completes, and each agent's exchange is
logged as ``closing_prompt_answered`` or ``closing_prompt_failed``. The run page
shows both after the last round, and the exchange's tokens belong in the run's
token totals: its cost is already in ``SimulationEnded.total_cost_usd``, so
leaving its tokens out makes the two disagree.
"""

from pathlib import Path

import pytest

from glossogen.model_catalog.token_pricing import usage_cost_usd
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    ClosingPromptAnswered,
    ClosingPromptFailed,
    LLMResponseReceived,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
    StopReason,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.server.runs.models import ClosingExchangeStatus, RunDetailResponse
from tests.fakes.local_app import at_second, write_event_log

SCENARIO = "move_a_box"
MODEL = "claude-sonnet-5-5"
PROMPT = "The shift is over. Did you settle on any way of telling each other something?"


def usage(*, output_tokens: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=1000,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def registered(agent_id: str) -> AgentRegistered:
    return AgentRegistered(
        round_number=0,
        timestamp=at_second(0),
        agent_id=agent_id,
        role_name=agent_id,
        model=MODEL,
        provider="anthropic",
        system_prompt="",
        channel_ids=[],
        tool_names=["read_notifications"],
        model_settings=AgentModelSettings(max_tokens=1024),
    )


def played(agent_id: str) -> LLMResponseReceived:
    return LLMResponseReceived(
        round_number=1,
        timestamp=at_second(1),
        agent_id=agent_id,
        text="playing",
        tool_calls=[],
        stop_reason=StopReason.END_TURN,
        usage=usage(output_tokens=10),
    )


def answered(agent_id: str) -> ClosingPromptAnswered:
    return ClosingPromptAnswered(
        event_id=f"closing-{agent_id}",
        round_number=1,
        timestamp=at_second(50),
        agent_id=agent_id,
        model=MODEL,
        prompt=PROMPT,
        answer="Yes: a sled meant the shared bay.",
        usage=usage(output_tokens=200),
    )


def failed(agent_id: str, error_type: str, message: str) -> ClosingPromptFailed:
    return ClosingPromptFailed(
        event_id=f"closing-{agent_id}",
        round_number=1,
        timestamp=at_second(51),
        agent_id=agent_id,
        model=MODEL,
        prompt=PROMPT,
        error_type=error_type,
        message=message,
        usage=usage(output_tokens=0),
    )


async def detail_of(tmp_path: Path, events: list[EventBase]) -> RunDetailResponse:
    """Write ``events`` between a start and an end with no recorded cost, and read the detail."""
    started = SimulationStarted(
        round_number=0,
        timestamp=at_second(0),
        run_id=f"{SCENARIO}/1770000100",
        scenario_name=SCENARIO,
        scenario_description="",
        channel_ids=[],
        provider="anthropic",
        scenario_config={},
    )
    ended = SimulationEnded(
        round_number=1,
        timestamp=at_second(100),
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
    )
    run_dir = write_event_log(
        runs_dir=tmp_path,
        scenario_name=SCENARIO,
        run_dir_name="1770000100",
        events=[started, *events, ended],
        extra_records=[],
    )
    return await load_run_detail(
        log_path=event_log_path(run_dir=run_dir, scenario_name=SCENARIO), children=[]
    )


async def test_answered_and_failed_exchanges_are_both_on_the_page(tmp_path: Path) -> None:
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="operator_a"),
            registered(agent_id="operator_b"),
            registered(agent_id="operator_c"),
            answered(agent_id="operator_a"),
            # What asyncio.timeout raises: a TimeoutError with an empty message.
            failed(agent_id="operator_b", error_type="TimeoutError", message=""),
            failed(agent_id="operator_c", error_type="APIStatusError", message="overloaded"),
        ],
    )

    first, second, third = detail.closing_exchanges
    assert first.agent_id == "operator_a"
    assert first.status is ClosingExchangeStatus.ANSWERED
    assert first.answer == "Yes: a sled meant the shared bay."
    assert first.failure is None
    assert first.prompt == PROMPT
    assert second.agent_id == "operator_b"
    assert second.status is ClosingExchangeStatus.FAILED
    assert second.answer is None
    assert second.failure == "TimeoutError"
    assert third.status is ClosingExchangeStatus.FAILED
    assert third.failure == "APIStatusError: overloaded"


async def test_the_exchange_counts_in_the_run_s_tokens_and_cost(tmp_path: Path) -> None:
    """The run logged no cost, so the page prices every exchange it read, the closing one too."""
    game: list[EventBase] = [registered(agent_id="operator_a"), played(agent_id="operator_a")]
    closing = answered(agent_id="operator_a")
    without = await detail_of(tmp_path=tmp_path / "without", events=game)
    with_closing = await detail_of(tmp_path=tmp_path / "with", events=[*game, closing])

    assert without.agent_token_usage.output_tokens == 10
    assert with_closing.agent_token_usage.output_tokens == 210
    assert with_closing.agent_token_usage.input_tokens == 2000
    closing_cost = usage_cost_usd(
        model=MODEL,
        provider="anthropic",
        at=closing.timestamp,
        input_tokens=closing.usage.input_tokens,
        output_tokens=closing.usage.output_tokens,
        cache_read_tokens=closing.usage.cache_read_input_tokens,
        cache_write_tokens=closing.usage.cache_creation_input_tokens,
    )
    assert closing_cost is not None and closing_cost > 0, "the test model must be priced"
    assert with_closing.total_cost_usd == pytest.approx(without.total_cost_usd + closing_cost)
