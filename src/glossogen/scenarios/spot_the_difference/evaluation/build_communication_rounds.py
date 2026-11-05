"""spot_the_difference's implementation of ``build_communication_rounds``.

Joins each round's link-channel messages with the ``SpotTheDifferenceCaseStarted``
event's scene pair and planted differences, rendering the per-round ground
truth into the ``CommunicationRoundView.ground_truth_block`` text the generic
communication-feature prompts consume. What each viewer saw (its own scene)
and the planted differences are rendered verbatim so the judge can decide
which protocol moves are sensible.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationRoundView,
    round_views_with_case,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.spot_the_difference.events import SpotObject, SpotTheDifferenceCaseStarted
from glossogen.scenarios.spot_the_difference.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
)

_LINK_CHANNEL_IDS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the scene-pair ground truth."""
    return round_views_with_case(
        events=events,
        case_event_cls=SpotTheDifferenceCaseStarted,
        channel_ids=_LINK_CHANNEL_IDS,
        render_header=_render_header,
        render_ground_truth_block=_render_ground_truth_block,
        missing_case_header="(unknown)",
        missing_case_ground_truth_block="(no case data for this round)",
    )


def _render_object(obj: SpotObject) -> str:
    """Render one scene object as ``<size> <color> <shape> in the <region>``."""
    return f"{obj.size} {obj.color} {obj.shape} in the {obj.region}"


def _render_header(case: SpotTheDifferenceCaseStarted) -> str:
    """One-line round anchor: object count and number of differences."""
    return f"{len(case.scene_a)} objects · K={case.difference_count} differences"


def _render_ground_truth_block(case: SpotTheDifferenceCaseStarted) -> str:
    """Render both scenes and the planted differences as one text block."""
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
