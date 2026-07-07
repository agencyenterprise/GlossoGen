"""Pydantic event types specific to the spot_the_difference scenario.

The event log serializes the per-round ground truth (both scenes plus the
planted differences) and the LLM judge's verdict on every ``submit_differences``
call (which planted differences the team's submission identified, how many of
its items matched nothing, and the team's character count at submission).
"""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase


class SpotObject(BaseModel):
    """One scene object: a shape/color/size bundle at a grid cell.

    ``column`` / ``row`` are the internal geometry (never shown to agents);
    ``region`` is the coarse 3x3 area the agents actually see.
    """

    shape: str
    color: str
    size: str
    column: int
    row: int
    region: str


class SpotPlantedDifference(BaseModel):
    """One ground-truth difference between scene A and scene B.

    ``scene_a_object`` / ``scene_b_object`` is ``None`` for an added object
    (absent from A) or a removed object (absent from B). ``attribute_name``
    names the changed dimension for ``attribute_changed`` and is ``None``
    otherwise.
    """

    kind: str
    description: str
    scene_a_object: SpotObject | None
    scene_b_object: SpotObject | None
    attribute_name: str | None


class SpotTheDifferenceCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth scene pair.

    The left viewer sees ``scene_a`` and the right viewer sees ``scene_b``;
    neither sees the other scene nor ``differences``.
    """

    event_type: Literal["spot_the_difference_case_started"] = "spot_the_difference_case_started"
    case_number: int
    grid_size: int
    round_time_budget_seconds: int
    difference_count: int
    scene_a: list[SpotObject]
    scene_b: list[SpotObject]
    differences: list[SpotPlantedDifference]


class DifferenceSubmissionJudged(EventBase):
    """Emitted after the LLM judge rules on a ``submit_differences`` call.

    ``matched_difference_indices`` are the 1-based indices into the round's
    planted differences that the team's submission correctly identified;
    ``false_positive_count`` is how many submitted items matched no planted
    difference. ``found_all`` is the correctness gate (every planted
    difference identified and no false positives).
    """

    event_type: Literal["difference_submission_judged"] = "difference_submission_judged"
    agent_id: str
    team_id: str
    submitted_items: list[str]
    matched_difference_indices: list[int]
    false_positive_count: int
    found_all: bool
    characters_at_submission: int
    judge_explanation: str
