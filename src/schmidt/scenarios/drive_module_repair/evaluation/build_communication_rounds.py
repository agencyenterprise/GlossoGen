"""drive_module_repair's implementation of ``SimulationScenario.build_communication_rounds``.

Joins each round's bay-channel messages with the ``DriveModuleCaseStarted``
event's per-fault ground truth and renders the three-agent information
asymmetry into the ``CommunicationRoundView.ground_truth_block`` text the
generic communication-feature prompts consume.

The technician sees only raw panel symptoms (revealed one at a time, tagged by
unit); the diagnostics engineer holds the symptom -> component mapping; the spec
engineer holds the full multi-step replacement procedure. The block renders
each fault's symptom, component, and the procedure to relay, so the judge can
decide which protocol moves are sensible for each agent.
"""

import logging

from schmidt.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenarios.drive_module_repair.events import DriveModuleCaseStarted
from schmidt.scenarios.drive_module_repair.ids import BAY_CHANNEL_ID

logger = logging.getLogger(__name__)


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group bay-channel messages by round and attach the per-fault ground truth.

    Rounds with a ``DriveModuleCaseStarted`` event are emitted even when no bay
    messages were sent (a silent round is signal too). Rounds with neither case
    data nor messages are skipped.
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


def _render_header(case: DriveModuleCaseStarted | None) -> str:
    """One-line round anchor: case number plus unit / fault counts."""
    if case is None:
        return "(unknown case)"
    units = case.module_count
    faults = case.replacement_count
    return (
        f"case {case.case_number}: {units} unit{'' if units == 1 else 's'}, "
        f"{faults} fault{'' if faults == 1 else 's'}"
    )


def _render_ground_truth_block(case: DriveModuleCaseStarted | None) -> str:
    """Render the three-agent asymmetry for one round into a single text block."""
    if case is None:
        return "(no case data for this round)"
    technician_lines = [f"- {stage.module_label}: {stage.symptom}" for stage in case.stages]
    engineer_lines = [
        (
            f'- {stage.module_label} / "{stage.symptom}" -> {stage.component}; '
            f"procedure to relay: {stage.judge_expected_action}"
        )
        for stage in case.stages
    ]
    sections: list[str] = [
        "TECHNICIAN sees (raw panel symptoms, revealed one at a time, tagged by unit):"
    ]
    sections.extend(technician_lines if technician_lines else ["(no fault data)"])
    sections.append("")
    sections.append(
        "ENGINEERS hold the mapping + procedure (diagnostics: symptom -> component; "
        "spec: the full procedure):"
    )
    sections.extend(engineer_lines if engineer_lines else ["(no fault data)"])
    return "\n".join(sections)


def _index_cases_by_round(events: list[SimulationEvent]) -> dict[int, DriveModuleCaseStarted]:
    """Map round number -> the round's ``DriveModuleCaseStarted`` event."""
    cases: dict[int, DriveModuleCaseStarted] = {}
    for event in events:
        if isinstance(event, DriveModuleCaseStarted):
            cases[event.round_number] = event
    return cases


def _index_messages_by_round(
    events: list[SimulationEvent],
) -> dict[int, list[CommunicationMessageLine]]:
    """Map round number -> ordered list of bay-channel messages."""
    by_round: dict[int, list[CommunicationMessageLine]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id != BAY_CHANNEL_ID:
            continue
        by_round.setdefault(event.round_number, []).append(
            CommunicationMessageLine(
                sender_agent_id=event.message.sender_agent_id,
                channel_id=event.message.channel_id,
                text=event.message.text,
            )
        )
    return by_round
