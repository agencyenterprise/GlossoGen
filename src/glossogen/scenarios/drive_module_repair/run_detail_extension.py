"""drive_module_repair extension to the platform run-detail API.

Surfaces per-round case ground truth (each unit's faults with the expected
component, tool, torque, and calibration) and the replacement-judge verdict
keyed by tool ``call_id``, so the round-timeline modal can show exactly what
was wrong, the expected fix, the action the technician sent, and the judge's
ruling.

``DriveModuleRepairScenario.run_detail_extension`` returns the extension, and the server wires
:class:`DriveModuleRepairRunExtras` into the discriminated-union
``scenario_extras`` field on :class:`RunDetailResponse`.
"""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import (
    AgentDetail,
    ChannelMessage,
    JudgeGroundTruthMetadata,
)
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
    mirror_events,
    pair_with_tool_calls,
)
from glossogen.scenarios.drive_module_repair.events import (
    DriveModuleCaseStarted,
    DriveModuleReplacementJudged,
)
from glossogen.scenarios.drive_module_repair.ids import SERVICE_COMPONENT_TOOL

# The field technician's action tool. ``service_component`` is the current name;
# ``replace_component`` is the name recorded in run logs created before the rename,
# so both are accepted when pairing judge verdicts to tool results.
ACTION_TOOL_NAMES = frozenset({SERVICE_COMPONENT_TOOL, "replace_component"})


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
    judge_ground_truth_by_call_id: dict[str, JudgeGroundTruthMetadata]


def _ground_truth(judged: DriveModuleReplacementJudged) -> JudgeGroundTruthMetadata:
    """The platform-wide judge ground-truth shape for one ``service_component`` verdict."""
    return JudgeGroundTruthMetadata(
        expected_actions=judged.expected_action,
        judge_match=judged.judge_match,
        judge_explanation=judged.judge_explanation,
    )


class DriveModuleRepairRunDetailExtension(ScenarioRunDetailExtension):
    """drive_module_repair hook into :class:`RunDetailResponse.scenario_extras`."""

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
            cases=mirror_events(
                events=events, event_cls=DriveModuleCaseStarted, mirror_cls=DriveModuleCaseSummary
            ),
            judge_ground_truth_by_call_id=pair_with_tool_calls(
                events=events,
                judged_event_cls=DriveModuleReplacementJudged,
                tool_names=ACTION_TOOL_NAMES,
                build_payload=_ground_truth,
            ),
        )
