"""spot_the_intersection's implementation of ``build_communication_rounds``.

Joins each round's link-channel messages with that round's
``SpotTheIntersectionRoundStarted`` event: every seat's board as its viewer read
it, the answer, and every object held by more than one board and fewer than all
(decoys, near-misses, and twin objects that some boards share), so a
communication judge can tell which moves narrowed the candidates.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationRoundView,
    round_views_with_case,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.spot_the_intersection.events import SpotTheIntersectionRoundStarted
from glossogen.scenarios.spot_the_intersection.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
)

_LINK_CHANNEL_IDS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the boards and answer."""
    return round_views_with_case(
        events=events,
        case_event_cls=SpotTheIntersectionRoundStarted,
        channel_ids=_LINK_CHANNEL_IDS,
        render_header=_header,
        render_ground_truth_block=_ground_truth,
        missing_case_header="(unknown)",
        missing_case_ground_truth_block="(no board data for this round)",
    )


def _header(round_started: SpotTheIntersectionRoundStarted) -> str:
    """One-line round anchor: team size and board size."""
    return f"{round_started.team_size} viewers · {round_started.board_size} objects per board"


def _ground_truth(round_started: SpotTheIntersectionRoundStarted) -> str:
    """Every board, the answer, and the objects held by some boards but not all."""
    sections: list[str] = []
    for index, lines in enumerate(round_started.boards, start=1):
        sections.append(f"VIEWER {index} sees:")
        sections.extend(f"- {line}" for line in lines)
        sections.append("")
    sections.append(f"ANSWER (on every board): {round_started.answer_line}")
    shared = [
        record
        for record in round_started.objects
        if 1 < len(record.seat_numbers) < round_started.team_size
    ]
    if shared:
        sections.append("ON SOME BOARDS BUT NOT ALL:")
        for record in shared:
            sections.append(
                f"- {record.color} {record.shape} at {record.cell} "
                f"(viewers {', '.join(str(number) for number in record.seat_numbers)})"
            )
    return "\n".join(sections)
