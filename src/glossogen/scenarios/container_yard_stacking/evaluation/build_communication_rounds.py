"""Container-yard's implementation of ``SimulationScenario.build_communication_rounds``.

Joins each round's link-channel messages with the ``ContainerYardCaseStarted``
event's batch assignment and renders the per-round ground truth into the
``CommunicationRoundView.ground_truth_block`` text the generic
communication-feature prompts consume.

The three-agent information asymmetry is rendered verbatim (what each agent
saw at round start), so the judge can decide which protocol moves are
sensible for each agent.
"""

from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationRoundView,
    round_views_with_case,
)
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardContainer,
)
from glossogen.scenarios.container_yard_stacking.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
)

_LINK_CHANNEL_IDS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the yard case ground truth."""
    return round_views_with_case(
        events=events,
        case_event_cls=ContainerYardCaseStarted,
        channel_ids=_LINK_CHANNEL_IDS,
        render_header=_render_header,
        render_ground_truth_block=_render_ground_truth_block,
        missing_case_header="(unknown)",
        missing_case_ground_truth_block="(no case data for this round)",
    )


def _container_text(container: ContainerYardContainer) -> str:
    """Render an event container's bundle as a comma-joined value list."""
    return ", ".join(attribute.value for attribute in container.attributes)


def _render_header(case: ContainerYardCaseStarted) -> str:
    """One-line row anchor for each round (batch size + per-item intake→target)."""
    moves = " | ".join(f"{item.intake_slot}->{item.target_slot}" for item in case.batch)
    return f"{len(case.batch)} container(s) · {moves}"


def _render_ground_truth_block(case: ContainerYardCaseStarted) -> str:
    """Render the spotter / planner / crane asymmetry as one text block."""
    sections: list[str] = []
    sections.append("YARD SPOTTER sees (each container's attributes @ its intake slot):")
    for item in sorted(case.batch, key=lambda i: i.intake_slot):
        sections.append(f"- {_container_text(container=item.container)} @ slot {item.intake_slot}")
    sections.append("")
    sections.append("LOGISTICS PLANNER sees (each container's attributes -> its target bay):")
    for item in sorted(case.batch, key=lambda i: i.target_slot):
        sections.append(f"- {_container_text(container=item.container)} -> bay {item.target_slot}")
    sections.append("")
    sections.append("CRANE OPERATOR sees only occupancy (blind to attributes):")
    occupied = sorted(slot.slot for slot in case.initial_row if slot.container is not None)
    empty = sorted(slot.slot for slot in case.initial_row if slot.container is None)
    sections.append(f"- occupied slots: {occupied}")
    sections.append(f"- empty slots: {empty}")
    sections.append("")
    sections.append("Per-container ground truth (intake slot -> target bay):")
    for item in case.batch:
        sections.append(
            f"  {_container_text(container=item.container)}: "
            f"slot {item.intake_slot} -> bay {item.target_slot}"
        )
    return "\n".join(sections)
