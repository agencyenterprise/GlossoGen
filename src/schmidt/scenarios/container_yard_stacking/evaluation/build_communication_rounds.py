"""Container-yard's implementation of ``SimulationScenario.build_communication_rounds``.

Joins each round's link-channel messages with the
``ContainerYardCaseStarted`` event's case data and renders the
per-round ground truth into the
``CommunicationRoundView.ground_truth_block`` text the generic
communication-feature prompts consume.

The yard's three-agent information asymmetry is rendered verbatim
into the block (what each agent saw at round start), so the judge can
decide which protocol moves are sensible for each agent.
"""

import logging

from schmidt.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardCraneMoveStep,
    ContainerYardCraneStation,
    ContainerYardStackPosition,
    ContainerYardStackSnapshot,
    ContainerYardTruckAssignment,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
)

_LINK_CHANNEL_IDS = frozenset({LINK_CHANNEL_ID, LINK_A_CHANNEL_ID, LINK_B_CHANNEL_ID})

logger = logging.getLogger(__name__)


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group link-channel messages by round and attach the yard case ground truth.

    Rounds that have no link messages are still emitted as long as
    they have a ``ContainerYardCaseStarted`` event (silent rounds are
    signal too). Rounds with neither are skipped.
    """
    cases_by_round = _index_cases_by_round(events=events)
    messages_by_round = _index_messages_by_round(events=events)
    all_rounds = sorted(set(cases_by_round.keys()) | set(messages_by_round.keys()))
    views: list[CommunicationRoundView] = []
    for round_number in all_rounds:
        case = cases_by_round.get(round_number)
        messages = messages_by_round.get(round_number, [])
        if case is None and not messages:
            continue
        header = _render_header(case=case)
        ground_truth_block = _render_ground_truth_block(case=case)
        views.append(
            CommunicationRoundView(
                round_number=round_number,
                header=header,
                ground_truth_block=ground_truth_block,
                messages=messages,
            )
        )
    return views


def _render_header(case: ContainerYardCaseStarted | None) -> str:
    """One-line row anchor for each round (step count + target slots)."""
    if case is None:
        return "(unknown)"
    targets = " | ".join(
        f"step{step.step_index}→Stack {step.target_position.stack} Tier {step.target_position.tier}"
        for step in case.steps
    )
    return f"{len(case.steps)} container(s) · {targets}"


def _render_ground_truth_block(case: ContainerYardCaseStarted | None) -> str:
    """Render the yard operator / planner / crane asymmetry as one text block."""
    if case is None:
        return "(no case data for this round)"
    sections: list[str] = []
    sections.append(
        "YARD OPERATOR sees (one incoming container ID at a time, revealed step by step):"
    )
    for step in case.steps:
        sections.append(f"- step {step.step_index}: {step.incoming_container_id}")
    sections.append("")
    sections.append("LOGISTICS PLANNER sees (yard map + shift manifest + per-step targets):")
    sections.append(
        "- active crane stations: "
        + "; ".join(_render_station(station=station) for station in case.active_crane_stations)
    )
    sections.append("- current stack layout (round start):")
    sections.extend(f"    {_render_stack_snapshot(stack=stack)}" for stack in case.initial_stacks)
    sections.append("- per-step ground truth:")
    for step in case.steps:
        sections.append(
            f"    step {step.step_index}: target {_render_stack_position(step.target_position)} "
            f"via {step.correct_crane_station}"
        )
    sections.append(
        "- shift manifest (id → target slot; the real entries map one-to-one to active steps):"
    )
    sections.extend(
        f"    {entry.container_id} → {_render_stack_position(entry.target_position)}"
        for entry in case.manifest
    )
    sections.append("")
    sections.append("CRANE OPERATOR sees: nothing case-specific (relies on planner relay).")
    sections.append("")
    sections.append("Expected per step:")
    for step in case.steps:
        sections.append(
            f"  step {step.step_index} trucks: "
            + ", ".join(
                _render_truck_assignment(assignment=assignment)
                for assignment in step.truck_assignments
            )
        )
        sections.append(f"  step {step.step_index} crane plan:")
        sections.extend(
            f"    {_render_crane_step(step=move)}" for move in step.expected_move_sequence
        )
    return "\n".join(sections)


def _render_station(station: ContainerYardCraneStation) -> str:
    """Render one active crane station as a compact text fragment."""
    pads = ", ".join(station.pads)
    reachable = ", ".join(str(s) for s in station.reachable_stacks)
    return f"{station.station_name} (pads: {pads}; reachable stacks: {reachable})"


def _render_stack_snapshot(stack: ContainerYardStackSnapshot) -> str:
    """Render one stack's bottom-to-top contents."""
    if not stack.containers_bottom_to_top:
        return f"Stack {stack.stack}: empty"
    tiers = ", ".join(
        f"Tier {idx} = {cid}" for idx, cid in enumerate(stack.containers_bottom_to_top, start=1)
    )
    return f"Stack {stack.stack}: {tiers}"


def _render_stack_position(position: ContainerYardStackPosition) -> str:
    """Render a stack position as ``Stack S Tier T``."""
    return f"Stack {position.stack} Tier {position.tier}"


def _render_truck_assignment(assignment: ContainerYardTruckAssignment) -> str:
    """Render one truck assignment as ``inbound truck → <station> carrying <id>``."""
    if assignment.container_id == "":
        carries = "empty"
    else:
        carries = assignment.container_id
    return f"{assignment.truck_role} truck → {assignment.station_name} (carries: {carries})"


def _render_crane_step(step: ContainerYardCraneMoveStep) -> str:
    """Render one crane plan step as ``<id>: <source> → <destination>``."""
    source = _render_endpoint(
        kind=step.source_kind,
        stack=step.source_stack,
        tier=step.source_tier,
    )
    destination = _render_endpoint(
        kind=step.destination_kind,
        stack=step.destination_stack,
        tier=step.destination_tier,
    )
    return f"move {step.move_index}: {step.container_id} from {source} to {destination}"


def _render_endpoint(kind: str, stack: int | None, tier: int | None) -> str:
    """Render a crane endpoint (``inbound_truck`` / ``outbound_truck`` / ``stack_tier``)."""
    if kind == "stack_tier":
        return f"Stack {stack} Tier {tier}"
    return kind


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
