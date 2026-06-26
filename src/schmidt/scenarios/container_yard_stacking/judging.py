"""Deterministic ``move_container`` judging for the yard world.

A move names a source slot and a destination slot. The verdict is
deterministic: a structurally impossible move (source empty, destination
occupied, slot out of range) is a soft reject the operator can retry; a
structurally valid move that names the wrong source container or the wrong
target bay fails the round; a correct move relocates the container and
reports the placement. The whole batch is visible at round start, so moves
are unordered and there is no per-step reveal.
"""

from typing import NamedTuple

from schmidt.runtime.scenario_world import WorldContext
from schmidt.scenarios.container_yard_stacking.case_rendering import render_container
from schmidt.scenarios.container_yard_stacking.events import ContainerYardMoveVerdict
from schmidt.scenarios.container_yard_stacking.ids import (
    CONTAINER_PLACED_MARKER,
    MOVE_REJECTED_MARKER,
    MOVE_SUCCESS_MARKER,
)
from schmidt.scenarios.container_yard_stacking.world_state import MoveResult, StepOutcome, TeamState
from schmidt.scenarios.container_yard_stacking.yard_cases import CaseStep, YardCase


class MoveJudgement(NamedTuple):
    """Everything the tool layer needs to report and log one move."""

    result: MoveResult
    verdict: ContainerYardMoveVerdict
    step_index: int
    marker: str
    explanation: str


def last_failure_reason(team: TeamState) -> str:
    """Return the team's most recent failure reason for this round."""
    if team.failure_reason == "":
        return "Move rejected."
    return team.failure_reason


def _step_for_intake_slot(case: YardCase, slot: int) -> CaseStep | None:
    """Return the batch step whose intake slot is ``slot``, if any."""
    for step in case.steps:
        if step.intake_slot == slot:
            return step
    return None


async def record_move(
    team: TeamState,
    case: YardCase,
    context: WorldContext,
    submitted_from_slot: int,
    submitted_to_slot: int,
) -> MoveJudgement:
    """Apply or reject one ``move_container`` call for ``team``."""
    yard_slot_count = case.yard_slot_count
    from_in_range = 1 <= submitted_from_slot <= yard_slot_count
    to_in_range = 1 <= submitted_to_slot <= yard_slot_count
    from_container = team.current_row.get(submitted_from_slot) if from_in_range else None
    to_container = team.current_row.get(submitted_to_slot) if to_in_range else None
    from_occupied = from_container is not None
    to_empty = to_in_range and to_container is None
    step = _step_for_intake_slot(case=case, slot=submitted_from_slot) if from_in_range else None
    from_correct = (
        step is not None and from_container is not None and from_container == step.container
    )
    to_correct = step is not None and submitted_to_slot == step.target_slot
    step_index = 0 if step is None else step.step_index
    verdict = ContainerYardMoveVerdict(
        from_slot_occupied=from_occupied,
        to_slot_empty=to_empty,
        from_slot_correct=from_correct,
        to_slot_correct=to_correct,
    )
    if team.round_failed_terminally:
        return MoveJudgement(
            result=MoveResult(accepted=False, soft_rejected=False),
            verdict=verdict,
            step_index=step_index,
            marker=MOVE_REJECTED_MARKER,
            explanation="The round has already failed terminally; no more moves accepted.",
        )
    if not from_in_range or not to_in_range or not from_occupied or not to_empty:
        return _soft(
            verdict=verdict,
            step_index=step_index,
            explanation=_structural_reason(
                from_in_range=from_in_range,
                to_in_range=to_in_range,
                from_occupied=from_occupied,
                to_empty=to_empty,
                submitted_from_slot=submitted_from_slot,
                submitted_to_slot=submitted_to_slot,
                yard_slot_count=yard_slot_count,
            ),
        )
    if from_correct and to_correct and step is not None:
        return await _accept(
            team=team,
            case=case,
            step=step,
            context=context,
            submitted_from_slot=submitted_from_slot,
            submitted_to_slot=submitted_to_slot,
            verdict=verdict,
        )
    team.round_failed_terminally = True
    reason = _correctness_reason(from_correct=from_correct, to_correct=to_correct)
    if team.failure_reason == "":
        team.failure_reason = reason
    return MoveJudgement(
        result=MoveResult(accepted=False, soft_rejected=False),
        verdict=verdict,
        step_index=step_index,
        marker=MOVE_REJECTED_MARKER,
        explanation=reason,
    )


def _soft(verdict: ContainerYardMoveVerdict, step_index: int, explanation: str) -> MoveJudgement:
    """Build a soft-reject judgement (retryable, no terminal failure)."""
    return MoveJudgement(
        result=MoveResult(accepted=False, soft_rejected=True),
        verdict=verdict,
        step_index=step_index,
        marker=MOVE_REJECTED_MARKER,
        explanation=explanation,
    )


async def _accept(
    team: TeamState,
    case: YardCase,
    step: CaseStep,
    context: WorldContext,
    submitted_from_slot: int,
    submitted_to_slot: int,
    verdict: ContainerYardMoveVerdict,
) -> MoveJudgement:
    """Relocate the container, record the placement, report progress."""
    container = team.current_row[submitted_from_slot]
    team.current_row[submitted_from_slot] = None
    team.current_row[submitted_to_slot] = container
    team.placed_count += 1
    team.step_outcomes.append(
        StepOutcome(
            step_index=step.step_index,
            container_summary=render_container(container=step.container),
            intake_slot=step.intake_slot,
            target_slot=step.target_slot,
            succeeded=True,
        )
    )
    await context.send_update_to_channel(
        channel_id=team.link_channel_id,
        text=(
            f"{CONTAINER_PLACED_MARKER}. A container reached slot {submitted_to_slot}. "
            f"({team.placed_count}/{len(case.steps)} placed.)"
        ),
    )
    return MoveJudgement(
        result=MoveResult(accepted=True, soft_rejected=False),
        verdict=verdict,
        step_index=step.step_index,
        marker=MOVE_SUCCESS_MARKER,
        explanation=f"Container relocated to slot {submitted_to_slot}.",
    )


def _structural_reason(
    from_in_range: bool,
    to_in_range: bool,
    from_occupied: bool,
    to_empty: bool,
    submitted_from_slot: int,
    submitted_to_slot: int,
    yard_slot_count: int,
) -> str:
    """Explain a structurally impossible move so the operator can retry."""
    if not from_in_range:
        return (
            f"Source slot {submitted_from_slot} is out of range (slots are 1..{yard_slot_count})."
        )
    if not to_in_range:
        return (
            f"Destination slot {submitted_to_slot} is out of range "
            f"(slots are 1..{yard_slot_count})."
        )
    if not from_occupied:
        return f"Source slot {submitted_from_slot} is empty — there is no container to pick up."
    if not to_empty:
        return f"Destination slot {submitted_to_slot} is already occupied."
    return "Move could not be applied."


def _correctness_reason(from_correct: bool, to_correct: bool) -> str:
    """Explain a structurally valid but incorrect move (terminal failure)."""
    reasons: list[str] = []
    if not from_correct:
        reasons.append("the source slot is not an intake slot holding a batch container to place")
    if not to_correct:
        reasons.append("the destination is not that container's assigned bay")
    if not reasons:
        return "Move rejected."
    return "Move rejected: " + "; ".join(reasons) + "."
