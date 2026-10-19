"""The one tool spot_the_intersection offers its viewers.

``submit_object`` names the object a viewer believes is on every board of its
team. Each viewer submits once per round and cannot change it, and the team is
scored once every member has submitted. Whether a submission was right is
revealed only when the round ends, so no viewer can submit, learn the answer,
and pass it on. A submission arriving after its round was scored, while the
clock is still closing the round, is refused rather than recorded against a
result it can no longer change.
"""

from collections.abc import Callable

from glossogen.runtime.scenario_tool import SCENARIO_TOOL_TIMEOUT_SECONDS, ScenarioTool
from glossogen.scenario_base import ScenarioRuntimeHandle
from glossogen.scenarios.spot_the_intersection.board_model import (
    COLORS,
    SHAPES,
    BoardObject,
    Color,
    Shape,
    cell_label,
)
from glossogen.scenarios.spot_the_intersection.board_rendering import parse_cell_label
from glossogen.scenarios.spot_the_intersection.events import IntersectionSubmissionRecorded
from glossogen.scenarios.spot_the_intersection.ids import (
    ALREADY_SUBMITTED_MARKER,
    ANSWER_LOCKED_MARKER,
    SUBMISSION_RECORDED_MARKER,
    SUBMIT_OBJECT_TOOL,
)
from glossogen.scenarios.spot_the_intersection.world import (
    SpotTheIntersectionWorld,
    SubmissionReceipt,
)

_DESCRIPTION = (
    "Submit the object you believe is on every board of your team: its shape, its color, "
    "and its cell, named by column letter and row number (for example C4). Every member of "
    "your team must submit, and your team is correct only when every member submits that "
    "same, correct object. One call per viewer per round; it cannot be changed."
)


def build_tools(
    world: SpotTheIntersectionWorld, get_runtime: Callable[[], ScenarioRuntimeHandle | None]
) -> list[ScenarioTool]:
    """Return the ``submit_object`` tool."""

    async def submit_object(agent_id: str, shape: Shape, color: Color, cell: str) -> str:
        """Submit the object on every board of the caller's team."""
        seat = world.seat_of(agent_id=agent_id)
        if seat is None:
            raise ValueError(f"Unknown agent for {SUBMIT_OBJECT_TOOL}: {agent_id}")
        if shape not in SHAPES:
            raise ValueError(f"shape must be one of {', '.join(SHAPES)} (got {shape!r})")
        if color not in COLORS:
            raise ValueError(f"color must be one of {', '.join(COLORS)} (got {color!r})")
        if world.in_postmortem:
            return "Cannot submit during the post-round discussion phase. Wait for the next round."
        current = world.current_round_boards
        if current is None:
            return "There is no round in play yet."
        if world.outcome_for(team_id=seat.team_id, round_number=current.round_number) is not None:
            return "This round has ended and been scored. Wait for the next round."
        column, row = parse_cell_label(label=cell.strip().upper(), grid_size=current.grid_size)
        if world.has_submitted(agent_id=agent_id):
            return (
                f"{ALREADY_SUBMITTED_MARKER}. You have already submitted this round, and a "
                "submission cannot be changed."
            )
        obj = BoardObject(shape=shape, color=color, column=column, row=row)
        receipt = world.record_submission(agent_id=agent_id, obj=obj)
        await _log_submission(
            get_runtime=get_runtime,
            round_number=current.round_number,
            agent_id=agent_id,
            team_id=seat.team_id,
            seat_number=seat.board_index + 1,
            obj=obj,
            receipt=receipt,
        )
        if receipt.completed_team:
            await world.announce_team_locked(team_id=seat.team_id)
            return (
                f"{ANSWER_LOCKED_MARKER}. Every member has submitted; your team's answer is "
                "locked. Results are revealed when the round ends."
            )
        return (
            f"{SUBMISSION_RECORDED_MARKER}. Your answer is recorded and cannot be changed. "
            "Your team is scored once every member has submitted."
        )

    return [
        ScenarioTool(
            name=SUBMIT_OBJECT_TOOL,
            description=_DESCRIPTION,
            executor=submit_object,
            timeout_s=SCENARIO_TOOL_TIMEOUT_SECONDS,
        )
    ]


async def _log_submission(
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
    round_number: int,
    agent_id: str,
    team_id: str,
    seat_number: int,
    obj: BoardObject,
    receipt: SubmissionReceipt,
) -> None:
    """Record one accepted submission in the event log, under the round it was recorded for."""
    runtime = get_runtime()
    if runtime is None:
        return
    await runtime.event_logger.log(
        event=IntersectionSubmissionRecorded(
            round_number=round_number,
            agent_id=agent_id,
            team_id=team_id,
            seat_number=seat_number,
            shape=obj.shape,
            color=obj.color,
            cell=cell_label(column=obj.column, row=obj.row),
            correct=receipt.correct,
            team_characters=receipt.team_characters,
            members_submitted=receipt.members_submitted,
            members_required=receipt.members_required,
        )
    )
