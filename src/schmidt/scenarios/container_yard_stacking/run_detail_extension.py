"""Container-yard-stacking extension to the platform run-detail API.

Materializes per-round case ground truth (active stations, initial stack
layout, manifest, per-step expected trucks + crane plan) and per-tool-call
verdicts (move_truck, place_on_stack, lift_from_stack) keyed by tool
``call_id``. The frontend renders the case data as a panel at the top of
the round-timeline modal and the per-call verdicts inline alongside each
tool call in the chat timeline.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from schmidt.models.event import SimulationEvent, ToolResultReceived
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardCraneMoveJudged,
    ContainerYardCraneMoveStep,
    ContainerYardCraneMoveVerdict,
    ContainerYardCraneStation,
    ContainerYardManifestEntry,
    ContainerYardStackPosition,
    ContainerYardStackSnapshot,
    ContainerYardTruckAssignment,
    ContainerYardTruckCommitVerdict,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    LIFT_FROM_STACK_TOOL,
    MOVE_TRUCK_TOOL,
    PLACE_ON_STACK_TOOL,
)
from schmidt.server.runs.run_detail_types import AgentDetail, ChannelMessage
from schmidt.server.runs.scenario_extension import ScenarioRunDetailExtension, ScenarioRunExtrasBase


class ContainerYardCaseStepDTO(BaseModel):
    """Ground-truth plan for one delivery within a round."""

    step_index: int
    incoming_container_id: str
    target_position: ContainerYardStackPosition
    correct_crane_station: str
    truck_assignments: list[ContainerYardTruckAssignment]
    expected_move_sequence: list[ContainerYardCraneMoveStep]


class ContainerYardCaseSummary(BaseModel):
    """Per-round case metadata used by the round-detail panel.

    Mirrors the ``ContainerYardCaseStarted`` event one-for-one, repackaged
    as a stable DTO so the frontend never has to touch raw event JSON.
    """

    round_number: int
    case_number: int
    round_time_budget_seconds: int
    active_crane_stations: list[ContainerYardCraneStation]
    initial_stacks: list[ContainerYardStackSnapshot]
    manifest: list[ContainerYardManifestEntry]
    steps: list[ContainerYardCaseStepDTO]


class ContainerYardTruckMetadata(BaseModel):
    """Verdict for a single ``move_truck`` call attached by ``call_id``."""

    step_index: int
    submitted_truck_role: Literal["inbound", "outbound"]
    submitted_station_name: str
    submitted_pad: str
    submitted_container_id: str
    verdict: ContainerYardTruckCommitVerdict
    overall_success: bool
    explanation: str
    expected_truck_assignments: list[ContainerYardTruckAssignment]


class ContainerYardCraneMetadata(BaseModel):
    """Verdict for a single ``place_on_stack``/``lift_from_stack`` call.

    ``expected_move`` is the planner's expected next move at the time the
    call was made — useful for showing "expected vs submitted" inline.
    """

    step_index: int
    move_index: int
    submitted_move: ContainerYardCraneMoveStep
    verdict: ContainerYardCraneMoveVerdict
    accepted: bool
    explanation: str
    expected_move: ContainerYardCraneMoveStep | None


class ContainerYardRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for container-yard runs."""

    scenario_name: Literal["container_yard_stacking"] = "container_yard_stacking"
    cases: list[ContainerYardCaseSummary]
    truck_metadata_by_call_id: dict[str, ContainerYardTruckMetadata]
    crane_metadata_by_call_id: dict[str, ContainerYardCraneMetadata]


def _build_case(event: ContainerYardCaseStarted) -> ContainerYardCaseSummary:
    return ContainerYardCaseSummary(
        round_number=event.round_number,
        case_number=event.case_number,
        round_time_budget_seconds=event.round_time_budget_seconds,
        active_crane_stations=event.active_crane_stations,
        initial_stacks=event.initial_stacks,
        manifest=event.manifest,
        steps=[
            ContainerYardCaseStepDTO(
                step_index=step.step_index,
                incoming_container_id=step.incoming_container_id,
                target_position=step.target_position,
                correct_crane_station=step.correct_crane_station,
                truck_assignments=step.truck_assignments,
                expected_move_sequence=step.expected_move_sequence,
            )
            for step in event.steps
        ],
    )


def _build_cases(events: list[SimulationEvent]) -> list[ContainerYardCaseSummary]:
    cases: list[ContainerYardCaseSummary] = []
    for event in events:
        if not isinstance(event, ContainerYardCaseStarted):
            continue
        cases.append(_build_case(event=event))
    return cases


def _find_step(case: ContainerYardCaseSummary, step_index: int) -> ContainerYardCaseStepDTO | None:
    for step in case.steps:
        if step.step_index == step_index:
            return step
    return None


def _build_truck_metadata(
    judged: ContainerYardTruckJudged,
    case: ContainerYardCaseSummary | None,
) -> ContainerYardTruckMetadata:
    expected_assignments: list[ContainerYardTruckAssignment] = []
    if case is not None:
        step = _find_step(case=case, step_index=judged.step_index)
        if step is not None:
            expected_assignments = list(step.truck_assignments)
    return ContainerYardTruckMetadata(
        step_index=judged.step_index,
        submitted_truck_role=judged.submitted_truck_role,
        submitted_station_name=judged.submitted_station_name,
        submitted_pad=judged.submitted_pad,
        submitted_container_id=judged.submitted_container_id,
        verdict=judged.verdict,
        overall_success=judged.overall_success,
        explanation=judged.explanation,
        expected_truck_assignments=expected_assignments,
    )


def _build_crane_metadata(
    judged: ContainerYardCraneMoveJudged,
    case: ContainerYardCaseSummary | None,
) -> ContainerYardCraneMetadata:
    expected_move: ContainerYardCraneMoveStep | None = None
    if case is not None:
        step = _find_step(case=case, step_index=judged.step_index)
        if step is not None:
            for move in step.expected_move_sequence:
                if move.move_index == judged.move_index:
                    expected_move = move
                    break
    return ContainerYardCraneMetadata(
        step_index=judged.step_index,
        move_index=judged.move_index,
        submitted_move=judged.submitted_move,
        verdict=judged.verdict,
        accepted=judged.accepted,
        explanation=judged.explanation,
        expected_move=expected_move,
    )


def _build_call_id_maps(
    events: list[SimulationEvent],
    cases_by_round: dict[int, ContainerYardCaseSummary],
) -> tuple[dict[str, ContainerYardTruckMetadata], dict[str, ContainerYardCraneMetadata]]:
    """Pair each judge event to its tool-call ``call_id`` via FIFO per agent.

    The world emits judged events synchronously while handling each tool
    call, so the chronological order of judged events for a given agent
    matches the chronological order of that agent's tool results.
    """
    pending_truck_by_agent: dict[str, list[ContainerYardTruckMetadata]] = {}
    pending_crane_by_agent: dict[str, list[ContainerYardCraneMetadata]] = {}
    truck_by_call_id: dict[str, ContainerYardTruckMetadata] = {}
    crane_by_call_id: dict[str, ContainerYardCraneMetadata] = {}
    for event in events:
        if isinstance(event, ContainerYardTruckJudged):
            case = cases_by_round.get(event.round_number)
            pending_truck_by_agent.setdefault(event.agent_id, []).append(
                _build_truck_metadata(judged=event, case=case)
            )
        elif isinstance(event, ContainerYardCraneMoveJudged):
            case = cases_by_round.get(event.round_number)
            pending_crane_by_agent.setdefault(event.agent_id, []).append(
                _build_crane_metadata(judged=event, case=case)
            )
        elif isinstance(event, ToolResultReceived):
            if event.tool_name == MOVE_TRUCK_TOOL:
                truck_queue = pending_truck_by_agent.get(event.agent_id)
                if truck_queue:
                    truck_by_call_id[event.call_id] = truck_queue.pop(0)
            elif event.tool_name in (PLACE_ON_STACK_TOOL, LIFT_FROM_STACK_TOOL):
                crane_queue = pending_crane_by_agent.get(event.agent_id)
                if crane_queue:
                    crane_by_call_id[event.call_id] = crane_queue.pop(0)
    return truck_by_call_id, crane_by_call_id


class ContainerYardRunDetailExtension(ScenarioRunDetailExtension):
    """Container-yard hook into :class:`RunDetailResponse.scenario_extras`."""

    scenario_name: ClassVar[str] = "container_yard_stacking"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = ContainerYardRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> ContainerYardRunExtras:
        cases = _build_cases(events=events)
        cases_by_round = {case.round_number: case for case in cases}
        truck_map, crane_map = _build_call_id_maps(events=events, cases_by_round=cases_by_round)
        return ContainerYardRunExtras(
            cases=cases,
            truck_metadata_by_call_id=truck_map,
            crane_metadata_by_call_id=crane_map,
        )
