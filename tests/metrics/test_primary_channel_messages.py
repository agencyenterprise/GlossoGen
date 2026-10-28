"""The per-round grouping of channel messages that metrics and round views read.

`group_messages_by_round` is the one loop; the collectors built on it differ in
which text they read and whether they drop empty text, and those differences
are what these tests pin down. An empty message on a scored channel is kept by
the grouping and by the scenario round views, and dropped by the metrics.
"""

from datetime import UTC, datetime

from glossogen.evaluation.metric_core import primary_channel_messages
from glossogen.evaluation.metric_core.primary_channel_messages import (
    RoundMessages,
    collect_primary_messages_by_round,
    transmitted_text,
)
from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.evaluation.metrics import language_repetition_metric
from glossogen.evaluation.metrics.communication import round_view
from glossogen.evaluation.metrics.communication.round_view import CommunicationMessageLine
from glossogen.models.event import MessageSent, SimulationEvent, ToolResultReceived
from glossogen.models.mcp_responses import SendReceipt, SendStatus
from glossogen.models.message import SimulationMessage
from glossogen.runtime.communication_tools import SEND_MESSAGE_TOOL_NAME

FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
LINK = frozenset({"link"})


def build_message(
    *, message_id: str, round_number: int, channel_id: str, sender: str, text: str
) -> MessageSent:
    """Build a MessageSent with the given transmitted text."""
    return MessageSent(
        timestamp=FIXED_TIME,
        round_number=round_number,
        token_count=len(text),
        message=SimulationMessage(
            message_id=message_id,
            channel_id=channel_id,
            sender_agent_id=sender,
            sender_display_name=sender,
            text=text,
            timestamp=FIXED_TIME,
            round_number=round_number,
        ),
    )


def build_send_result(*, message_id: str, round_number: int, pristine: str) -> ToolResultReceived:
    """Build the send_message result that records the text the sender composed."""
    return ToolResultReceived(
        timestamp=FIXED_TIME,
        round_number=round_number,
        agent_id="alice",
        tool_name=SEND_MESSAGE_TOOL_NAME,
        call_id=f"call-{message_id}",
        arguments={"text": pristine},
        result=SendReceipt(status=SendStatus.SENT, message_id=message_id).model_dump_json(),
    )


def mixed_events() -> list[SimulationEvent]:
    """Rounds out of order, an off-channel message, and a round whose only message is empty."""
    return [
        build_message(
            message_id="m1", round_number=2, channel_id="link", sender="alice", text="b1"
        ),
        build_message(message_id="m2", round_number=1, channel_id="link", sender="bob", text="a1"),
        build_message(message_id="m3", round_number=1, channel_id="ops", sender="bob", text="x"),
        build_message(message_id="m4", round_number=2, channel_id="link", sender="bob", text=""),
        build_message(
            message_id="m5", round_number=1, channel_id="link", sender="alice", text="a2"
        ),
        build_message(message_id="m6", round_number=3, channel_id="link", sender="alice", text=""),
    ]


def test_grouping_sorts_rounds_keeps_log_order_and_keeps_empty_messages() -> None:
    """Empty messages are the readers' call, so the grouping keeps them."""
    grouped = primary_channel_messages.group_messages_by_round(
        events=mixed_events(), channel_ids=LINK
    )

    assert [
        (group.round_number, [message.message.message_id for message in group.messages])
        for group in grouped
    ] == [(1, ["m2", "m5"]), (2, ["m1", "m4"]), (3, ["m6"])]


def test_grouping_ignores_events_that_are_not_messages() -> None:
    """A send result in the log is not a message."""
    events: list[SimulationEvent] = [
        build_send_result(message_id="m1", round_number=1, pristine="hello"),
        build_message(message_id="m1", round_number=1, channel_id="link", sender="alice", text="h"),
    ]

    grouped = primary_channel_messages.group_messages_by_round(events=events, channel_ids=LINK)

    assert [(group.round_number, len(group.messages)) for group in grouped] == [(1, 1)]


def test_the_metric_collector_drops_empty_texts_and_rounds_left_empty() -> None:
    """Round 3's only message is empty, so the round is missing rather than zero."""
    rounds = collect_primary_messages_by_round(
        events=mixed_events(), channel_ids=LINK, text_of=transmitted_text
    )

    assert rounds == [
        RoundMessages(round_number=1, texts=["a1", "a2"]),
        RoundMessages(round_number=2, texts=["b1"]),
    ]


def test_the_language_repetition_collector_filters_on_pristine_text() -> None:
    """Noise can empty a message on the wire; the judge still sees what was composed."""
    events: list[SimulationEvent] = [
        build_send_result(message_id="m1", round_number=1, pristine="twelve 12"),
        build_message(message_id="m1", round_number=1, channel_id="link", sender="alice", text=""),
        build_message(message_id="m2", round_number=2, channel_id="link", sender="bob", text=""),
    ]

    rounds = language_repetition_metric._collect_link_messages_by_round(  # pyright: ignore[reportPrivateUsage]
        events=events,
        channel_ids=LINK,
        pristine_index=build_pristine_text_index(events=events),
    )

    assert [
        (round_messages.round_number, [(m.message_id, m.text) for m in round_messages.messages])
        for round_messages in rounds
    ] == [(1, [("m1", "twelve 12")])]


def test_round_view_lines_carry_transmitted_text_and_keep_empty_messages() -> None:
    """The communication judges see what the channel delivered, silence included."""
    lines = round_view.message_lines_by_round(events=mixed_events(), channel_ids=LINK)

    assert lines == {
        1: [
            CommunicationMessageLine(sender_agent_id="bob", channel_id="link", text="a1"),
            CommunicationMessageLine(sender_agent_id="alice", channel_id="link", text="a2"),
        ],
        2: [
            CommunicationMessageLine(sender_agent_id="alice", channel_id="link", text="b1"),
            CommunicationMessageLine(sender_agent_id="bob", channel_id="link", text=""),
        ],
        3: [CommunicationMessageLine(sender_agent_id="alice", channel_id="link", text="")],
    }
