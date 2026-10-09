"""Provider compaction payloads survive event logging and history reconstruction."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic_ai.messages import CompactionPart, ModelResponse, PartStartEvent, TextPart

from glossogen.evaluation.log_reader import load_events
from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.message_history_builder import build_message_history
from glossogen.models.event import (
    ContextCompacted,
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
)
from glossogen.models.event_base import TokenUsage
from glossogen.runners.communication_protocol import platform_runner_prompts
from glossogen.runners.pydantic_ai_runner import (
    _StreamingState,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.pydantic_ai_runner import (
    PydanticAIRunner,
)

_AGENT = "seat"
_DETAILS = {"encrypted_content": "encrypted-summary"}


def _stamp(events: list[SimulationEvent]) -> list[SimulationEvent]:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    return [
        event.model_copy(update={"timestamp": start + timedelta(seconds=index)})
        for index, event in enumerate(events)
    ]


def _events() -> list[SimulationEvent]:
    return _stamp(
        [
            SimulationStarted(
                round_number=0,
                run_id="smoke/1",
                scenario_name="smoke",
                scenario_description="",
                channel_ids=[],
                scenario_config={},
                provider="openai",
            ),
            ContextCompacted(
                round_number=1,
                agent_id=_AGENT,
                provider_name="openai",
                summary_char_count=0,
                summary_text="",
                part_id="cmp_1",
                provider_details=_DETAILS,
            ),
            LLMResponseReceived(
                round_number=1,
                agent_id=_AGENT,
                text="continued",
                tool_calls=[],
                stop_reason=StopReason.END_TURN,
                usage=TokenUsage(
                    input_tokens=1,
                    output_tokens=1,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                ),
            ),
        ]
    )


def _history(events: list[SimulationEvent], *, tool_calls_only: bool = False):
    return build_message_history(
        events=events,
        agent_id=_AGENT,
        system_prompt="system",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=tool_calls_only,
        channel_visibility={},
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )


def test_reconstructed_history_keeps_the_provider_compaction_payload() -> None:
    responses = [message for message in _history(_events()) if isinstance(message, ModelResponse)]
    assert responses[0].parts == [
        CompactionPart(
            content=None,
            id="cmp_1",
            provider_name="openai",
            provider_details=_DETAILS,
        ),
        TextPart(content="continued"),
    ]


def test_filtered_predecessor_history_does_not_leak_a_compaction_summary() -> None:
    history = _history(_events(), tool_calls_only=True)
    assert all(
        not isinstance(part, CompactionPart) for message in history for part in message.parts
    )


async def test_stream_logging_records_compaction_identifiers_and_details(tmp_path: Path) -> None:
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
    for event in [
        PartStartEvent(
            index=0,
            part=CompactionPart(
                id="cmp_1",
                provider_name="openai",
                provider_details=_DETAILS,
            ),
        ),
        PartStartEvent(index=1, part=TextPart(content="continued")),
    ]:
        runner._process_stream_event(  # pyright: ignore[reportPrivateUsage]
            agent_id=_AGENT,
            event=event,
            state=state,
            event_logger=event_logger,
            round_number=1,
        )
    await asyncio.gather(*state.background_tasks)
    await event_logger.close()

    [logged] = [
        event
        for event in await load_events(log_path=tmp_path / "smoke.jsonl")
        if isinstance(event, ContextCompacted)
    ]
    assert logged.part_id == "cmp_1"
    assert logged.provider_details == _DETAILS
