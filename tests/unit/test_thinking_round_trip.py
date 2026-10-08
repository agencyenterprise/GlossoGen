"""A reconstructed history sends thinking back in the form the live run sent it.

A live run returns each thinking part to its provider with the identifiers the
provider issued: OpenAI's reasoning item id and encrypted content, Anthropic's
block signature. The runner records those per part, and the history builder
rebuilds the parts from the record. Thinking a run recorded as text alone has
no identifiers and is left out, since pydantic-ai would otherwise send it as a
tagged assistant message, which no live request carried.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic_ai.messages import (
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    ThinkingPart,
    ThinkingPartDelta,
)

from glossogen.evaluation.log_reader import load_events
from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.message_history_builder import build_message_history
from glossogen.models.event import (
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.thinking_part_record import ThinkingPartRecord
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.runners.communication_protocol import platform_runner_prompts
from glossogen.runners.pydantic_ai_runner import (
    _StreamingState,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.pydantic_ai_runner import (
    PydanticAIRunner,
)

_AGENT = "seat"
_NATIVE = ThinkingPartRecord(
    content="plan the reply",
    id="rs_1",
    signature="encrypted-reasoning",
    provider_name="openai",
)


def _usage() -> TokenUsage:
    """A minimal token usage record."""
    return TokenUsage(
        input_tokens=1,
        output_tokens=1,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def _stamped(events: list[SimulationEvent]) -> list[SimulationEvent]:
    """Give each event a distinct increasing timestamp, in list order."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
    stamped: list[SimulationEvent] = []
    for index, event in enumerate(events):
        assert isinstance(event, EventBase)
        stamped.append(event.model_copy(update={"timestamp": start + timedelta(seconds=index)}))
    return stamped


def _run_with_one_turn(
    thinking: str | None, thinking_parts: list[ThinkingPartRecord]
) -> list[SimulationEvent]:
    """A run whose one agent turn carried the given thinking and one link send."""
    call = ToolCallRequest(
        call_id="c-1", tool_name="send_message", arguments={"channel_id": "link", "text": "hi"}
    )
    return _stamped(
        events=[
            SimulationStarted(
                round_number=0,
                run_id="smoke/1",
                scenario_name="smoke",
                scenario_description="",
                channel_ids=["link"],
                scenario_config={"round_count": 1},
                provider="openai",
            ),
            ToolCallInvoked(
                round_number=1,
                agent_id=_AGENT,
                call_id=call.call_id,
                tool_name=call.tool_name,
                arguments=call.arguments,
            ),
            ToolResultReceived(
                round_number=1,
                agent_id=_AGENT,
                tool_name=call.tool_name,
                call_id=call.call_id,
                arguments=call.arguments,
                result="ok",
            ),
            LLMResponseReceived(
                round_number=1,
                agent_id=_AGENT,
                thinking=thinking,
                thinking_parts=thinking_parts,
                text="said",
                tool_calls=[call],
                stop_reason="tool_use",
                usage=_usage(),
            ),
        ]
    )


def _thinking_parts_in_history(events: list[SimulationEvent]) -> list[ThinkingPart]:
    """Every ``ThinkingPart`` the seat's reconstructed history holds."""
    history = build_message_history(
        events=events,
        agent_id=_AGENT,
        system_prompt="do things",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=False,
        channel_visibility={},
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )
    return [
        part
        for message in history
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ThinkingPart)
    ]


def test_recorded_parts_are_rebuilt_with_their_provider_identifiers() -> None:
    events = _run_with_one_turn(thinking=_NATIVE.content, thinking_parts=[_NATIVE])
    assert _thinking_parts_in_history(events=events) == [
        ThinkingPart(
            content=_NATIVE.content,
            id=_NATIVE.id,
            signature=_NATIVE.signature,
            provider_name=_NATIVE.provider_name,
        )
    ]


def test_thinking_recorded_as_text_alone_is_left_out() -> None:
    events = _run_with_one_turn(thinking="plan the reply", thinking_parts=[])
    assert _thinking_parts_in_history(events=events) == []


async def test_stream_records_each_part_with_the_identifiers_it_receives(tmp_path: Path) -> None:
    """OpenAI opens the part with its id, streams the summary, then sends the encrypted content."""
    runner = PydanticAIRunner(
        max_turns=1,
        event_bus=EventBus(max_queue_size=8),
        run_id="smoke/1",
        scenario_name="smoke",
        telemetry_enabled=False,
    )
    event_logger = EventLogger(
        log_path=tmp_path / "smoke.jsonl", event_bus=EventBus(max_queue_size=8)
    )
    await event_logger.open()
    state = _StreamingState()
    stream = [
        PartStartEvent(index=0, part=ThinkingPart(content="", id="rs_1", provider_name="openai")),
        PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta="plan ")),
        PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta="the reply")),
        PartDeltaEvent(
            index=0,
            delta=ThinkingPartDelta(signature_delta="encrypted-reasoning", provider_name="openai"),
        ),
    ]
    for event in stream:
        runner._process_stream_event(  # pyright: ignore[reportPrivateUsage]
            agent_id=_AGENT,
            event=event,
            state=state,
            event_logger=event_logger,
            round_number=1,
        )
    runner._flush_response_block(  # pyright: ignore[reportPrivateUsage]
        agent_id=_AGENT,
        state=state,
        event_logger=event_logger,
        stop_reason="end_turn",
        round_number=1,
        usage=None,
    )
    await asyncio.gather(*state.background_tasks)
    await event_logger.close()

    [logged] = [
        event
        for event in await load_events(log_path=tmp_path / "smoke.jsonl")
        if isinstance(event, LLMResponseReceived)
    ]
    assert logged.thinking == "plan the reply"
    assert logged.thinking_parts == [_NATIVE]
    assert state.accumulated_thinking == []


def test_a_failed_attempts_parts_are_discarded_and_a_delta_extends_the_newest_part() -> None:
    state = _StreamingState()
    state.start_thinking_part(
        part_index=0, part=ThinkingPart(content="kept", id="rs_1", provider_name="openai")
    )
    state.mark_attempt_start()
    state.start_thinking_part(
        part_index=0, part=ThinkingPart(content="retried", id="rs_2", provider_name="openai")
    )
    state.apply_thinking_delta(part_index=0, delta=ThinkingPartDelta(content_delta=" away"))
    assert [record.content for record in state.thinking_records()] == ["kept", "retried away"]

    state.discard_since_attempt_start()
    assert [record.content for record in state.thinking_records()] == ["kept"]
