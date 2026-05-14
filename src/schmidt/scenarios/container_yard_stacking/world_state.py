"""Mutable per-team state and immutable outcome types for the yard world.

The world holds one ``TeamState`` per team (solo mode keeps one; two-team
mode keeps two). Each ``TeamState`` carries the live truck positions,
current step bookkeeping, and the rolling list of finished ``YardOutcome``
entries. Truck commit and crane move judging modules mutate these fields;
``ContainerYardWorld`` owns the lifecycle (reset, finalize, mark outcome).
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class TruckState(NamedTuple):
    """Live per-step position and contents of one truck."""

    truck_role: str
    arrived: bool
    station_name: str
    pad: str
    container_id: str


class TruckCommitResult(NamedTuple):
    """Outcome of a single ``record_truck_commit`` call."""

    truck_role: str
    accepted: bool
    duplicate: bool


class StepOutcome(NamedTuple):
    """One step's recorded outcome within a completed round."""

    step_index: int
    incoming_container_id: str
    target_position_text: str
    succeeded: bool
    expected_move_count: int
    accepted_move_count: int
    expected_truck_count: int
    correctly_committed_truck_count: int


class YardOutcome(NamedTuple):
    """Result of a single yard case after a round completes for one team."""

    case_number: int
    team_id: str
    step_count: int
    steps_succeeded: int
    step_outcomes: tuple[StepOutcome, ...]
    total_expected_move_count: int
    total_accepted_move_count: int
    total_expected_truck_count: int
    total_correctly_committed_truck_count: int
    budget_exceeded: bool
    characters_used: int
    time_budget_seconds: int
    round_succeeded: bool
    failure_reason: str
    failure_step_index: int | None


@dataclass
class TeamState:
    """All per-team mutable state the world tracks for one team."""

    team_id: str
    link_channel_id: str
    yard_operator_id: str
    current_round_characters: int = 0
    round_budget_exceeded: bool = False
    notified_thresholds: set[str] = field(default_factory=set)
    outcomes: list[YardOutcome] = field(default_factory=list)
    current_stacks: dict[int, list[str]] = field(default_factory=dict)
    truck_states: dict[str, TruckState] = field(default_factory=dict)
    round_failed_terminally: bool = False
    failure_reason: str = ""
    round_outcome_marked: bool = False
    current_step_index: int = 0
    step_accepted_move_count: int = 0
    step_correctly_committed_truck_count: int = 0
    step_outcomes: list[StepOutcome] = field(default_factory=list)


def stack_position_text(stack: int, tier: int) -> str:
    """Return the canonical ``Stack S, Tier T`` position string."""
    return f"Stack {stack}, Tier {tier}"
