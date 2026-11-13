"""The resume context files record the history a resumed agent is handed.

``glossogen run --resume`` writes them before the supervisor launches, so a
history part that cannot be written as JSON stops every resume, fork and
replace-agent run at startup. The files are also the record an operator reads
to check what a replaced or imported seat was seeded with, so each part has to
carry its content.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import orjson
import pytest
from pydantic_ai.messages import ModelMessage

from glossogen.models.event import (
    ContextCompacted,
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.thinking_part_record import ThinkingPartRecord
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.run_replay.resume_context_writer import write_resume_context_files
from glossogen.scenario_contract.platform_runner_prompts import platform_runner_prompts

_AGENT = "seat"
_OTHER_AGENT = "other_seat"
_SUMMARY = "the agents agreed on a shorthand"


def _stamped(events: list[SimulationEvent]) -> list[SimulationEvent]:
    """Give each event a distinct increasing timestamp, in list order."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
    stamped: list[SimulationEvent] = []
    for index, event in enumerate(events):
        assert isinstance(event, EventBase)
        stamped.append(event.model_copy(update={"timestamp": start + timedelta(seconds=index)}))
    return stamped


def _started() -> SimulationStarted:
    return SimulationStarted(
        round_number=0,
        run_id="smoke/1",
        scenario_name="smoke",
        scenario_description="",
        channel_ids=[],
        scenario_config={},
        provider="anthropic",
    )


def _cycle() -> list[SimulationEvent]:
    """One round-1 cycle: signed thinking, a sentence and one recorded finding."""
    arguments = {"finding": "red means stop"}
    return [
        ToolCallInvoked(
            round_number=1,
            agent_id=_AGENT,
            call_id="call-1",
            tool_name="record_finding",
            arguments=arguments,
        ),
        ToolResultReceived(
            round_number=1,
            agent_id=_AGENT,
            tool_name="record_finding",
            call_id="call-1",
            arguments=arguments,
            result="recorded",
        ),
        LLMResponseReceived(
            round_number=1,
            agent_id=_AGENT,
            thinking="weighing it",
            thinking_parts=[
                ThinkingPartRecord(
                    content="weighing it",
                    id=None,
                    signature="sig-1",
                    provider_name="anthropic",
                    provider_details=None,
                )
            ],
            text="noting it down",
            tool_calls=[
                ToolCallRequest(call_id="call-1", tool_name="record_finding", arguments=arguments)
            ],
            stop_reason=StopReason.TOOL_USE,
            usage=TokenUsage(
                input_tokens=1,
                output_tokens=1,
                reasoning_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        ),
    ]


def _compaction() -> ContextCompacted:
    return ContextCompacted(
        round_number=1,
        agent_id=_AGENT,
        provider_name="anthropic",
        summary_char_count=len(_SUMMARY),
        summary_text=_SUMMARY,
        part_id=None,
        provider_details=None,
        replayable=True,
    )


def _history(events: list[SimulationEvent]) -> list[ModelMessage]:
    """The seat's full reconstructed history, as a plain ``--resume`` builds it."""
    stamped = _stamped(events=events)
    return build_message_history(
        events=stamped,
        agent_id=_AGENT,
        system_prompt="you are a seat",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=stamped[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=False,
        channel_visibility={},
        history_floor_round=None,
        filter_below_round=None,
        split_parallel_tool_calls=False,
    )


def _written_parts(*, run_dir: Path, agent_id: str) -> list[dict[str, Any]]:
    """Every part in ``agent_id``'s resume context file, in message order."""
    payload = orjson.loads((run_dir / f"resume_context_{agent_id}.json").read_bytes())
    return [part for message in payload["messages"] for part in message["parts"]]


def test_each_agent_gets_a_file_holding_its_history_in_order(tmp_path: Path) -> None:
    history = _history(events=[_started(), *_cycle()])

    write_resume_context_files(
        run_dir=tmp_path,
        agent_message_histories={_AGENT: history, _OTHER_AGENT: []},
    )

    payload = orjson.loads((tmp_path / f"resume_context_{_AGENT}.json").read_bytes())
    assert payload["agent_id"] == _AGENT
    assert payload["num_messages"] == len(history)
    parts = _written_parts(run_dir=tmp_path, agent_id=_AGENT)
    assert [part["kind"] for part in parts] == [
        "system",
        "user",
        "thinking",
        "text",
        "tool_call",
        "tool_return",
    ]
    thinking, text, call, result = parts[2:6]
    assert thinking["content"] == "weighing it"
    assert thinking["signature_recorded"] is True
    assert text["content"] == "noting it down"
    assert call["args"] == {"finding": "red means stop"}
    assert call["call_id"] == result["call_id"] == "call-1"
    assert result["content"] == "recorded"

    other = orjson.loads((tmp_path / f"resume_context_{_OTHER_AGENT}.json").read_bytes())
    assert other == {"agent_id": _OTHER_AGENT, "num_messages": 0, "messages": []}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "resume_context_writer._serialize_part has no branch for CompactionPart, so "
        "a compaction falls back to {'kind': 'CompactionPart'} and the file drops the "
        "summary the resumed agent is handed in place of its earlier turns."
    ),
)
def test_a_compaction_is_written_with_its_summary(tmp_path: Path) -> None:
    history = _history(events=[_started(), _compaction(), *_cycle()])

    write_resume_context_files(run_dir=tmp_path, agent_message_histories={_AGENT: history})

    parts = _written_parts(run_dir=tmp_path, agent_id=_AGENT)
    assert any(part.get("content") == _SUMMARY for part in parts)
