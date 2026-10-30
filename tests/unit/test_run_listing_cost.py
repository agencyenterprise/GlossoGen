"""The run listing prices a run's logged responses at the model each agent ran under.

Each response is priced at the rates in effect when it was logged, so a rate that
changes during the run applies only to the responses after the change.

A run without a ``simulation_ended`` event (in progress, starting, crashed) shows
this scanned cost rather than the total the runner records at the end.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import orjson
import pytest

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    AgentSwappedMidRun,
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
)
from glossogen.models.event_base import TokenUsage
from glossogen.server.runs.discovery import scan_jsonl
from glossogen.token_pricing import TokenPricing, compute_token_cost_usd, find_pricing

START = datetime(2026, 9, 1, tzinfo=UTC)
USAGE = TokenUsage(
    input_tokens=100_000,
    output_tokens=2_000,
    reasoning_tokens=0,
    cache_read_input_tokens=60_000,
    cache_creation_input_tokens=10_000,
)


def _at(seconds: int) -> datetime:
    return START + timedelta(seconds=seconds)


def _response(seconds: int) -> LLMResponseReceived:
    return LLMResponseReceived(
        agent_id="field_observer",
        thinking=None,
        text="reading sent",
        tool_calls=[],
        stop_reason=StopReason.END_TURN,
        usage=USAGE,
        round_number=1,
        timestamp=_at(seconds=seconds),
    )


def _cost(pricing: TokenPricing | None) -> float:
    assert pricing is not None
    return compute_token_cost_usd(
        pricing=pricing,
        input_tokens=USAGE.input_tokens,
        output_tokens=USAGE.output_tokens,
        cache_read_tokens=USAGE.cache_read_input_tokens,
        cache_write_tokens=USAGE.cache_creation_input_tokens,
    )


def _started(provider: str) -> SimulationStarted:
    return SimulationStarted(
        run_id="veyru/1788220800",
        scenario_name="veyru",
        scenario_description="",
        channel_ids=["link"],
        scenario_config={"round_count": 3},
        provider=provider,
        round_number=0,
        timestamp=_at(seconds=0),
    )


def _registered(model: str, provider: str, seconds: int) -> AgentRegistered:
    return AgentRegistered(
        agent_id="field_observer",
        role_name="Field Observer",
        system_prompt="You are the field observer.",
        channel_ids=["link"],
        tool_names=["send_message"],
        model=model,
        provider=provider,
        model_settings=AgentModelSettings(max_tokens=2048),
        round_number=0,
        timestamp=_at(seconds=seconds),
    )


def _swapped_run_events() -> list[SimulationEvent]:
    """A run whose one agent responds, is swapped to another model, and responds again."""
    return [
        _started(provider="anthropic"),
        _registered(model="claude-sonnet-4-6", provider="anthropic", seconds=1),
        _response(seconds=2),
        AgentSwappedMidRun(
            agent_id="field_observer",
            new_model="gpt-5.4-mini",
            new_provider="openai",
            channel_visibility={},
            round_number=2,
            timestamp=_at(seconds=3),
        ),
        _response(seconds=4),
    ]


def _write_log(log_path: Path, lines: list[dict[str, object]]) -> None:
    log_path.write_bytes(b"".join(orjson.dumps(line) + b"\n" for line in lines))


async def test_responses_after_a_swap_are_priced_at_the_swapped_in_model(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "veyru.jsonl"
    _write_log(
        log_path=log_path,
        lines=[event.model_dump(mode="json") for event in _swapped_run_events()],
    )

    scan = await scan_jsonl(file_path=log_path)

    before_swap = _cost(
        pricing=find_pricing(model="claude-sonnet-4-6", provider="anthropic", at=_at(seconds=1))
    )
    after_swap = _cost(
        pricing=find_pricing(model="gpt-5.4-mini", provider="openai", at=_at(seconds=3))
    )
    assert before_swap != pytest.approx(after_swap)
    assert scan.cost_usd == pytest.approx(before_swap + after_swap, rel=1e-12)


async def test_a_response_is_priced_at_the_rates_in_effect_when_it_was_logged(
    tmp_path: Path,
) -> None:
    """genai-prices bills deepseek-chat at one rate at 12:00 UTC and another at 20:00."""
    registered_at = 12 * 3600
    responded_at = 20 * 3600
    log_path = tmp_path / "veyru.jsonl"
    _write_log(
        log_path=log_path,
        lines=[
            event.model_dump(mode="json")
            for event in [
                _started(provider="deepseek"),
                _registered(model="deepseek-chat", provider="deepseek", seconds=registered_at),
                _response(seconds=responded_at),
            ]
        ],
    )

    scan = await scan_jsonl(file_path=log_path)

    at_registration = _cost(
        pricing=find_pricing(
            model="deepseek-chat", provider="deepseek", at=_at(seconds=registered_at)
        )
    )
    at_response = _cost(
        pricing=find_pricing(
            model="deepseek-chat", provider="deepseek", at=_at(seconds=responded_at)
        )
    )
    assert at_registration != pytest.approx(at_response)
    assert scan.cost_usd == pytest.approx(at_response, rel=1e-12)


async def test_a_response_without_usage_fails_the_scan_naming_its_line(tmp_path: Path) -> None:
    """A response the scan cannot price is refused rather than counted as costing nothing."""
    lines = [event.model_dump(mode="json") for event in _swapped_run_events()]
    del lines[2]["usage"]
    log_path = tmp_path / "veyru.jsonl"
    _write_log(log_path=log_path, lines=lines)

    with pytest.raises(
        ValueError, match=r"veyru\.jsonl line 3 is not a valid llm_response_received"
    ):
        await scan_jsonl(file_path=log_path)
