"""Which channels a run's reasoning is shown under.

The run page shows a reasoning entry in a channel when it is linked to that
channel, and the PDF export filters the same way. An entry is linked to the
channel of its agent's previous send and of its next send, so a channel shows what
the agent was thinking on either side of what it said there. These read a written
log back through ``load_run_detail``.
"""

from pathlib import Path

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    MessageSent,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
    StopReason,
)
from glossogen.models.event_base import EventBase, TokenUsage
from glossogen.models.message import SimulationMessage
from glossogen.run_file_paths import event_log_path
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.server.runs.models import ReasoningKind, RunDetailResponse
from tests.fakes.local_app import at_second, write_event_log

SCENARIO = "veyru"
CHANNELS = ["link", "ops", "side"]
NO_USAGE = TokenUsage(
    input_tokens=0,
    output_tokens=0,
    reasoning_tokens=0,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
)


def registered(agent_id: str) -> AgentRegistered:
    """``agent_id`` registered on every channel."""
    return AgentRegistered(
        round_number=0,
        timestamp=at_second(0),
        agent_id=agent_id,
        role_name=agent_id,
        model="claude-sonnet-4-6",
        provider="anthropic",
        system_prompt="",
        channel_ids=CHANNELS,
        tool_names=["send_message"],
        model_settings=AgentModelSettings(max_tokens=1024),
    )


def thought(event_id: str, agent_id: str, seconds: int) -> LLMResponseReceived:
    """A response carrying text only, which becomes one reasoning entry."""
    return LLMResponseReceived(
        event_id=event_id,
        round_number=1,
        timestamp=at_second(seconds),
        agent_id=agent_id,
        text=f"thinking {event_id}",
        tool_calls=[],
        stop_reason=StopReason.TOOL_USE,
        usage=NO_USAGE,
    )


def sent(agent_id: str, channel_id: str, seconds: int) -> MessageSent:
    """A message by ``agent_id`` on ``channel_id`` at ``seconds``, with id ``<agent>-<seconds>``."""
    return MessageSent(
        round_number=1,
        timestamp=at_second(seconds),
        message=SimulationMessage(
            message_id=f"{agent_id}-{seconds}",
            channel_id=channel_id,
            sender_agent_id=agent_id,
            sender_display_name=agent_id,
            text="hello",
            timestamp=at_second(seconds),
            round_number=1,
        ),
        token_count=1,
    )


async def detail_of(tmp_path: Path, events: list[EventBase]) -> RunDetailResponse:
    """Write ``events`` between a start and an end, and read the run's detail back."""
    started = SimulationStarted(
        round_number=0,
        timestamp=at_second(0),
        run_id=f"{SCENARIO}/1770000100",
        scenario_name=SCENARIO,
        scenario_description="",
        channel_ids=CHANNELS,
        provider="anthropic",
        scenario_config={},
    )
    ended = SimulationEnded(
        round_number=1,
        timestamp=at_second(100),
        reason=RunStatus.SCENARIO_COMPLETE,
        total_messages=0,
        total_cost_usd=0.0,
    )
    run_dir = write_event_log(
        runs_dir=tmp_path,
        scenario_name=SCENARIO,
        run_dir_name="1770000100",
        events=[started, *events, ended],
        extra_records=[],
    )
    return await load_run_detail(
        log_path=event_log_path(run_dir=run_dir, scenario_name=SCENARIO), children=[]
    )


def channels_by_entry(detail: RunDetailResponse) -> dict[str, list[str]]:
    """Each reasoning entry's id mapped to the channels it is linked to."""
    return {entry.message_id: entry.channel_ids for entry in detail.reasoning}


async def test_reasoning_between_two_sends_is_linked_to_both_channels(tmp_path: Path) -> None:
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            sent(agent_id="alice", channel_id="ops", seconds=1),
            thought(event_id="between", agent_id="alice", seconds=2),
            sent(agent_id="alice", channel_id="link", seconds=3),
        ],
    )

    assert channels_by_entry(detail=detail) == {"between": ["link", "ops"]}


async def test_reasoning_between_two_sends_on_one_channel_is_linked_once(tmp_path: Path) -> None:
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            sent(agent_id="alice", channel_id="link", seconds=1),
            thought(event_id="between", agent_id="alice", seconds=2),
            sent(agent_id="alice", channel_id="link", seconds=3),
        ],
    )

    assert channels_by_entry(detail=detail) == {"between": ["link"]}


async def test_reasoning_before_the_first_send_is_linked_to_that_send(tmp_path: Path) -> None:
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            thought(event_id="first", agent_id="alice", seconds=1),
            thought(event_id="second", agent_id="alice", seconds=2),
            sent(agent_id="alice", channel_id="ops", seconds=3),
        ],
    )

    assert channels_by_entry(detail=detail) == {"first": ["ops"], "second": ["ops"]}


async def test_reasoning_after_the_last_send_is_linked_to_that_send(tmp_path: Path) -> None:
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            sent(agent_id="alice", channel_id="ops", seconds=1),
            thought(event_id="after", agent_id="alice", seconds=2),
        ],
    )

    assert channels_by_entry(detail=detail) == {"after": ["ops"]}


async def test_an_agent_that_never_sends_has_its_reasoning_in_no_channel(tmp_path: Path) -> None:
    """Such reasoning shows only in the all-activity view."""
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            thought(event_id="silent", agent_id="alice", seconds=1),
        ],
    )

    assert channels_by_entry(detail=detail) == {"silent": []}


async def test_another_agents_sends_do_not_link_an_agents_reasoning(tmp_path: Path) -> None:
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            registered(agent_id="bob"),
            sent(agent_id="alice", channel_id="ops", seconds=1),
            sent(agent_id="bob", channel_id="side", seconds=2),
            thought(event_id="alice-thought", agent_id="alice", seconds=3),
            thought(event_id="bob-thought", agent_id="bob", seconds=4),
            sent(agent_id="bob", channel_id="link", seconds=5),
        ],
    )

    assert channels_by_entry(detail=detail) == {
        "alice-thought": ["ops"],
        "bob-thought": ["link", "side"],
    }


async def test_sends_are_ordered_by_time_not_by_log_position(tmp_path: Path) -> None:
    """A send logged after the reasoning but stamped before it is still the previous send."""
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            thought(event_id="late", agent_id="alice", seconds=5),
            sent(agent_id="alice", channel_id="ops", seconds=1),
            sent(agent_id="alice", channel_id="link", seconds=9),
        ],
    )

    assert channels_by_entry(detail=detail) == {"late": ["link", "ops"]}


async def test_the_thinking_and_text_of_one_response_share_their_channels(
    tmp_path: Path,
) -> None:
    response = thought(event_id="both", agent_id="alice", seconds=2)
    response.thinking = "weighing it"
    detail = await detail_of(
        tmp_path=tmp_path,
        events=[
            registered(agent_id="alice"),
            sent(agent_id="alice", channel_id="ops", seconds=1),
            response,
            sent(agent_id="alice", channel_id="link", seconds=3),
        ],
    )

    assert [(entry.kind, entry.channel_ids) for entry in detail.reasoning] == [
        (ReasoningKind.THINKING, ["link", "ops"]),
        (ReasoningKind.TEXT, ["link", "ops"]),
    ]
