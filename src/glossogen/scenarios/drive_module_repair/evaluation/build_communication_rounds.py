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

from glossogen.evaluation.metrics.communication.round_view import round_views_with_case
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.communication_round_view import CommunicationRoundView
from glossogen.scenarios.drive_module_repair.events import DriveModuleCaseStarted
from glossogen.scenarios.drive_module_repair.ids import BAY_CHANNEL_ID

_BAY_CHANNEL_IDS = frozenset({BAY_CHANNEL_ID})


def build_communication_rounds(events: list[SimulationEvent]) -> list[CommunicationRoundView]:
    """Group bay-channel messages by round and attach the per-fault ground truth.

    Rounds with a ``DriveModuleCaseStarted`` event are emitted even when no bay
    messages were sent (a silent round is signal too). Rounds with neither case
    data nor messages are skipped.
    """
    return round_views_with_case(
        events=events,
        case_event_cls=DriveModuleCaseStarted,
        channel_ids=_BAY_CHANNEL_IDS,
        render_header=_render_header,
        render_ground_truth_block=_render_ground_truth_block,
        missing_case_header="(unknown case)",
        missing_case_ground_truth_block="(no case data for this round)",
    )


def _render_header(case: DriveModuleCaseStarted) -> str:
    """One-line round anchor: case number plus unit / fault counts."""
    units = case.module_count
    faults = case.replacement_count
    return (
        f"case {case.case_number}: {units} unit{'' if units == 1 else 's'}, "
        f"{faults} fault{'' if faults == 1 else 's'}"
    )


def _render_ground_truth_block(case: DriveModuleCaseStarted) -> str:
    """Render the three-agent asymmetry for one round into a single text block."""
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
