"""History cleanup reads the tool returns it rewrites as the models that produced them.

A return that does not validate is left as it is, so a renamed field costs the
cleanup on that return rather than deduplicating on a key full of defaults.
"""

import json

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from glossogen.models.mcp_responses import ChannelMessage, ReadChannelResult
from glossogen.runners.history_cleanup_processor import clean_history
from glossogen.runtime.activity_notification import NewInfoNotification, NoActivityNotification
from glossogen.runtime.communication_tools import READ_CHANNEL_TOOL_NAME
from glossogen.runtime.notification_payload import (
    DELIVERED_NOTIFICATION_ADAPTER,
    DeliveredNoActivity,
    delivered_notification,
)
from glossogen.runtime.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME


def call(tool_name: str, call_id: str, channel_id: str | None = None) -> ModelResponse:
    args = {} if channel_id is None else {"channel_id": channel_id, "last_n": 100}
    return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=call_id)])


def answer(tool_name: str, call_id: str, content: str) -> ModelRequest:
    return ModelRequest(
        parts=[ToolReturnPart(tool_name=tool_name, content=content, tool_call_id=call_id)]
    )


def poll_result(notification: NoActivityNotification | NewInfoNotification) -> str:
    return json.dumps(
        delivered_notification(
            notification=notification, pending_count=0, current_round=1
        ).model_dump(mode="json")
    )


def channel_read(texts: list[str]) -> str:
    return json.dumps(
        ReadChannelResult(
            current_round=1,
            messages=[
                ChannelMessage(round=1, sender="a", text=text, elapsed_seconds=1.0)
                for text in texts
            ],
        ).model_dump()
    )


FINAL: list[ModelMessage] = [ModelResponse(parts=[TextPart(content="done")])]


def test_an_empty_poll_is_dropped() -> None:
    history: list[ModelMessage] = [
        call(tool_name=READ_NOTIFICATIONS_TOOL_NAME, call_id="c1"),
        answer(
            tool_name=READ_NOTIFICATIONS_TOOL_NAME,
            call_id="c1",
            content=poll_result(notification=NoActivityNotification(detail="No new messages.")),
        ),
        *FINAL,
    ]

    assert clean_history(messages=history) == FINAL


def test_an_empty_poll_response_with_text_is_kept() -> None:
    response = ModelResponse(
        parts=[
            TextPart(content="I will wait."),
            ToolCallPart(
                tool_name=READ_NOTIFICATIONS_TOOL_NAME,
                args={},
                tool_call_id="c1",
            ),
        ]
    )
    history: list[ModelMessage] = [
        response,
        answer(
            tool_name=READ_NOTIFICATIONS_TOOL_NAME,
            call_id="c1",
            content=poll_result(notification=NoActivityNotification(detail="No new messages.")),
        ),
        *FINAL,
    ]

    assert clean_history(messages=history) == history


def test_a_poll_that_delivered_something_is_kept() -> None:
    history: list[ModelMessage] = [
        call(tool_name=READ_NOTIFICATIONS_TOOL_NAME, call_id="c1"),
        answer(
            tool_name=READ_NOTIFICATIONS_TOOL_NAME,
            call_id="c1",
            content=poll_result(notification=NewInfoNotification(text="brief", kind="injection")),
        ),
        *FINAL,
    ]

    assert clean_history(messages=history) == history


def test_a_scenario_rendering_is_never_mistaken_for_an_empty_poll() -> None:
    """A scenario's own wake carries no ``pending_count``, so it is not a platform poll."""
    history: list[ModelMessage] = [
        call(tool_name=READ_NOTIFICATIONS_TOOL_NAME, call_id="c1"),
        answer(
            tool_name=READ_NOTIFICATIONS_TOOL_NAME,
            call_id="c1",
            content=json.dumps({"type": "no_activity", "workspace": "depot"}),
        ),
        *FINAL,
    ]

    assert clean_history(messages=history) == history


def test_a_message_already_read_is_dropped_from_the_later_read() -> None:
    history: list[ModelMessage] = [
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", channel_id="link"),
        answer(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", content=channel_read(["one"])),
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", channel_id="link"),
        answer(
            tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", content=channel_read(["one", "two"])
        ),
        *FINAL,
    ]

    cleaned = clean_history(messages=history)

    second = cleaned[3]
    assert isinstance(second, ModelRequest)
    part = second.parts[0]
    assert isinstance(part, ToolReturnPart)
    assert part.content == channel_read(["two"])


def test_identical_messages_on_different_channels_are_not_deduplicated() -> None:
    history: list[ModelMessage] = [
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", channel_id="alpha"),
        answer(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", content=channel_read(["same"])),
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", channel_id="beta"),
        answer(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", content=channel_read(["same"])),
        *FINAL,
    ]

    assert clean_history(messages=history) == history


def test_repeated_identical_messages_on_one_channel_keep_their_multiplicity() -> None:
    history: list[ModelMessage] = [
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", channel_id="link"),
        answer(
            tool_name=READ_CHANNEL_TOOL_NAME,
            call_id="r1",
            content=channel_read(["same", "same"]),
        ),
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", channel_id="link"),
        answer(
            tool_name=READ_CHANNEL_TOOL_NAME,
            call_id="r2",
            content=channel_read(["same", "same", "same"]),
        ),
        *FINAL,
    ]

    cleaned = clean_history(messages=history)
    first = cleaned[1]
    second = cleaned[3]
    assert isinstance(first, ModelRequest)
    assert isinstance(second, ModelRequest)
    first_return = first.parts[0]
    second_return = second.parts[0]
    assert isinstance(first_return, ToolReturnPart)
    assert isinstance(second_return, ToolReturnPart)
    assert first_return.content == channel_read(["same", "same"])
    assert second_return.content == channel_read(["same"])


def test_a_read_whose_messages_do_not_validate_is_left_alone() -> None:
    renamed = json.dumps(
        {"current_round": 1, "messages": [{"round_number": 1, "sender": "a", "text": "one"}]}
    )
    history: list[ModelMessage] = [
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", channel_id="link"),
        answer(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r1", content=renamed),
        call(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", channel_id="link"),
        answer(tool_name=READ_CHANNEL_TOOL_NAME, call_id="r2", content=renamed),
        *FINAL,
    ]

    assert clean_history(messages=history) == history


def test_the_delivered_payload_keeps_its_wire_form() -> None:
    """Agents and recorded runs read these exact bytes."""
    rendered = poll_result(notification=NoActivityNotification(detail="No new messages."))

    assert rendered == (
        '{"type": "no_activity", "detail": "No new messages.", '
        '"pending_count": 0, "current_round": 1}'
    )
    assert isinstance(DELIVERED_NOTIFICATION_ADAPTER.validate_json(rendered), DeliveredNoActivity)
