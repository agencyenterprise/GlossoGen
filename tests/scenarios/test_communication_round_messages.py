"""The messages each scenario's `build_communication_rounds` hands the communication judges.

These scenarios share one message grouping and differ in which channels they
read. Each is fed messages on its own channels and on one it does not read, with
no case events, so the views carry messages only.
"""

from datetime import UTC, datetime
from typing import Protocol

import pytest

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.models.message import SimulationMessage
from glossogen.scenarios.container_yard_stacking.evaluation import (
    build_communication_rounds as container_yard_stacking,
)
from glossogen.scenarios.drive_module_repair.evaluation import (
    build_communication_rounds as drive_module_repair,
)
from glossogen.scenarios.spot_the_difference.evaluation import (
    build_communication_rounds as spot_the_difference,
)
from glossogen.scenarios.spot_the_intersection.evaluation import (
    build_communication_rounds as spot_the_intersection,
)
from glossogen.scenarios.veyru.evaluation import build_communication_rounds as veyru

FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class RoundBuilder(Protocol):
    """A scenario's ``build_communication_rounds``."""

    def __call__(self, events: list[SimulationEvent]) -> list[CommunicationRoundView]:
        """Build the per-round views from a run's events."""
        ...


def build_message(*, round_number: int, channel_id: str, sender: str, text: str) -> MessageSent:
    """Build a MessageSent with the given transmitted text."""
    return MessageSent(
        timestamp=FIXED_TIME,
        round_number=round_number,
        token_count=len(text),
        message=SimulationMessage(
            message_id=f"{channel_id}-{round_number}-{sender}-{text}",
            channel_id=channel_id,
            sender_agent_id=sender,
            sender_display_name=sender,
            text=text,
            timestamp=FIXED_TIME,
            round_number=round_number,
        ),
    )


@pytest.mark.parametrize(
    ("builder", "first_channel", "second_channel"),
    [
        pytest.param(
            container_yard_stacking.build_communication_rounds,
            "link_a",
            "link_b",
            id="container_yard_stacking",
        ),
        pytest.param(
            drive_module_repair.build_communication_rounds, "bay", "bay", id="drive_module_repair"
        ),
        pytest.param(
            spot_the_difference.build_communication_rounds,
            "link",
            "link_b",
            id="spot_the_difference",
        ),
        pytest.param(
            spot_the_intersection.build_communication_rounds,
            "link_a",
            "link",
            id="spot_the_intersection",
        ),
        pytest.param(veyru.build_communication_rounds, "link", "link_a", id="veyru"),
    ],
)
def test_each_round_carries_its_channel_messages_in_log_order(
    builder: RoundBuilder, first_channel: str, second_channel: str
) -> None:
    """Off-channel messages are left out, and an empty message is kept as sent."""
    events: list[SimulationEvent] = [
        build_message(round_number=2, channel_id=first_channel, sender="alice", text="late"),
        build_message(round_number=1, channel_id=second_channel, sender="bob", text="hello"),
        build_message(round_number=1, channel_id="postmortem", sender="bob", text="debrief"),
        build_message(round_number=1, channel_id=first_channel, sender="alice", text=""),
    ]

    views = builder(events=events)

    assert [(view.round_number, view.messages) for view in views] == [
        (
            1,
            [
                CommunicationMessageLine(
                    sender_agent_id="bob", channel_id=second_channel, text="hello"
                ),
                CommunicationMessageLine(
                    sender_agent_id="alice", channel_id=first_channel, text=""
                ),
            ],
        ),
        (
            2,
            [
                CommunicationMessageLine(
                    sender_agent_id="alice", channel_id=first_channel, text="late"
                )
            ],
        ),
    ]
