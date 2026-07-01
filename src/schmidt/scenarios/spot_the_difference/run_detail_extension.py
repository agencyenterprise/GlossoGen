"""spot_the_difference extension to the platform run-detail API.

Materializes everything the round-detail panel needs from ``scenario_extras``
alone: per-round case ground truth (both scenes and the planted differences),
each team's ``submit_differences`` verdict (keyed by tool ``call_id`` and
carrying its round), and the per-round-per-team outcome (success + reason).
The frontend panel shows, per round, what differs between the two scenes, what
each team submitted, and why each team passed or failed.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from schmidt.models.event import RoundResultRecorded, SimulationEvent, ToolResultReceived
from schmidt.scenarios.spot_the_difference.events import (
    DifferenceSubmissionJudged,
    SpotObject,
    SpotPlantedDifference,
    SpotTheDifferenceCaseStarted,
)
from schmidt.scenarios.spot_the_difference.ids import (
    SUBMISSION_RECORDED_MARKER,
    SUBMISSION_WAITING_MARKER,
    SUBMIT_DIFFERENCES_TOOL,
)
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

    round_number: int
    team_id: str
    submitted_items: list[str]
    matched_difference_indices: list[int]
    false_positive_count: int
    found_all: bool
    characters_at_submission: int
    explanation: str


class SpotTeamRoundResult(BaseModel):
    """One team's outcome for one round (the correctness-gate + win/loss verdict).

    ``team_id`` is ``null`` in single-team mode. ``reason`` is the human-readable
    explanation written by ``judge_round_result`` (e.g. ``won — found 3/3, 465
    chars`` / ``did not submit (found 0/3, 576 chars)``).
    """

    round_number: int
    team_id: str | None
    success: bool
    reason: str


class SpotTheDifferenceRunExtras(ScenarioRunExtrasBase):
    """Scenario-specific run-detail payload surfaced for spot_the_difference runs."""

    scenario_name: Literal["spot_the_difference"] = "spot_the_difference"
    cases: list[SpotTheDifferenceCaseSummary]
    submission_metadata_by_call_id: dict[str, SpotSubmissionMetadata]
    team_results: list[SpotTeamRoundResult]


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
        round_number=judged.round_number,
        team_id=judged.team_id,
        submitted_items=judged.submitted_items,
        matched_difference_indices=judged.matched_difference_indices,
        false_positive_count=judged.false_positive_count,
        found_all=judged.found_all,
        characters_at_submission=judged.characters_at_submission,
        explanation=judged.judge_explanation,
    )


def _build_team_results(events: list[SimulationEvent]) -> list[SpotTeamRoundResult]:
    """Materialize each ``RoundResultRecorded`` event as a per-team round outcome."""
    results: list[SpotTeamRoundResult] = []
    for event in events:
        if not isinstance(event, RoundResultRecorded):
            continue
        results.append(
            SpotTeamRoundResult(
                round_number=event.round_number,
                team_id=event.team_id,
                success=event.success,
                reason=event.reason,
            )
        )
    return results


def _build_call_id_map(events: list[SimulationEvent]) -> dict[str, SpotSubmissionMetadata]:
    """Pair each judge verdict to its ``submit_differences`` tool-call ``call_id``.

    Keyed by ``(agent_id, round_number)``: an agent submits at most once per
    round (later submits are rejected) and is judged at most once per round,
    both in the same round — so the mapping is exact. A plain FIFO would
    mis-pair here because under ``all_must_submit`` the first member's verdict
    is logged only when the team locks (on the second member's call), i.e.
    after that member's own tool result. Only accepted submit calls (recorded
    or waiting-for-partner) are paired; rejected calls carry no verdict.
    """
    verdict_by_agent_round: dict[tuple[str, int], SpotSubmissionMetadata] = {}
    for event in events:
        if isinstance(event, DifferenceSubmissionJudged):
            verdict_by_agent_round[(event.agent_id, event.round_number)] = (
                _build_submission_metadata(judged=event)
            )
    by_call_id: dict[str, SpotSubmissionMetadata] = {}
    for event in events:
        if not isinstance(event, ToolResultReceived) or event.tool_name != SUBMIT_DIFFERENCES_TOOL:
            continue
        if not (
            event.result.startswith(SUBMISSION_RECORDED_MARKER)
            or event.result.startswith(SUBMISSION_WAITING_MARKER)
        ):
            continue
        verdict = verdict_by_agent_round.get((event.agent_id, event.round_number))
        if verdict is not None:
            by_call_id[event.call_id] = verdict
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
            team_results=_build_team_results(events=events),
        )
