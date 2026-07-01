"""drive_module_repair extension to the platform run-detail API.

Surfaces per-round case ground truth (each unit's faults with the expected
component, tool, torque, and calibration) and the replacement-judge verdict
keyed by tool ``call_id``, so the round-timeline modal can show exactly what
was wrong, the expected fix, the action the technician sent, and the judge's
ruling.

The platform discovers this module at startup and wires
:class:`DriveModuleRepairRunExtras` into the discriminated-union
``scenario_extras`` field on :class:`RunDetailResponse`.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

from schmidt.models.event import SimulationEvent, ToolResultReceived
from schmidt.scenarios.drive_module_repair.events import (
    DriveModuleCaseStarted,
    DriveModuleReplacementJudged,
)
from schmidt.scenarios.drive_module_repair.ids import SERVICE_COMPONENT_TOOL
from schmidt.server.runs.run_detail_types import AgentDetail, ChannelMessage
from schmidt.server.runs.scenario_extension import ScenarioRunDetailExtension, ScenarioRunExtrasBase

# The field technician's action tool. ``service_component`` is the current name;
# ``replace_component`` is the name recorded in run logs created before the rename,
# so both are accepted when pairing judge verdicts to tool results.
ACTION_TOOL_NAMES = frozenset({SERVICE_COMPONENT_TOOL, "replace_component"})


class DriveModuleReplacementMetadata(BaseModel):
    """Judge context captured for a single ``service_component`` call.

    Attached to the corresponding tool-use entry so the frontend can show
    the expected replacement and the LLM judge's verdict alongside the call.
    """

    expected_actions: str
    judge_match: bool
    judge_explanation: str


class DriveModuleCaseStageDTO(BaseModel):
    """One ordered replacement stage: the unit, fault, and full expected procedure.

    ``steps`` is the ordered multi-step procedure; ``service_class``, ``tool``,
    ``torque_nm``, ``passes``, and ``calibration`` are the headline parameters.
    """

    step_index: int
    module_label: str
    component: str
    symptom: str
    service_class: str
    tool: str
    torque_nm: int
    passes: int
    calibration: str
    steps: list[str]
    judge_expected_action: str


class DriveModuleCaseSummary(BaseModel):
    """Per-round case metadata for the round-timeline modal.

    One entry per round, mirroring the ``DriveModuleCaseStarted`` event.
    ``stages`` is the full ground truth (every unit's faults concatenated in
    canonical order); each stage names its unit so the modal can group by it.
    """

    round_number: int
    case_number: int
    module_count: int
    replacement_count: int
    round_time_budget_seconds: int
    stages: list[DriveModuleCaseStageDTO]


class SSEDriveModuleReplacementJudged(BaseModel):
    """SSE event carrying the replacement judge's verdict for a service_component call.

    Mirrors the persisted :class:`DriveModuleReplacementJudged` field names,
    since the live stream emits the raw event dict under its ``event_type``.
    """

    event_type: Literal["drive_module_replacement_judged"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    step_index: int
    expected_action: str
    technician_action: str
    judge_match: bool
    judge_explanation: str


class DriveModuleRepairRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for drive_module_repair runs."""

    scenario_name: Literal["drive_module_repair"] = "drive_module_repair"
    cases: list[DriveModuleCaseSummary]
    replacement_metadata_by_call_id: dict[str, DriveModuleReplacementMetadata]


def _build_cases(events: list[SimulationEvent]) -> list[DriveModuleCaseSummary]:
    cases: list[DriveModuleCaseSummary] = []
    for event in events:
        if not isinstance(event, DriveModuleCaseStarted):
            continue
        cases.append(
            DriveModuleCaseSummary(
                round_number=event.round_number,
                case_number=event.case_number,
                module_count=event.module_count,
                replacement_count=event.replacement_count,
                round_time_budget_seconds=event.round_time_budget_seconds,
                stages=[
                    DriveModuleCaseStageDTO(
                        step_index=stage.step_index,
                        module_label=stage.module_label,
                        component=stage.component,
                        symptom=stage.symptom,
                        service_class=stage.service_class,
                        tool=stage.tool,
                        torque_nm=stage.torque_nm,
                        passes=stage.passes,
                        calibration=stage.calibration,
                        steps=stage.steps,
                        judge_expected_action=stage.judge_expected_action,
                    )
                    for stage in event.stages
                ],
            )
        )
    return cases


def _build_replacement_metadata_by_call_id(
    events: list[SimulationEvent],
) -> dict[str, DriveModuleReplacementMetadata]:
    """Pair each ``DriveModuleReplacementJudged`` with its ``service_component`` tool result.

    The judged events are emitted in the same FIFO order as the corresponding
    tool results, scoped per agent; walks both event types chronologically and
    pairs them by (agent_id, FIFO position).
    """
    pending_by_agent: dict[str, list[DriveModuleReplacementMetadata]] = {}
    metadata_by_call_id: dict[str, DriveModuleReplacementMetadata] = {}
    for event in events:
        if isinstance(event, DriveModuleReplacementJudged):
            pending_by_agent.setdefault(event.agent_id, []).append(
                DriveModuleReplacementMetadata(
                    expected_actions=event.expected_action,
                    judge_match=event.judge_match,
                    judge_explanation=event.judge_explanation,
                )
            )
        elif isinstance(event, ToolResultReceived):
            if event.tool_name not in ACTION_TOOL_NAMES:
                continue
            queue = pending_by_agent.get(event.agent_id)
            if not queue:
                continue
            metadata_by_call_id[event.call_id] = queue.pop(0)
    return metadata_by_call_id


class DriveModuleRepairRunDetailExtension(ScenarioRunDetailExtension):
    """drive_module_repair hook into :class:`RunDetailResponse.scenario_extras`."""

    scenario_name: ClassVar[str] = "drive_module_repair"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = DriveModuleRepairRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = (SSEDriveModuleReplacementJudged,)

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> DriveModuleRepairRunExtras:
        _ = agents_by_id, messages
        return DriveModuleRepairRunExtras(
            cases=_build_cases(events=events),
            replacement_metadata_by_call_id=_build_replacement_metadata_by_call_id(events=events),
        )
