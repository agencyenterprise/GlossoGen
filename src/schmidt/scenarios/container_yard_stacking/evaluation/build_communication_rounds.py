"""Container-yard's implementation of ``SimulationScenario.build_communication_rounds``.

Joins each round's link-channel messages with the ``ContainerYardCaseStarted``
event's batch assignment and renders the per-round ground truth into the
``CommunicationRoundView.ground_truth_block`` text the generic
communication-feature prompts consume.

The three-agent information asymmetry is rendered verbatim (what each agent
saw at round start), so the judge can decide which protocol moves are
sensible for each agent.
"""

import logging

from schmidt.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardContainer,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
)

_LINK_CHANNEL_IDS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})

logger = logging.getLogger(__name__)


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the yard case ground truth."""
    cases_by_round = _index_cases_by_round(events=events)
    messages_by_round = _index_messages_by_round(events=events)
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


def _container_text(container: ContainerYardContainer) -> str:
    """Render an event container's bundle as a comma-joined value list."""
    return ", ".join(attribute.value for attribute in container.attributes)


def _render_header(case: ContainerYardCaseStarted | None) -> str:
    """One-line row anchor for each round (batch size + per-item intake→target)."""
    if case is None:
        return "(unknown)"
    moves = " | ".join(f"{item.intake_slot}->{item.target_slot}" for item in case.batch)
    return f"{len(case.batch)} container(s) · {moves}"


def _render_ground_truth_block(case: ContainerYardCaseStarted | None) -> str:
    """Render the spotter / planner / crane asymmetry as one text block."""
    if case is None:
        return "(no case data for this round)"
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


def _index_cases_by_round(events: list[SimulationEvent]) -> dict[int, ContainerYardCaseStarted]:
    """Map round number → the round's most recent ``ContainerYardCaseStarted`` event."""
    cases: dict[int, ContainerYardCaseStarted] = {}
    for event in events:
        if isinstance(event, ContainerYardCaseStarted):
            cases[event.round_number] = event
    return cases


def _index_messages_by_round(
    events: list[SimulationEvent],
) -> dict[int, list[CommunicationMessageLine]]:
    """Map round number → ordered list of link-channel messages."""
    by_round: dict[int, list[CommunicationMessageLine]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in _LINK_CHANNEL_IDS:
            continue
        by_round.setdefault(event.round_number, []).append(
            CommunicationMessageLine(
                sender_agent_id=event.message.sender_agent_id,
                channel_id=event.message.channel_id,
                text=event.message.text,
            )
        )
    return by_round
