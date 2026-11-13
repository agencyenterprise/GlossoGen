"""Where a rebuilt history places tool calls whose response was cut off.

Each tool call is logged when it starts, and the model response that made it
only once the whole turn ends. A cut through the log can keep the call and lose
its response: a crash mid-turn, or a fork's copy cut at the boundary while the
predecessor was mid-turn. Such a call belongs after every turn whose response
was logged before it and before every later one.
"""

from datetime import UTC, datetime, timedelta

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

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
        assert isinstance(event, EventBase)
        stamped.append(event.model_copy(update={"timestamp": start + timedelta(seconds=index)}))
    return stamped


def _started() -> SimulationStarted:
    return SimulationStarted(
        round_number=0,
        run_id="smoke/1",
        scenario_name="smoke",
        scenario_description="",
        channel_ids=["link"],
        scenario_config={"round_count": 4},
        provider="anthropic",
    )


def _call(round_number: int, call_id: str) -> list[SimulationEvent]:
    """A ``record_finding`` call and its result, without the response that made it."""
    arguments = {"finding": call_id}
    return [
        ToolCallInvoked(
            round_number=round_number,
            agent_id=_AGENT,
            call_id=call_id,
            tool_name="record_finding",
            arguments=arguments,
        ),
        ToolResultReceived(
            round_number=round_number,
            agent_id=_AGENT,
            tool_name="record_finding",
            call_id=call_id,
            arguments=arguments,
            result="ok",
        ),
    ]


def _turn(round_number: int, text: str, call_id: str) -> list[SimulationEvent]:
    """A whole turn: one call, its result, then the response holding the text."""
    return [
        *_call(round_number=round_number, call_id=call_id),
        LLMResponseReceived(
            round_number=round_number,
            agent_id=_AGENT,
            text=text,
            tool_calls=[
                ToolCallRequest(
                    call_id=call_id, tool_name="record_finding", arguments={"finding": call_id}
                )
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


def _order(events: list[SimulationEvent], filter_below_round: int | None) -> list[str]:
    """The texts and call ids of the seat's rebuilt history, in order."""
    stamped = _stamped(events=events)
    history = build_message_history(
        events=stamped,
        agent_id=_AGENT,
        system_prompt="do things",
        runner_prompts=platform_runner_prompts(role_name="worker"),
        target_timestamp=stamped[-1].timestamp,
        cutoff_round=None,
        tool_calls_only=filter_below_round is not None,
        channel_visibility={},
        history_floor_round=None,
        filter_below_round=filter_below_round,
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


def test_a_call_cut_off_by_a_crash_comes_last() -> None:
    """On a plain resume the cut-off call is the newest thing the agent did."""
    order = _order(
        events=[
            _started(),
            *_turn(round_number=1, text="round one", call_id="r1"),
            *_call(round_number=2, call_id="cut-r2"),
        ],
        filter_below_round=None,
    )

    assert order == ["round one", "r1", "cut-r2"]


def test_a_predecessor_call_cut_at_the_fork_stays_before_the_replacements_turns() -> None:
    """On recovery of a replace-agent fork, each cut-off call keeps its place in time.

    The predecessor's round-2 call lost its response at the fork boundary. The
    replacement then played round 3, and its own round-4 call lost its response
    to the crash. The first goes before the replacement's turn, the second after.
    """
    order = _order(
        events=[
            _started(),
            *_call(round_number=2, call_id="predecessor-r2"),
            RoundAdvanced(round_number=3, trigger="round_timeout"),
            *_turn(round_number=3, text="my own words", call_id="own-r3"),
            RoundAdvanced(round_number=4, trigger="all_agents_idle"),
            *_call(round_number=4, call_id="cut-r4"),
        ],
        filter_below_round=3,
    )

    assert order == ["predecessor-r2", "my own words", "own-r3", "cut-r4"]
