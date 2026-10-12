"""What the Codex adapter reads out of the app server's notifications.

The payloads are trimmed from a live session: a response's output items arrive
as raw items with no response id, ``rawResponse/completed`` closes the response
with its usage, and a client-defined tool's result is read off its completed
``dynamicToolCall`` item.
"""

from typing import Any

import pytest

from glossogen.models.event_base import TokenUsage
from glossogen.runners.codex_app_server.app_server_connection import ServerNotification
from glossogen.runners.codex_app_server.codex_item_translator import (
    CodexItemTranslator,
    CodexRawEventsMissing,
)
from glossogen.runners.session_harness.seat_session import (
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    TextChunk,
    ThinkingChunk,
    ToolResultChunk,
    ToolUseChunk,
)

THREAD_ID = "01a12248-482e-79a3-bfc0-e319953a7dbe"
TURN_ID = "01a12248-488a-74b3-a75d-79bcfbcfeb8e"
USAGE = {
    "totalTokens": 220,
    "inputTokens": 172,
    "cachedInputTokens": 64,
    "cacheWriteInputTokens": 0,
    "outputTokens": 48,
    "reasoningOutputTokens": 12,
}


def raw_item(item: dict[str, Any], turn_id: str) -> ServerNotification:
    return ServerNotification(
        method="rawResponseItem/completed",
        params={"threadId": THREAD_ID, "turnId": turn_id, "item": item},
    )


def response_completed(turn_id: str) -> ServerNotification:
    return ServerNotification(
        method="rawResponse/completed",
        params={"threadId": THREAD_ID, "turnId": turn_id, "responseId": "resp_1", "usage": USAGE},
    )


def function_call(name: str, call_id: str, arguments: str) -> dict[str, Any]:
    return {"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}


def test_a_parallel_response_is_one_response_with_both_calls_and_its_usage() -> None:
    translator = CodexItemTranslator()
    items = [
        *translator.translate(
            notification=raw_item(
                item=function_call(name="long_wait", call_id="call_a", arguments='{"seconds":5}'),
                turn_id=TURN_ID,
            )
        ),
        *translator.translate(
            notification=raw_item(
                item=function_call(name="echo_state", call_id="call_b", arguments='{"note":"b"}'),
                turn_id=TURN_ID,
            )
        ),
        *translator.translate(notification=response_completed(turn_id=TURN_ID)),
    ]

    message_id = f"{TURN_ID}-response-1"
    assert items == [
        ResponseStarted(message_id=message_id),
        ToolUseChunk(
            message_id=message_id,
            call_id="call_a",
            tool_name="long_wait",
            arguments={"seconds": 5},
            answered_by_cli=False,
        ),
        ToolUseChunk(
            message_id=message_id,
            call_id="call_b",
            tool_name="echo_state",
            arguments={"note": "b"},
            answered_by_cli=False,
        ),
        ResponseCompleted(
            message_id=message_id,
            stop_reason="tool_use",
            usage=TokenUsage(
                input_tokens=172,
                output_tokens=48,
                cache_read_input_tokens=64,
                cache_creation_input_tokens=0,
            ),
        ),
    ]


def test_the_next_response_opens_after_the_previous_one_closed() -> None:
    translator = CodexItemTranslator()
    translator.translate(
        notification=raw_item(
            item=function_call(name="refuse", call_id="call_r", arguments="{}"), turn_id=TURN_ID
        )
    )
    translator.translate(notification=response_completed(turn_id=TURN_ID))

    items = translator.translate(
        notification=raw_item(
            item={
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "DONE"}],
            },
            turn_id=TURN_ID,
        )
    )
    closed = translator.translate(notification=response_completed(turn_id=TURN_ID))

    message_id = f"{TURN_ID}-response-2"
    assert items == [
        ResponseStarted(message_id=message_id),
        TextChunk(message_id=message_id, text="DONE"),
    ]
    assert [type(item) for item in closed] == [ResponseCompleted]
    assert isinstance(closed[0], ResponseCompleted)
    assert closed[0].stop_reason == "end_turn"


def test_a_reasoning_summary_is_kept_as_thinking() -> None:
    translator = CodexItemTranslator()
    items = translator.translate(
        notification=raw_item(
            item={
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Compare the faces first."}],
            },
            turn_id=TURN_ID,
        )
    )

    message_id = f"{TURN_ID}-response-1"
    assert items == [
        ResponseStarted(message_id=message_id),
        ThinkingChunk(
            message_id=message_id,
            thinking="Compare the faces first.",
            signature=None,
            provider_name="openai",
        ),
    ]


def test_the_users_own_message_and_call_outputs_are_not_responses() -> None:
    translator = CodexItemTranslator()
    user = raw_item(
        item={"type": "message", "role": "user", "content": [{"type": "input_text", "text": "x"}]},
        turn_id=TURN_ID,
    )
    output = raw_item(
        item={"type": "function_call_output", "call_id": "call_a", "output": "waited"},
        turn_id=TURN_ID,
    )

    assert translator.translate(notification=user) == []
    assert translator.translate(notification=output) == []


def test_a_failed_tool_calls_result_is_read_and_other_items_are_not() -> None:
    translator = CodexItemTranslator()
    failed = ServerNotification(
        method="item/completed",
        params={
            "threadId": THREAD_ID,
            "turnId": TURN_ID,
            "item": {
                "type": "dynamicToolCall",
                "id": "call_r",
                "tool": "refuse",
                "status": "failed",
                "contentItems": [{"type": "inputText", "text": "you may not do that"}],
                "success": False,
            },
        },
    )
    agent_message = ServerNotification(
        method="item/completed",
        params={"item": {"type": "agentMessage", "id": "msg_1", "text": "DONE"}},
    )

    assert translator.translate(notification=failed) == [
        ToolResultChunk(call_id="call_r", content="you may not do that")
    ]
    assert translator.translate(notification=agent_message) == []


def turn_completed(status: str, error: dict[str, str] | None) -> ServerNotification:
    return ServerNotification(
        method="turn/completed",
        params={
            "threadId": THREAD_ID,
            "turn": {"id": TURN_ID, "status": status, "error": error},
        },
    )


def test_a_turn_ends_the_cycle_and_a_failed_one_says_why() -> None:
    translator = CodexItemTranslator()
    translator.translate(
        notification=raw_item(
            item={
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            },
            turn_id=TURN_ID,
        )
    )
    translator.translate(notification=response_completed(turn_id=TURN_ID))

    assert translator.translate(notification=turn_completed(status="completed", error=None)) == [
        CycleEnded(session_id=THREAD_ID, is_error=False, error_text="", reported_cost_usd=None)
    ]
    assert translator.translate(
        notification=turn_completed(status="failed", error={"message": "rate limited"})
    ) == [
        CycleEnded(
            session_id=THREAD_ID, is_error=True, error_text="rate limited", reported_cost_usd=None
        )
    ]


def test_a_turn_that_completes_without_a_raw_response_is_refused() -> None:
    """A server that ignores ``experimentalRawEvents`` would otherwise run the seat unlogged."""
    translator = CodexItemTranslator()

    with pytest.raises(CodexRawEventsMissing, match="without a raw response event"):
        translator.translate(notification=turn_completed(status="completed", error=None))


def test_a_turn_interrupted_or_failed_before_any_response_still_ends_the_cycle() -> None:
    translator = CodexItemTranslator()

    ended = translator.translate(notification=turn_completed(status="interrupted", error=None))

    assert ended == [
        CycleEnded(
            session_id=THREAD_ID, is_error=True, error_text="interrupted", reported_cost_usd=None
        )
    ]


def test_responses_are_numbered_afresh_in_each_turn() -> None:
    translator = CodexItemTranslator()
    translator.translate(
        notification=raw_item(
            item=function_call(name="refuse", call_id="call_1", arguments="{}"), turn_id="turn-1"
        )
    )
    translator.translate(notification=response_completed(turn_id="turn-1"))

    items = translator.translate(
        notification=raw_item(
            item=function_call(name="refuse", call_id="call_2", arguments="{}"), turn_id="turn-2"
        )
    )

    assert items[0] == ResponseStarted(message_id="turn-2-response-1")


def test_a_response_with_no_usage_or_cache_writes_is_read_as_the_schema_allows() -> None:
    """``usage`` may be null, ``cacheWriteInputTokens`` absent, a reasoning item's content null."""
    translator = CodexItemTranslator()
    reasoning = translator.translate(
        notification=raw_item(
            item={"type": "reasoning", "summary": [], "content": None}, turn_id=TURN_ID
        )
    )
    no_usage = translator.translate(
        notification=ServerNotification(
            method="rawResponse/completed",
            params={"threadId": THREAD_ID, "turnId": TURN_ID, "responseId": "r", "usage": None},
        )
    )
    translator.translate(
        notification=raw_item(
            item=function_call(name="refuse", call_id="call_r", arguments="{}"), turn_id=TURN_ID
        )
    )
    usage_without_cache_writes = {
        key: value for key, value in USAGE.items() if key != "cacheWriteInputTokens"
    }
    no_cache_writes = translator.translate(
        notification=ServerNotification(
            method="rawResponse/completed",
            params={
                "threadId": THREAD_ID,
                "turnId": TURN_ID,
                "responseId": "r2",
                "usage": usage_without_cache_writes,
            },
        )
    )

    assert reasoning == [ResponseStarted(message_id=f"{TURN_ID}-response-1")]
    assert no_usage == [
        ResponseCompleted(
            message_id=f"{TURN_ID}-response-1",
            stop_reason="end_turn",
            usage=TokenUsage(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )
    ]
    assert [item.usage for item in no_cache_writes if isinstance(item, ResponseCompleted)] == [
        TokenUsage(
            input_tokens=172,
            output_tokens=48,
            cache_read_input_tokens=64,
            cache_creation_input_tokens=0,
        )
    ]


def test_arguments_that_are_json_but_not_an_object_are_kept_raw_for_codex_to_answer() -> None:
    translator = CodexItemTranslator()

    items = translator.translate(
        notification=raw_item(
            item=function_call(name="send_message", call_id="call_1", arguments="[1, 2]"),
            turn_id=TURN_ID,
        )
    )

    assert items[1] == ToolUseChunk(
        message_id=f"{TURN_ID}-response-1",
        call_id="call_1",
        tool_name="send_message",
        arguments={"unparsed_arguments": "[1, 2]"},
        answered_by_cli=True,
    )


def test_a_function_call_without_a_call_id_or_a_name_is_refused() -> None:
    translator = CodexItemTranslator()

    with pytest.raises(ValueError, match="no call_id"):
        translator.translate(
            notification=raw_item(
                item={"type": "function_call", "name": "send_message", "arguments": "{}"},
                turn_id=TURN_ID,
            )
        )
    with pytest.raises(ValueError, match="no name"):
        translator.translate(
            notification=raw_item(
                item={"type": "function_call", "call_id": "call_1", "arguments": "{}"},
                turn_id=TURN_ID,
            )
        )


def test_a_call_output_codex_wrote_as_parts_reads_as_their_text() -> None:
    translator = CodexItemTranslator()
    translator.translate(
        notification=raw_item(
            item=function_call(name="send_message", call_id="call_1", arguments="{not json"),
            turn_id=TURN_ID,
        )
    )

    items = translator.translate(
        notification=raw_item(
            item={
                "type": "function_call_output",
                "call_id": "call_1",
                "output": [
                    {"type": "input_text", "text": "failed to "},
                    {"type": "input_text", "text": "parse"},
                ],
            },
            turn_id=TURN_ID,
        )
    )

    assert items == [ToolResultChunk(call_id="call_1", content="failed to parse")]


def test_an_error_with_no_response_open_abandons_nothing() -> None:
    translator = CodexItemTranslator()

    items = translator.translate(
        notification=ServerNotification(
            method="error",
            params={"threadId": THREAD_ID, "turnId": TURN_ID, "willRetry": True},
        )
    )

    assert items == []
