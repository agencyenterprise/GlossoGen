"""`render_run_transcript`: which events a transcript keeps, drops and how it prints them."""

from datetime import UTC, datetime

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.canvas import CanvasDrawing, CanvasPixel
from glossogen.models.event import (
    AgentRegistered,
    AgentResumed,
    InjectionDelivered,
    LLMResponseReceived,
    MessageSent,
    RoundAdvanced,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
    UnrecognizedEvent,
    WaitRegistered,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.glossogen_build import GlossogenBuild
from glossogen.models.message import SimulationMessage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.models.wait_for import WaitFor
from glossogen.run_export.run_transcript import render_run_transcript, section_heading


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=10,
        output_tokens=5,
        reasoning_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def _setup_events(build: GlossogenBuild | None) -> list[SimulationEvent]:
    return [
        SimulationStarted(
            round_number=0,
            run_id="veyru/1700000000",
            scenario_name="veyru",
            scenario_description="Two agents stabilize a creature.",
            channel_ids=["link"],
            scenario_config={"round_count": 3},
            provider="anthropic",
            glossogen_build=build,
        ),
        AgentRegistered(
            round_number=0,
            agent_id="observer",
            role_name="Field Observer",
            system_prompt="You watch the creature.",
            channel_ids=["link"],
            tool_names=["send_message"],
            model="claude-haiku-4-5",
            provider="anthropic",
            model_settings=AgentModelSettings(max_tokens=1024),
        ),
    ]


def _round_one_events() -> list[SimulationEvent]:
    send_call = ToolCallRequest(
        call_id="call-1", tool_name="send_message", arguments={"text": "T bright"}
    )
    return [
        InjectionDelivered(round_number=1, agent_id="observer", text="ROUND 1 briefing"),
        LLMResponseReceived(
            round_number=1,
            agent_id="observer",
            thinking="The top face glows.",
            text=None,
            tool_calls=[send_call],
            stop_reason=StopReason.TOOL_USE,
            usage=_usage(),
        ),
        ToolCallInvoked(
            round_number=1,
            agent_id="observer",
            call_id="call-1",
            tool_name="send_message",
            arguments={"text": "T bright"},
        ),
        ToolCallInvoked(
            round_number=1,
            agent_id="observer",
            call_id="call-without-response",
            tool_name="read_notifications",
            arguments={},
        ),
        MessageSent(
            round_number=1,
            message=SimulationMessage(
                message_id="m-1",
                channel_id="link",
                sender_agent_id="observer",
                sender_display_name="Field Observer",
                text="T bright",
                timestamp=datetime(2026, 8, 1, tzinfo=UTC),
                round_number=1,
            ),
            token_count=3,
        ),
        ToolResultReceived(
            round_number=1,
            agent_id="observer",
            tool_name="send_message",
            call_id="call-1",
            arguments={"text": "T bright"},
            result="sent",
        ),
        WaitRegistered(
            round_number=1,
            agent_id="observer",
            wait_id="wait-1",
            wait_for=WaitFor.ANY,
            deadline_s=None,
        ),
        WaitRegistered(
            round_number=1,
            agent_id="observer",
            wait_id="wait-2",
            wait_for=WaitFor.ANY,
            deadline_s=None,
            reasoning="Waiting for the engineer's reply.",
        ),
        AgentResumed(
            round_number=1,
            agent_id="observer",
            wait_id="wait-1",
            wake_reasons=["new_notification"],
            waited_seconds=1.5,
            terminated=False,
        ),
        RoundAdvanced(round_number=1, trigger="simulation_start"),
        UnrecognizedEvent(
            round_number=1,
            event_type="veyru_case_started",
            payload={
                "event_id": "e-1",
                "timestamp": "2026-08-01T00:00:00Z",
                "event_type": "veyru_case_started",
                "round_number": 1,
                "case_number": 1,
            },
        ),
    ]


def test_sections_are_split_by_round_and_headed() -> None:
    sections = render_run_transcript(events=_setup_events(build=None) + _round_one_events())

    assert [section.round_number for section in sections] == [0, 1]
    assert section_heading(round_number=0) == "=== Before round 1 ==="
    assert section_heading(round_number=1) == "=== Round 1 ==="


def test_setup_section_holds_the_run_the_build_and_each_system_prompt() -> None:
    build = GlossogenBuild(version="1.2.3", git_commit="abc123", has_uncommitted_changes=True)
    setup = render_run_transcript(events=_setup_events(build=build))[0].text

    assert "Run: veyru/1700000000" in setup
    assert "glossogen: 1.2.3, commit abc123 with uncommitted changes in src/" in setup
    assert '"round_count": 3' in setup
    assert "role Field Observer, model claude-haiku-4-5 on anthropic" in setup
    assert "You watch the creature." in setup


def test_a_log_without_a_build_says_so() -> None:
    setup = render_run_transcript(events=_setup_events(build=None))[0].text

    assert "glossogen: not recorded in this log" in setup


def test_round_keeps_what_agents_were_told_wrote_called_and_received() -> None:
    round_one = render_run_transcript(events=_round_one_events())[0].text

    assert "[briefing to observer]\nROUND 1 briefing" in round_one
    assert "[observer thinks]\nThe top face glows." in round_one
    assert '[observer calls] send_message({"text": "T bright"})' in round_one
    assert "[observer -> #link] T bright" in round_one
    assert "[observer receives from send_message] sent" in round_one
    assert "[observer waits for any] Waiting for the engineer's reply." in round_one


def test_a_drawing_is_written_out_as_its_size_and_pixels() -> None:
    drawing = MessageSent(
        round_number=1,
        message=SimulationMessage(
            message_id="m-drawing",
            channel_id="link",
            sender_agent_id="observer",
            sender_display_name="Field Observer",
            text="",
            timestamp=datetime(2026, 8, 1, tzinfo=UTC),
            round_number=1,
            drawing=CanvasDrawing(
                width=16, height=16, pixels=[CanvasPixel(x=2, y=5), CanvasPixel(x=3, y=5)]
            ),
        ),
        token_count=0,
    )

    round_one = render_run_transcript(events=[drawing])[0].text

    assert "[observer -> #link] [drawing 16x16, 2 pixels: [2, 5] [3, 5]]" in round_one


def test_round_drops_repeated_calls_and_wait_bookkeeping() -> None:
    round_one = render_run_transcript(events=_round_one_events())[0].text

    assert round_one.count("send_message({") == 1
    assert "[observer calls] read_notifications({})" in round_one
    assert "wait-1" not in round_one
    assert "new_notification" not in round_one


def test_other_events_print_their_fields_without_platform_bookkeeping() -> None:
    round_one = render_run_transcript(events=_round_one_events())[0].text

    assert '[round_advanced] {"trigger": "simulation_start"}' in round_one
    assert '[veyru_case_started] {"case_number": 1}' in round_one
    assert "event_id" not in round_one
    assert "timestamp" not in round_one


def test_an_empty_response_is_reported_with_its_stop_reason() -> None:
    empty = LLMResponseReceived(
        round_number=2,
        agent_id="observer",
        thinking=None,
        text=None,
        tool_calls=[],
        stop_reason=StopReason.END_TURN,
        usage=_usage(),
    )

    text = render_run_transcript(events=[empty])[0].text

    assert text == f"[observer] empty response, stop reason {StopReason.END_TURN}"


def _response_with_call(call_id: str) -> LLMResponseReceived:
    return LLMResponseReceived(
        round_number=1,
        agent_id="observer",
        thinking=None,
        text="I will describe the faces.",
        tool_calls=[
            ToolCallRequest(call_id=call_id, tool_name="send_message", arguments={"text": "T"})
        ],
        stop_reason=StopReason.TOOL_USE,
        usage=_usage(),
    )


def test_a_response_logged_after_its_call_prints_before_it_and_the_call_prints_once() -> None:
    events: list[SimulationEvent] = [
        ToolCallInvoked(
            round_number=1,
            agent_id="observer",
            call_id="call-1",
            tool_name="send_message",
            arguments={"text": "T"},
        ),
        ToolResultReceived(
            round_number=1,
            agent_id="observer",
            tool_name="send_message",
            call_id="call-1",
            arguments={"text": "T"},
            result="sent",
        ),
        _response_with_call(call_id="call-1"),
    ]

    lines = render_run_transcript(events=events)[0].text.splitlines()

    assert lines == [
        "[observer writes]",
        "I will describe the faces.",
        '[observer calls] send_message({"text": "T"})',
        "[observer receives from send_message] sent",
    ]


def test_a_call_that_never_ran_prints_with_its_response() -> None:
    text = render_run_transcript(events=[_response_with_call(call_id="refused")])[0].text

    assert text.splitlines() == [
        "[observer writes]",
        "I will describe the faces.",
        '[observer calls] send_message({"text": "T"})',
    ]
