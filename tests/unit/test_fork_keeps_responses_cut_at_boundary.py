"""A fork's cut log keeps each response whose tool calls ran before the cut.

The runner logs a response once its tool calls have run, so a call that ran
before a fork's boundary can belong to a response logged after it. The fork
inserts that response before the boundary event, holding only the calls that
ran before the boundary.
"""

from pathlib import Path

from glossogen.models.event import (
    EventBase,
    LLMResponseReceived,
    RoundAdvanced,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_derivation.run_jsonl_rewriter import insert_responses_cut_at_boundary
from glossogen.run_storage.event_log_reader import load_events

AGENT = "player_a"
BEFORE_CUT = ToolCallRequest(call_id="call_before", tool_name="move", arguments={"to": 1})
AFTER_CUT = ToolCallRequest(call_id="call_after", tool_name="move", arguments={"to": 2})


def invoked(call: ToolCallRequest) -> ToolCallInvoked:
    return ToolCallInvoked(
        agent_id=AGENT,
        call_id=call.call_id,
        tool_name=call.tool_name,
        arguments=call.arguments,
        round_number=1,
    )


def response(calls: list[ToolCallRequest]) -> LLMResponseReceived:
    return LLMResponseReceived(
        agent_id=AGENT,
        thinking="I move twice.",
        text="Moving.",
        tool_calls=calls,
        stop_reason=StopReason.TOOL_USE,
        usage=TokenUsage(
            input_tokens=10,
            output_tokens=5,
            reasoning_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        round_number=1,
    )


def started() -> SimulationStarted:
    return SimulationStarted(
        round_number=0,
        run_id="signal_game/1",
        scenario_name="signal_game",
        scenario_description="",
        channel_ids=[],
        scenario_config={},
        provider="anthropic",
    )


def jsonl(events: list[EventBase]) -> bytes:
    return b"".join(event.model_dump_json().encode() + b"\n" for event in events)


BOUNDARY = RoundAdvanced(trigger="idle", round_number=2)


async def cut_at(
    tmp_path: Path, before: list[EventBase], after: bytes
) -> tuple[int, list[EventBase]]:
    """Write ``before``, the boundary and ``after`` as a source log; cut a copy at the boundary."""
    head = jsonl(events=[started(), *before, BOUNDARY])
    source = tmp_path / "source.jsonl"
    source.write_bytes(head + after)
    copy = tmp_path / "copy.jsonl"
    copy.write_bytes(head)
    inserted = await insert_responses_cut_at_boundary(
        source_log_path=source, log_path=copy, truncate_after_offset=len(head)
    )
    return inserted, list(await load_events(log_path=copy))


async def test_a_response_logged_after_the_cut_is_inserted_with_its_earlier_calls(
    tmp_path: Path,
) -> None:
    inserted, events = await cut_at(
        tmp_path=tmp_path,
        before=[invoked(call=BEFORE_CUT)],
        after=jsonl(events=[invoked(call=AFTER_CUT), response(calls=[BEFORE_CUT, AFTER_CUT])]),
    )

    assert inserted == 1
    assert events[-1].event_id == BOUNDARY.event_id
    [logged] = [event for event in events if isinstance(event, LLMResponseReceived)]
    assert logged.tool_calls == [BEFORE_CUT]
    assert logged.text == "Moving."
    assert logged.thinking == "I move twice."


async def test_a_response_logged_before_the_cut_is_not_inserted_again(tmp_path: Path) -> None:
    inserted, events = await cut_at(
        tmp_path=tmp_path,
        before=[invoked(call=BEFORE_CUT), response(calls=[BEFORE_CUT])],
        after=jsonl(events=[invoked(call=AFTER_CUT), response(calls=[AFTER_CUT])]),
    )

    assert inserted == 0
    assert len([event for event in events if isinstance(event, LLMResponseReceived)]) == 1


async def test_a_last_source_line_still_being_written_is_not_read(tmp_path: Path) -> None:
    complete = jsonl(events=[response(calls=[BEFORE_CUT])])
    inserted, _ = await cut_at(
        tmp_path=tmp_path,
        before=[invoked(call=BEFORE_CUT)],
        after=complete + b'{"event_type": "llm_resp',
    )

    assert inserted == 1
