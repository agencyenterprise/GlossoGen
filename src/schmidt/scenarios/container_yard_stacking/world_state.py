"""Mutable per-team state and immutable outcome types for the yard world.

The world holds one ``TeamState`` per team (solo mode keeps one; two-team
mode keeps two). Each ``TeamState`` carries the live yard row, how many
batch containers have been placed, and the rolling list of finished
``YardOutcome`` entries. The move-judging module mutates these fields;
``ContainerYardWorld`` owns the lifecycle (reset, finalize, mark outcome).
"""

from dataclasses import dataclass, field
from typing import NamedTuple

from schmidt.scenarios.container_yard_stacking.container_attributes import Container


class MoveResult(NamedTuple):
    """Outcome of a single ``record_move`` call."""

    accepted: bool
    soft_rejected: bool


class StepOutcome(NamedTuple):
    """One batch container's recorded outcome within a completed round."""

    step_index: int
    container_summary: str
    intake_slot: int
    target_slot: int
    succeeded: bool


class YardOutcome(NamedTuple):
    """Result of a single yard case after a round completes for one team."""

    case_number: int
    team_id: str
    step_count: int
    steps_succeeded: int
    step_outcomes: tuple[StepOutcome, ...]
    budget_exceeded: bool
    characters_used: int
    round_time_budget_seconds: int
    round_succeeded: bool
    failure_reason: str
    failure_step_index: int | None


@dataclass
class TeamState:
    """All per-team mutable state the world tracks for one team."""

    team_id: str
    link_channel_id: str
    current_round_characters: int = 0
    round_budget_exceeded: bool = False
    notified_thresholds: set[str] = field(default_factory=set[str])
    outcomes: list[YardOutcome] = field(default_factory=list[YardOutcome])
    current_row: dict[int, Container | None] = field(default_factory=dict[int, "Container | None"])
    round_failed_terminally: bool = False
    failure_reason: str = ""
    round_outcome_marked: bool = False
    placed_count: int = 0
    step_outcomes: list[StepOutcome] = field(default_factory=list[StepOutcome])
