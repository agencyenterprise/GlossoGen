"""What the SDK adapter reads out of the messages the Claude Code CLI streams.

The shapes below are the ones a live session produced: each content block
arrives as its own ``AssistantMessage`` sharing the response's id, a response's
stop reason and final usage arrive only on the raw ``message_delta`` stream
event, and a tool result's content is a list of parts, or a bare string when the
tool reported an error.
"""

from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from glossogen.models.event_base import TokenUsage
from glossogen.run_export.archive_member_filter import should_include_in_archive
from glossogen.runners.claude_agent_sdk.claude_sdk_seat_session import SdkMessageTranslator
from glossogen.runners.harness_names import HARNESS_STATE_DIR_NAME
from glossogen.runners.session_harness.seat_session import (
    CompactionBoundary,
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    SessionStarted,
    TextChunk,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.runners.session_harness.session_transcripts import keep_session_transcripts

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
    projects = seat_dir / HARNESS_STATE_DIR_NAME / "claude_config" / "projects" / "workspace"
    projects.mkdir(parents=True)
    (projects / "session-1.jsonl").write_text('{"type": "user"}\n')
    (seat_dir / HARNESS_STATE_DIR_NAME / "claude_config" / ".claude.json").write_text("{}")

    keep_session_transcripts(
        seat_dir=seat_dir,
        source_dir=seat_dir / HARNESS_STATE_DIR_NAME / "claude_config" / "projects",
    )

    kept = seat_dir / "transcripts" / "session-1.jsonl"
    assert kept.read_text() == '{"type": "user"}\n'
    archived = [
        path.relative_to(run_dir).as_posix()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
        and should_include_in_archive(path=path, run_dir=run_dir, include_logs=True)
    ]
    assert archived == ["harness/field_observer/transcripts/session-1.jsonl"]


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
