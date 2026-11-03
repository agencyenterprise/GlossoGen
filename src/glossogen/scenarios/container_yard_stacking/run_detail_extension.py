"""Container-yard-stacking extension to the platform run-detail API.

Materializes per-round case ground truth (the occupancy row and the batch
assignment of each container's intake slot → target bay) and per-tool-call
verdicts (``move_container``) keyed by tool ``call_id``. The frontend renders
the case data as a panel at the top of the round-timeline modal and the
per-call verdicts inline alongside each tool call in the chat timeline.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
    pair_with_tool_calls,
)
from glossogen.scenarios.container_yard_stacking.events import (
    ContainerYardBatchItem,
    ContainerYardCaseStarted,
    ContainerYardMoveJudged,
    ContainerYardMoveVerdict,
    ContainerYardSlot,
)
from glossogen.scenarios.container_yard_stacking.ids import MOVE_CONTAINER_TOOL


class ContainerYardCaseSummary(BaseModel):
    """Per-round case metadata used by the round-detail panel.

    Mirrors the ``ContainerYardCaseStarted`` event, repackaged as a stable
    DTO so the frontend never has to touch raw event JSON.
    """

    round_number: int
    case_number: int
    round_time_budget_seconds: int
    yard_slot_count: int
    initial_row: list[ContainerYardSlot]
    batch: list[ContainerYardBatchItem]


class ContainerYardMoveMetadata(BaseModel):
    """Verdict for a single ``move_container`` call attached by ``call_id``.

    ``expected_from_slot`` / ``expected_to_slot`` are the batch container's
    ground-truth intake slot and target bay for the step the move targeted,
    useful for showing "expected vs submitted" inline.
    """

    step_index: int
    submitted_from_slot: int
    submitted_to_slot: int
    verdict: ContainerYardMoveVerdict
    accepted: bool
    soft_rejected: bool
    explanation: str
    expected_from_slot: int | None
    expected_to_slot: int | None


class ContainerYardRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for container-yard runs."""

    scenario_name: Literal["container_yard_stacking"] = "container_yard_stacking"
    cases: list[ContainerYardCaseSummary]
    move_metadata_by_call_id: dict[str, ContainerYardMoveMetadata]


def _build_case(event: ContainerYardCaseStarted) -> ContainerYardCaseSummary:
    return ContainerYardCaseSummary(
        round_number=event.round_number,
        case_number=event.case_number,
        round_time_budget_seconds=event.round_time_budget_seconds,
        yard_slot_count=event.yard_slot_count,
        initial_row=event.initial_row,
        batch=event.batch,
    )


def _build_cases(events: list[SimulationEvent]) -> list[ContainerYardCaseSummary]:
    cases: list[ContainerYardCaseSummary] = []
    for event in events:
        if not isinstance(event, ContainerYardCaseStarted):
            continue
        cases.append(_build_case(event=event))
    return cases


def _find_item(case: ContainerYardCaseSummary, step_index: int) -> ContainerYardBatchItem | None:
    if 1 <= step_index <= len(case.batch):
        return case.batch[step_index - 1]
    return None


def _build_move_metadata(
    judged: ContainerYardMoveJudged,
    case: ContainerYardCaseSummary | None,
) -> ContainerYardMoveMetadata:
    expected_from_slot: int | None = None
    expected_to_slot: int | None = None
    if case is not None:
        item = _find_item(case=case, step_index=judged.step_index)
        if item is not None:
            expected_from_slot = item.intake_slot
            expected_to_slot = item.target_slot
    return ContainerYardMoveMetadata(
        step_index=judged.step_index,
        submitted_from_slot=judged.submitted_from_slot,
        submitted_to_slot=judged.submitted_to_slot,
        verdict=judged.verdict,
        accepted=judged.accepted,
        soft_rejected=judged.soft_rejected,
        explanation=judged.explanation,
        expected_from_slot=expected_from_slot,
        expected_to_slot=expected_to_slot,
    )


class ContainerYardRunDetailExtension(ScenarioRunDetailExtension):
    """Container-yard hook into :class:`RunDetailResponse.scenario_extras`."""

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
        return ContainerYardRunExtras(
            cases=cases,
            move_metadata_by_call_id=pair_with_tool_calls(
                events=events,
                judged_event_cls=ContainerYardMoveJudged,
                tool_names=frozenset({MOVE_CONTAINER_TOOL}),
                build_payload=lambda judged: _build_move_metadata(
                    judged=judged, case=cases_by_round.get(judged.round_number)
                ),
            ),
        )
