"""Pydantic event types specific to the spot_the_intersection scenario.

A round's start records every board as its viewer reads it, every distinct
object with what it was placed for and which seats hold it, and the round's
certificate. Each ``submit_object`` call records the object submitted and
whether it was the answer. Seats are numbered from 1, matching the agent ids.
"""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase
from glossogen.scenarios.spot_the_intersection.board_certification import ObjectKind


class IntersectionObjectRecord(BaseModel):
    """One distinct object of a round, what it was placed for and the seats holding it."""

    kind: ObjectKind
    shape: str
    color: str
    cell: str
    seat_numbers: list[int]


class IntersectionCertificateRecord(BaseModel):
    """What certification measured on a round's boards.

    ``candidates_without_seat[i]`` counts the objects on every board but seat
    ``i + 1``'s. The ``shared_*`` counts are how many values each partial
    comparison finds on every board. ``dump_object_mentions`` lists every board
    in full; ``sequential_filter_object_mentions`` has each viewer in seat order
    list what survives on its board. ``generation_attempts`` counts the draws
    before the round certified.
    """

    candidates_without_seat: list[int]
    shared_cells: int
    shared_looks: int
    shared_shapes_and_cells: int
    shared_colors_and_cells: int
    dump_object_mentions: int
    sequential_filter_object_mentions: int
    generation_attempts: int


class SpotTheIntersectionRoundStarted(EventBase):
    """Emitted once at round start with the full ground truth.

    ``boards[i]`` is seat ``i + 1``'s board, line for line in the order its
    viewer reads it, and both teams' seat ``i + 1`` hold it. ``decoy_count`` and
    ``filler_count`` are the round's two draws: ``decoy_count`` decoy objects,
    and ``board_size`` objects on every board, padded with fillers, so a board
    holds ``filler_count`` fillers plus one for each decoy it lacks.
    """

    event_type: Literal["spot_the_intersection_round_started"] = (
        "spot_the_intersection_round_started"
    )
    team_size: int
    grid_size: int
    board_size: int
    decoy_count: int
    filler_count: int
    round_time_budget_seconds: int
    answer_line: str
    boards: list[list[str]]
    objects: list[IntersectionObjectRecord]
    certificate: IntersectionCertificateRecord


class IntersectionSubmissionRecorded(EventBase):
    """Emitted for every accepted ``submit_object`` call.

    ``team_characters`` is the team's charge under the run's ``team_characters``
    knob when this viewer submitted; on the submission that completes the team
    it is the count the team is scored on.
    """

    event_type: Literal["intersection_submission_recorded"] = "intersection_submission_recorded"
    agent_id: str
    team_id: str
    seat_number: int
    shape: str
    color: str
    cell: str
    correct: bool
    team_characters: int
    members_submitted: int
    members_required: int
