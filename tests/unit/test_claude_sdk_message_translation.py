"""What the SDK adapter reads out of the messages the Claude Code CLI streams.

The shapes below are the ones a live session produced: each content block
arrives as its own ``AssistantMessage`` sharing the response's id, the adapter
reads a response's stop reason and final usage from the raw ``message_delta``
stream event, and a tool result's content is a list of parts, or a bare string
when the tool reported an error.
"""

from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ContentBlock,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from glossogen.models.event_base import TokenUsage  # noqa: E402
from glossogen.run_export.archive_member_filter import should_include_in_archive  # noqa: E402
from glossogen.runners.claude_agent_sdk.claude_sdk_seat_session import (  # noqa: E402
    SdkMessageTranslator,
)
from glossogen.runners.harness_names import HARNESS_STATE_DIR_NAME  # noqa: E402
from glossogen.runners.session_harness.seat_session import (  # noqa: E402
    CompactionBoundary,
    CycleEnded,
    ResponseAbandoned,
    ResponseCompleted,
    ResponseStarted,
    SessionStarted,
    TextChunk,
    ThinkingChunk,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.runners.session_harness.session_transcripts import (  # noqa: E402
    keep_session_transcripts,
)

MESSAGE_ID = "msg_011Cfs6BC2SvV7t3ZH3xDWU8"
MODEL = "claude-haiku-4-5-20251001"


def stream_event(event: dict[str, object]) -> StreamEvent:
    """A raw API stream event as the SDK wraps it."""
    return StreamEvent(uuid="u", session_id="s", event=event)


def test_a_response_opens_on_message_start_and_closes_with_its_final_usage() -> None:
    """Anthropic counts only uncached input in ``input_tokens``; the log counts all of it."""
    translator = SdkMessageTranslator()
    opened = translator.translate(
        message=stream_event(event={"type": "message_start", "message": {"id": MESSAGE_ID}})
    )
    closed = translator.translate(
        message=stream_event(
            event={
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 59,
                    "cache_read_input_tokens": 20_000,
                    "cache_creation_input_tokens": 500,
                },
            }
        )
    )

    assert opened == [ResponseStarted(message_id=MESSAGE_ID)]
    assert closed == [
        ResponseCompleted(
            message_id=MESSAGE_ID,
            stop_reason="tool_use",
            usage=TokenUsage(
                input_tokens=20_503,
                output_tokens=59,
                cache_read_input_tokens=20_000,
                cache_creation_input_tokens=500,
            ),
        )
    ]


def test_a_tool_call_is_reported_under_the_seat_tools_own_name() -> None:
    """The CLI prefixes served tools with their server; the log records the tool's name."""
    translator = SdkMessageTranslator()
    items = translator.translate(
        message=AssistantMessage(
            content=[
                TextBlock(text="Now calling it:"),
                ToolUseBlock(
                    id="toolu_1",
                    name="mcp__glossogen__send_message",
                    input={"channel_id": "link", "text": "hi"},
                ),
            ],
            model=MODEL,
            message_id=MESSAGE_ID,
        )
    )

    assert items == [
        TextChunk(message_id=MESSAGE_ID, text="Now calling it:"),
        ToolUseChunk(
            message_id=MESSAGE_ID,
            call_id="toolu_1",
            tool_name="send_message",
            arguments={"channel_id": "link", "text": "hi"},
            answered_by_cli=False,
        ),
    ]


def test_tool_results_read_as_text_whether_sent_as_parts_or_as_an_error_string() -> None:
    translator = SdkMessageTranslator()
    items = translator.translate(
        message=UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="toolu_1",
                    content=[{"type": "text", "text": "echoed a"}],
                    is_error=None,
                ),
                ToolResultBlock(tool_use_id="toolu_2", content="refused", is_error=True),
            ]
        )
    )

    assert items == [
        ToolResultChunk(call_id="toolu_1", content="echoed a"),
        ToolResultChunk(call_id="toolu_2", content="refused"),
    ]


def test_a_failed_turn_carries_the_clis_explanation() -> None:
    translator = SdkMessageTranslator()
    items = translator.translate(
        message=ResultMessage(
            subtype="error_during_execution",
            duration_ms=10,
            duration_api_ms=5,
            is_error=True,
            num_turns=1,
            session_id="session-1",
            total_cost_usd=0.01,
            errors=["API Error: overloaded"],
        )
    )

    assert items == [
        CycleEnded(
            session_id="session-1",
            is_error=True,
            error_text="API Error: overloaded",
            reported_cost_usd=0.01,
        )
    ]


def test_a_compaction_is_reported_and_other_system_messages_are_not() -> None:
    translator = SdkMessageTranslator()
    details: dict[str, object] = {"subtype": "compact_boundary", "pre_tokens": 160_000}

    assert translator.translate(
        message=SystemMessage(subtype="compact_boundary", data=details)
    ) == [CompactionBoundary(details=details)]
    assert translator.translate(message=SystemMessage(subtype="status", data={})) == []


def test_the_session_is_known_from_the_clis_first_message() -> None:
    """A crash before the turn ends can then resume the session rather than start over."""
    translator = SdkMessageTranslator()
    assert translator.translate(
        message=SystemMessage(subtype="init", data={"session_id": "session-1"})
    ) == [SessionStarted(session_id="session-1")]


def test_a_closed_session_keeps_its_transcript_and_archives_leave_the_cli_state_out(
    tmp_path: Path,
) -> None:
    """The transcript is the seat's record; the rest of the CLI's directory is machine state."""
    run_dir = tmp_path / "run"
    seat_dir = run_dir / "harness" / "field_observer"
    projects = seat_dir / HARNESS_STATE_DIR_NAME / "claude_config" / "projects"
    (projects / "workspace").mkdir(parents=True)
    (projects / "workspace" / "session-1.jsonl").write_text('{"type": "user"}\n')
    (projects / "other").mkdir()
    (projects / "other" / "session-1.jsonl").write_text('{"type": "other"}\n')
    (seat_dir / HARNESS_STATE_DIR_NAME / "claude_config" / ".claude.json").write_text("{}")

    keep_session_transcripts(seat_dir=seat_dir, source_dir=projects)

    kept = seat_dir / "transcripts" / "workspace" / "session-1.jsonl"
    assert kept.read_text() == '{"type": "user"}\n'
    archived = [
        path.relative_to(run_dir).as_posix()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
        and should_include_in_archive(path=path, run_dir=run_dir, include_logs=True)
    ]
    assert archived == [
        "harness/field_observer/transcripts/other/session-1.jsonl",
        "harness/field_observer/transcripts/workspace/session-1.jsonl",
    ]


def test_a_request_the_cli_reports_as_failed_is_not_the_models_output() -> None:
    """The CLI writes the API's error text into an assistant message marked with ``error``."""
    translator = SdkMessageTranslator()

    items = translator.translate(
        message=AssistantMessage(
            content=[
                TextBlock(text="API Error: Claude's response exceeded the output token maximum")
            ],
            model=MODEL,
            error="invalid_request",
            message_id=MESSAGE_ID,
        )
    )

    assert items == []


def test_a_failed_request_abandons_the_response_it_had_opened() -> None:
    translator = SdkMessageTranslator()
    translator.translate(
        message=stream_event(event={"type": "message_start", "message": {"id": MESSAGE_ID}})
    )

    items = translator.translate(
        message=AssistantMessage(
            content=[TextBlock(text="API Error: overloaded")],
            model=MODEL,
            error="rate_limit",
            message_id=MESSAGE_ID,
        )
    )

    assert items == [ResponseAbandoned(message_id=MESSAGE_ID)]
    assert (
        translator.translate(message=AssistantMessage(content=[], model=MODEL, error="rate_limit"))
        == []
    ), "nothing is open to abandon twice"


def test_a_thinking_block_is_kept_with_its_signature_and_other_blocks_are_dropped() -> None:
    translator = SdkMessageTranslator()
    blocks: list[ContentBlock] = [
        ThinkingBlock(thinking="Consider the link.", signature="sig"),
        TextBlock(text="ok"),
        ToolResultBlock(tool_use_id="not-an-assistant-block", content="x"),
    ]

    items = translator.translate(
        message=AssistantMessage(content=blocks, model=MODEL, message_id=MESSAGE_ID)
    )

    assert items == [
        ThinkingChunk(
            message_id=MESSAGE_ID,
            thinking="Consider the link.",
            signature="sig",
            provider_name="anthropic",
        ),
        TextChunk(message_id=MESSAGE_ID, text="ok"),
    ]


def test_a_block_without_a_message_id_belongs_to_the_open_response() -> None:
    translator = SdkMessageTranslator()
    translator.translate(
        message=stream_event(event={"type": "message_start", "message": {"id": MESSAGE_ID}})
    )

    items = translator.translate(
        message=AssistantMessage(content=[TextBlock(text="ok")], model=MODEL)
    )

    assert items == [TextChunk(message_id=MESSAGE_ID, text="ok")]


def test_a_delta_without_a_stop_reason_closes_the_response_with_none_named() -> None:
    translator = SdkMessageTranslator()
    translator.translate(
        message=stream_event(event={"type": "message_start", "message": {"id": MESSAGE_ID}})
    )

    items = translator.translate(
        message=stream_event(event={"type": "message_delta", "delta": {}, "usage": {}})
    )

    assert items == [
        ResponseCompleted(
            message_id=MESSAGE_ID,
            stop_reason="",
            usage=TokenUsage(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )
    ]


def test_a_tool_result_with_no_content_or_an_unexpected_shape_still_reads_as_text() -> None:
    translator = SdkMessageTranslator()

    items = translator.translate(
        message=UserMessage(
            content=[
                ToolResultBlock(tool_use_id="toolu_1", content=None),
                ToolResultBlock(tool_use_id="toolu_2", content=cast(Any, {"unexpected": 1})),
            ]
        )
    )

    assert items == [
        ToolResultChunk(call_id="toolu_1", content=""),
        ToolResultChunk(call_id="toolu_2", content="{'unexpected': 1}"),
    ]
    assert translator.translate(message=UserMessage(content="a plain user turn")) == []


def test_a_failed_turn_without_an_error_list_explains_itself_from_its_result_or_subtype() -> None:
    def failed(result: str | None, subtype: str) -> ResultMessage:
        return ResultMessage(
            subtype=subtype,
            duration_ms=10,
            duration_api_ms=5,
            is_error=True,
            num_turns=1,
            session_id="session-1",
            result=result,
        )

    translator = SdkMessageTranslator()

    assert translator.translate(message=failed(result="went wrong", subtype="error")) == [
        CycleEnded(
            session_id="session-1", is_error=True, error_text="went wrong", reported_cost_usd=None
        )
    ]
    assert translator.translate(message=failed(result=None, subtype="error_max_turns")) == [
        CycleEnded(
            session_id="session-1",
            is_error=True,
            error_text="error_max_turns",
            reported_cost_usd=None,
        )
    ]
