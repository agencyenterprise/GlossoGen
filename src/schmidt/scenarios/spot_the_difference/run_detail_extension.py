"""spot_the_difference extension to the platform run-detail API.

Materializes per-round case ground truth (both scenes and the planted
differences) and per-tool-call submission verdicts (``submit_differences``)
keyed by tool ``call_id``. The frontend renders the case data as a panel at
the top of the round-timeline modal and the per-call verdicts inline
alongside each tool call in the chat timeline.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from schmidt.models.event import SimulationEvent, ToolResultReceived
from schmidt.scenarios.spot_the_difference.events import (
    DifferenceSubmissionJudged,
    SpotObject,
    SpotPlantedDifference,
    SpotTheDifferenceCaseStarted,
)
from schmidt.scenarios.spot_the_difference.ids import SUBMIT_DIFFERENCES_TOOL
from schmidt.server.runs.run_detail_types import AgentDetail, ChannelMessage
from schmidt.server.runs.scenario_extension import ScenarioRunDetailExtension, ScenarioRunExtrasBase


class SpotTheDifferenceCaseSummary(BaseModel):
    """Per-round case metadata used by the round-detail panel.

    Mirrors the ``SpotTheDifferenceCaseStarted`` event, repackaged as a stable
    DTO so the frontend never has to touch raw event JSON.
    """

    round_number: int
    case_number: int
    grid_size: int
    difference_count: int
    scene_a: list[SpotObject]
    scene_b: list[SpotObject]
    differences: list[SpotPlantedDifference]


class SpotSubmissionMetadata(BaseModel):
    """Verdict for a single ``submit_differences`` call attached by ``call_id``."""

    team_id: str
    submitted_items: list[str]
    matched_difference_indices: list[int]
    false_positive_count: int
    found_all: bool
    characters_at_submission: int
    explanation: str


class SpotTheDifferenceRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for spot_the_difference runs."""

    scenario_name: Literal["spot_the_difference"] = "spot_the_difference"
    cases: list[SpotTheDifferenceCaseSummary]
    submission_metadata_by_call_id: dict[str, SpotSubmissionMetadata]


def _build_case(event: SpotTheDifferenceCaseStarted) -> SpotTheDifferenceCaseSummary:
    return SpotTheDifferenceCaseSummary(
        round_number=event.round_number,
        case_number=event.case_number,
        grid_size=event.grid_size,
        difference_count=event.difference_count,
        scene_a=event.scene_a,
        scene_b=event.scene_b,
        differences=event.differences,
    )


def _build_cases(events: list[SimulationEvent]) -> list[SpotTheDifferenceCaseSummary]:
    cases: list[SpotTheDifferenceCaseSummary] = []
    for event in events:
        if not isinstance(event, SpotTheDifferenceCaseStarted):
            continue
        cases.append(_build_case(event=event))
    return cases


def _build_submission_metadata(judged: DifferenceSubmissionJudged) -> SpotSubmissionMetadata:
    return SpotSubmissionMetadata(
        team_id=judged.team_id,
        submitted_items=judged.submitted_items,
        matched_difference_indices=judged.matched_difference_indices,
        false_positive_count=judged.false_positive_count,
        found_all=judged.found_all,
        characters_at_submission=judged.characters_at_submission,
        explanation=judged.judge_explanation,
    )


def _build_call_id_map(events: list[SimulationEvent]) -> dict[str, SpotSubmissionMetadata]:
    """Pair each judge event to its tool-call ``call_id`` via FIFO per agent."""
    pending_by_agent: dict[str, list[SpotSubmissionMetadata]] = {}
    by_call_id: dict[str, SpotSubmissionMetadata] = {}
    for event in events:
        if isinstance(event, DifferenceSubmissionJudged):
            pending_by_agent.setdefault(event.agent_id, []).append(
                _build_submission_metadata(judged=event)
            )
        elif isinstance(event, ToolResultReceived) and event.tool_name == SUBMIT_DIFFERENCES_TOOL:
            queue = pending_by_agent.get(event.agent_id)
            if queue:
                by_call_id[event.call_id] = queue.pop(0)
    return by_call_id


class SpotTheDifferenceRunDetailExtension(ScenarioRunDetailExtension):
    """spot_the_difference hook into :class:`RunDetailResponse.scenario_extras`."""

    scenario_name: ClassVar[str] = "spot_the_difference"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = SpotTheDifferenceRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],  # noqa: ARG002 — protocol-required
        messages: list[ChannelMessage],  # noqa: ARG002 — protocol-required
    ) -> SpotTheDifferenceRunExtras:
        return SpotTheDifferenceRunExtras(
            cases=_build_cases(events=events),
            submission_metadata_by_call_id=_build_call_id_map(events=events),
        )
