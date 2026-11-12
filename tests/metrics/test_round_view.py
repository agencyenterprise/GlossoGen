"""How `round_views_with_case` joins a round's case event with its channel messages.

The scenarios that log one case event per round build their communication views
through it, so these tests pin the join: which rounds get a view, which case a
round reads, and what a round without a case shows.
"""

from datetime import UTC, datetime
from typing import Literal

from glossogen.evaluation.metrics.communication.round_view import round_views_with_case
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.models.event_base import EventBase
from glossogen.models.message import SimulationMessage
from glossogen.scenario_contract.communication_round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)

FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CHANNEL = "link"


class CaseLogged(EventBase):
    """A round's case, as a scenario would log it at round start."""

    event_type: Literal["case_logged"] = "case_logged"
    label: str


def case(*, round_number: int, label: str) -> CaseLogged:
    """Build a case event for ``round_number``."""
    return CaseLogged(timestamp=FIXED_TIME, round_number=round_number, label=label)


def message(*, round_number: int, channel_id: str, text: str) -> MessageSent:
    """Build a message sent by ``alice`` on ``channel_id``."""
    return MessageSent(
        timestamp=FIXED_TIME,
        round_number=round_number,
        token_count=len(text),
        message=SimulationMessage(
            message_id=f"{channel_id}-{round_number}-{text}",
            channel_id=channel_id,
            sender_agent_id="alice",
            sender_display_name="alice",
            text=text,
            timestamp=FIXED_TIME,
            round_number=round_number,
        ),
    )


def render_header(logged: CaseLogged) -> str:
    """Header naming the case."""
    return f"header {logged.label}"


def render_block(logged: CaseLogged) -> str:
    """Ground-truth block naming the case."""
    return f"block {logged.label}"


def build_views(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Run the join with this module's renderers and missing-case texts."""
    return round_views_with_case(
        events=events,
        case_event_cls=CaseLogged,
        channel_ids=frozenset({CHANNEL}),
        render_header=render_header,
        render_ground_truth_block=render_block,
        missing_case_header="(no header)",
        missing_case_ground_truth_block="(no block)",
    )


def test_each_round_with_a_case_or_a_message_gets_one_view_in_round_order() -> None:
    """A silent round with a case is kept; a round with only off-channel talk is not."""
    events: list[SimulationEvent] = [
        message(round_number=3, channel_id=CHANNEL, text="no case logged"),
        case(round_number=1, label="first"),
        message(round_number=1, channel_id=CHANNEL, text="hello"),
        case(round_number=2, label="silent"),
        message(round_number=4, channel_id="postmortem", text="off channel"),
    ]

    views = build_views(events=events)

    assert views == [
        CommunicationRoundView(
            round_number=1,
            header="header first",
            ground_truth_block="block first",
            messages=[
                CommunicationMessageLine(sender_agent_id="alice", channel_id=CHANNEL, text="hello")
            ],
        ),
        CommunicationRoundView(
            round_number=2, header="header silent", ground_truth_block="block silent", messages=[]
        ),
        CommunicationRoundView(
            round_number=3,
            header="(no header)",
            ground_truth_block="(no block)",
            messages=[
                CommunicationMessageLine(
                    sender_agent_id="alice", channel_id=CHANNEL, text="no case logged"
                )
            ],
        ),
    ]


def test_a_round_reads_the_last_case_logged_for_it() -> None:
    """A resumed round, or a second team's copy of the case, replaces the earlier event."""
    events: list[SimulationEvent] = [
        case(round_number=1, label="before resume"),
        case(round_number=1, label="after resume"),
    ]

    [view] = build_views(events=events)

    assert (view.header, view.ground_truth_block) == ("header after resume", "block after resume")
