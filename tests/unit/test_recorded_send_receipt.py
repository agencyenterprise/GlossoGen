"""Replaying recorded ``send_message`` results: old receipts, new receipts, tool errors.

Runs recorded before ``send_message`` returned a ``message_id`` hold results with
only ``status`` and the result's own fields. Channel-visibility filtering reads
each result to find the channel a call posted to; an old result reads as having
no id, and the call's channel comes from its ``channel_id`` argument. A rejected
call's result is plain text and is skipped.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart

from glossogen.models.channel_visibility import ChannelVisibility, ChannelVisibilityNone
from glossogen.models.event import (
    LLMResponseReceived,
    MessageSent,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.message import SimulationMessage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.runners.communication_protocol import platform_runner_prompts

_AGENT = "seat"
_START = datetime(2026, 8, 1, tzinfo=UTC)
_OLD_SHAPE_RESULT = (
    '{"status": "sent", "detail": "Message sent to channel \'postmortem\'", '
    '"new_messages": [], "token_count": 4, "current_round": 1}'
)


def _usage() -> TokenUsage:
    """A minimal token usage record."""
    return TokenUsage(
        input_tokens=1,
        output_tokens=1,
        reasoning_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def _send(call_id: str, arguments: dict[str, object], result: str) -> list[SimulationEvent]:
    """One round-1 LLM cycle holding one ``send_message`` call and its recorded result."""
    return [
        ToolCallInvoked(
            round_number=1,
            agent_id=_AGENT,
            call_id=call_id,
            tool_name="send_message",
            arguments=arguments,
        ),
        ToolResultReceived(
            round_number=1,
            agent_id=_AGENT,
            tool_name="send_message",
            call_id=call_id,
            arguments=arguments,
            result=result,
        ),
        LLMResponseReceived(
            round_number=1,
            agent_id=_AGENT,
            text="",
            tool_calls=[
                ToolCallRequest(call_id=call_id, tool_name="send_message", arguments=arguments)
            ],
            stop_reason=StopReason.TOOL_USE,
            usage=_usage(),
        ),
    ]


def _message_sent(message_id: str) -> MessageSent:
    """The ``message_sent`` event the runtime logs for a post to ``postmortem``."""
    return MessageSent(
        round_number=1,
        message=SimulationMessage(
            message_id=message_id,
            channel_id="postmortem",
            sender_agent_id=_AGENT,
            sender_display_name="Seat",
            text="sent",
            timestamp=_START,
            round_number=1,
        ),
        token_count=1,
    )


def _surviving_call_ids(body: list[SimulationEvent]) -> set[str]:
    """Replay ``body`` with ``postmortem`` hidden and collect the tool calls kept."""
    events: list[SimulationEvent] = [
        SimulationStarted(
            round_number=0,
            run_id="smoke/1",
            scenario_name="smoke",
            scenario_description="",
            channel_ids=["link", "postmortem"],
            scenario_config={"round_count": 3},
            provider="anthropic",
        ),
        *body,
    ]
    stamped: list[SimulationEvent] = []
    for index, event in enumerate(events):
        assert isinstance(event, EventBase)
        stamped.append(event.model_copy(update={"timestamp": _START + timedelta(seconds=index)}))
    visibility: dict[str, ChannelVisibility] = {"postmortem": ChannelVisibilityNone()}
    history = build_message_history(
        events=stamped,
        agent_id=_AGENT,
        system_prompt="do things",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=stamped[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=False,
        channel_visibility=visibility,
        history_floor_round=None,
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )
    call_ids: set[str] = set()
    for message in history:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                call_ids.add(part.tool_call_id)
    return call_ids


def test_a_result_recorded_without_a_message_id_replays_without_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An old-shape result is a receipt with no id; the call's argument names its channel."""
    body = _send(
        call_id="old-1",
        arguments={"channel_id": "postmortem", "text": "sent", "force": False},
        result=_OLD_SHAPE_RESULT,
    )

    with caplog.at_level(logging.DEBUG):
        call_ids = _surviving_call_ids(body=body)

    assert call_ids == set()
    assert [
        record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR
    ] == []


def test_a_send_without_a_channel_argument_takes_its_channel_from_the_receipt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A result carrying ``message_id`` joins to its ``message_sent`` event's channel."""
    body = [
        *_send(
            call_id="new-1",
            arguments={"recipients": ["other"], "text": "sent"},
            result='{"status": "sent", "message_id": "m-1"}',
        ),
        _message_sent(message_id="m-1"),
    ]

    with caplog.at_level(logging.DEBUG):
        call_ids = _surviving_call_ids(body=body)

    assert call_ids == set()
    assert [
        record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR
    ] == []


def test_a_tool_error_recorded_as_text_replays_without_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected call's plain-text result is skipped, not reported as a malformed receipt."""
    body = _send(
        call_id="err-1",
        arguments={"channel_id": "postmortem", "text": "sent"},
        result="Error executing tool send_message: Agent 'seat' is being swapped out",
    )

    with caplog.at_level(logging.DEBUG):
        call_ids = _surviving_call_ids(body=body)

    assert call_ids == set()
    assert [
        record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR
    ] == []
