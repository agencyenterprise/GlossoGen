"""The seeding filters stop at ``filter_below_round``.

``tool_calls_only`` and ``channel_visibility`` exist to seed a replacement
agent with a stripped view of its predecessor's history. Crash recovery of a
replace-agent fork applies the same filter over a log that also holds the
replacement's own turns, so the filters are bounded to the rounds before the
fork's entry round: the predecessor's text is stripped and its blocked-channel
calls dropped, while the replacement keeps everything it produced itself.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from glossogen.models.channel_visibility import ChannelVisibility, ChannelVisibilityNone
from glossogen.models.event import (
    LLMResponseReceived,
    RoundAdvanced,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.run_replay.message_history_builder import build_message_history
from glossogen.scenario_contract.platform_runner_prompts import platform_runner_prompts

_AGENT = "seat"


def _stamped(events: list[SimulationEvent]) -> list[SimulationEvent]:
    """Give each event a distinct increasing timestamp, in list order."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
    stamped: list[SimulationEvent] = []
    for index, event in enumerate(events):
        base = event
        assert isinstance(base, EventBase)
        stamped.append(base.model_copy(update={"timestamp": start + timedelta(seconds=index)}))
    return stamped


def _usage() -> TokenUsage:
    """A minimal token usage record."""
    return TokenUsage(
        input_tokens=1,
        output_tokens=1,
        reasoning_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def _turn(round_number: int, text: str, call_id: str) -> list[SimulationEvent]:
    """One LLM cycle in ``round_number``: some text plus one postmortem send."""
    events: list[SimulationEvent] = [
        ToolCallInvoked(
            round_number=round_number,
            agent_id=_AGENT,
            call_id=call_id,
            tool_name="send_message",
            arguments={"channel_id": "postmortem", "text": "sent"},
        ),
        ToolResultReceived(
            round_number=round_number,
            agent_id=_AGENT,
            tool_name="send_message",
            call_id=call_id,
            arguments={"channel_id": "postmortem", "text": "sent"},
            result="ok",
        ),
        LLMResponseReceived(
            round_number=round_number,
            agent_id=_AGENT,
            text=text,
            tool_calls=[
                ToolCallRequest(
                    call_id=call_id,
                    tool_name="send_message",
                    arguments={"channel_id": "postmortem", "text": "sent"},
                )
            ],
            stop_reason=StopReason.TOOL_USE,
            usage=_usage(),
        ),
    ]
    return events


def _events() -> list[SimulationEvent]:
    """A predecessor turn in round 1 and the seat's own turn in round 3."""
    return _stamped(
        events=[
            SimulationStarted(
                round_number=0,
                run_id="smoke/1",
                scenario_name="smoke",
                scenario_description="",
                channel_ids=["link", "postmortem"],
                scenario_config={"round_count": 3},
                provider="anthropic",
            ),
            *_turn(round_number=1, text="predecessor thoughts", call_id="c-1"),
            *_turn(round_number=3, text="my own words", call_id="c-2"),
        ]
    )


def _build(filter_below_round: int | None) -> tuple[set[str], set[str]]:
    """Reconstruct the seat's history and collect its surviving texts and call ids."""
    events = _events()
    visibility: dict[str, ChannelVisibility] = {"postmortem": ChannelVisibilityNone()}
    history = build_message_history(
        events=events,
        agent_id=_AGENT,
        system_prompt="do things",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=True,
        channel_visibility=visibility,
        history_floor_round=None,
        filter_below_round=filter_below_round,
        split_parallel_tool_calls=False,
    )
    texts: set[str] = set()
    call_ids: set[str] = set()
    for message in history:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, TextPart):
                texts.add(part.content)
            if isinstance(part, ToolCallPart):
                call_ids.add(part.tool_call_id)
    return texts, call_ids


def test_the_window_keeps_the_seats_own_turns_intact() -> None:
    """Rounds at or past the window pass through: text kept, blocked calls kept."""
    texts, call_ids = _build(filter_below_round=3)

    assert "my own words" in texts
    assert "predecessor thoughts" not in texts
    assert call_ids == {"c-2"}


def test_no_window_filters_the_whole_history() -> None:
    """Without a window the filters behave as before: everything is seeded stripped."""
    texts, call_ids = _build(filter_below_round=None)

    assert texts == set()
    assert call_ids == set()


def _recovered_history_with_a_boundary_orphan() -> list[str]:
    """The seat's recovered history, in order, when a predecessor call lost its parent.

    The clone is cut at the boundary ``RoundAdvanced``. A predecessor cycle that
    straddled it, as a round timeout mid-cycle leaves it, keeps the round-2 call
    and result but loses the ``LLMResponseReceived`` flushed after the cut. The
    replacement then plays round 3 and the fork crashes as round 4 opens.
    """
    events = _stamped(
        events=[
            SimulationStarted(
                round_number=0,
                run_id="smoke/1",
                scenario_name="smoke",
                scenario_description="",
                channel_ids=["link"],
                scenario_config={"round_count": 4},
                provider="anthropic",
            ),
            ToolCallInvoked(
                round_number=2,
                agent_id=_AGENT,
                call_id="predecessor-r2",
                tool_name="record_finding",
                arguments={"finding": "r2"},
            ),
            ToolResultReceived(
                round_number=2,
                agent_id=_AGENT,
                tool_name="record_finding",
                call_id="predecessor-r2",
                arguments={"finding": "r2"},
                result="ok",
            ),
            RoundAdvanced(round_number=3, trigger="round_timeout"),
            *_turn(round_number=3, text="my own words", call_id="own-r3"),
            RoundAdvanced(round_number=4, trigger="all_agents_idle"),
        ]
    )
    history = build_message_history(
        events=events,
        agent_id=_AGENT,
        system_prompt="do things",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=events[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=True,
        channel_visibility={},
        history_floor_round=None,
        filter_below_round=3,
        split_parallel_tool_calls=False,
    )
    order: list[str] = []
    for message in history:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, TextPart):
                order.append(part.content)
            if isinstance(part, ToolCallPart):
                order.append(part.tool_call_id)
    return order


@pytest.mark.xfail(
    strict=True,
    reason=(
        "build_message_history appends every parentless call as one synthetic "
        "cycle after all parented cycles (message_history_builder.py, "
        "_build_orphan_cycle). On crash recovery the predecessor's round-2 "
        "orphan lands after the replacement's round-3 turn, so the seat's "
        "latest turn reads as its predecessor's."
    ),
)
def test_a_predecessor_call_that_lost_its_parent_stays_before_the_replacements_turns() -> None:
    """Recovered history keeps the predecessor's round-2 call ahead of round 3."""
    order = _recovered_history_with_a_boundary_orphan()

    assert set(order) == {"predecessor-r2", "my own words", "own-r3"}
    assert order.index("predecessor-r2") < order.index("my own words")
