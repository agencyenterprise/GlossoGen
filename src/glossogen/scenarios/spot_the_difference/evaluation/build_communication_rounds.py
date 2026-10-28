"""spot_the_difference's implementation of ``build_communication_rounds``.

Joins each round's link-channel messages with the ``SpotTheDifferenceCaseStarted``
event's scene pair and planted differences, rendering the per-round ground
truth into the ``CommunicationRoundView.ground_truth_block`` text the generic
communication-feature prompts consume. What each viewer saw (its own scene)
and the planted differences are rendered verbatim so the judge can decide
which protocol moves are sensible.
"""

import logging

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationRoundView,
    message_lines_by_round,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.spot_the_difference.events import SpotObject, SpotTheDifferenceCaseStarted
from glossogen.scenarios.spot_the_difference.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
)

_LINK_CHANNEL_IDS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})

logger = logging.getLogger(__name__)


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the scene-pair ground truth."""
    cases_by_round = _index_cases_by_round(events=events)
    messages_by_round = message_lines_by_round(events=events, channel_ids=_LINK_CHANNEL_IDS)
    all_rounds = sorted(set(cases_by_round.keys()) | set(messages_by_round.keys()))
    views: list[CommunicationRoundView] = []
    for round_number in all_rounds:
        case = cases_by_round.get(round_number)
        messages = messages_by_round.get(round_number, [])
        if case is None and not messages:
            continue
        views.append(
            CommunicationRoundView(
                round_number=round_number,
                header=_render_header(case=case),
                ground_truth_block=_render_ground_truth_block(case=case),
                messages=messages,
            )
        )
    return views


def _render_object(obj: SpotObject) -> str:
    """Render one scene object as ``<size> <color> <shape> in the <region>``."""
    return f"{obj.size} {obj.color} {obj.shape} in the {obj.region}"


def _render_header(case: SpotTheDifferenceCaseStarted | None) -> str:
    """One-line round anchor: object count and number of differences."""
    if case is None:
        return "(unknown)"
    return f"{len(case.scene_a)} objects · K={case.difference_count} differences"


def _render_ground_truth_block(case: SpotTheDifferenceCaseStarted | None) -> str:
    """Render both scenes and the planted differences as one text block."""
    if case is None:
        return "(no case data for this round)"
    sections: list[str] = []
    sections.append("LEFT VIEWER sees scene A:")
    for obj in sorted(case.scene_a, key=lambda o: (o.row, o.column)):
        sections.append(f"- {_render_object(obj=obj)}")
    sections.append("")
    sections.append("RIGHT VIEWER sees scene B:")
    for obj in sorted(case.scene_b, key=lambda o: (o.row, o.column)):
        sections.append(f"- {_render_object(obj=obj)}")
    sections.append("")
    sections.append(f"PLANTED DIFFERENCES (the {case.difference_count} to be found):")
    for index, diff in enumerate(case.differences, start=1):
        sections.append(f"  {index}. [{diff.kind}] {diff.description}")
    return "\n".join(sections)


def _index_cases_by_round(events: list[SimulationEvent]) -> dict[int, SpotTheDifferenceCaseStarted]:
    """Map round number -> the round's most recent case-started event."""
    cases: dict[int, SpotTheDifferenceCaseStarted] = {}
    for event in events:
        if isinstance(event, SpotTheDifferenceCaseStarted):
            cases[event.round_number] = event
    return cases
