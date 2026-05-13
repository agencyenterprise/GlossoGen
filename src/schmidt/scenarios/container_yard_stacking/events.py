"""Pydantic event types specific to the container_yard_stacking scenario."""

from typing import Literal, Self

from pydantic import BaseModel, model_validator

from schmidt.models.event_base import EventBase


class ContainerYardStackPosition(BaseModel):
    """A target slot in the yard expressed as (stack, tier)."""

    stack: int
    tier: int


class ContainerYardCraneStation(BaseModel):
    """A crane station active this round and the stack indices it can reach."""

    station_name: str
    pads: list[str]
    reachable_stacks: list[int]


class ContainerYardTruckAssignment(BaseModel):
    """Ground-truth assignment for one truck the yard operator must commit.

    ``container_id`` is the incoming container for inbound trucks and an
    empty string for outbound trucks (they arrive empty and leave loaded).
    The transfer pad is the planner's choice at runtime — any pad of the
    correct station is acceptable, with the constraint that inbound and
    outbound trucks use different pads on rounds with a blocker.
    """

    truck_role: str
    station_name: str
    container_id: str


class ContainerYardCraneMoveStep(BaseModel):
    """One step in the expected crane plan or in the agent's submitted history.

    The endpoints are structured (no string rendering): ``source_kind`` is
    ``"inbound_truck"`` or ``"stack_tier"``; ``destination_kind`` is
    ``"outbound_truck"`` or ``"stack_tier"``. The ``*_stack`` / ``*_tier``
    fields are populated only when the corresponding kind is
    ``"stack_tier"`` and ``None`` otherwise.
    """

    move_index: int
    container_id: str
    source_kind: Literal["inbound_truck", "stack_tier"]
    source_stack: int | None
    source_tier: int | None
    destination_kind: Literal["outbound_truck", "stack_tier"]
    destination_stack: int | None
    destination_tier: int | None


class ContainerYardStackSnapshot(BaseModel):
    """One stack's bottom-to-top container IDs at a point in time."""

    stack: int
    containers_bottom_to_top: list[str]


class ContainerYardManifestEntry(BaseModel):
    """One entry in the shift manifest shown to the logistics planner.

    The real incoming entry is mixed with decoys so the planner cannot
    pick the active target slot without the yard operator's container ID.
    """

    container_id: str
    target_position: ContainerYardStackPosition


class ContainerYardCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data."""

    event_type: Literal["container_yard_case_started"] = "container_yard_case_started"
    case_number: int
    incoming_container_id: str
    active_crane_stations: list[ContainerYardCraneStation]
    correct_crane_station: str
    initial_stacks: list[ContainerYardStackSnapshot]
    target_position: ContainerYardStackPosition
    truck_assignments: list[ContainerYardTruckAssignment]
    expected_move_sequence: list[ContainerYardCraneMoveStep]
    time_budget_seconds: int
    manifest: list[ContainerYardManifestEntry]


class ContainerYardTruckCommitVerdict(BaseModel):
    """World's per-criterion verdict on a structured ``move_truck`` call.

    ``role_matches_active_assignment`` is true when the submitted
    ``truck_role`` corresponds to an expected truck for this round.
    ``targets_correct_pad`` is true when the submitted pad is one of the
    correct station's transfer pads AND is not already committed to a
    different truck this round.
    """

    role_matches_active_assignment: bool
    targets_correct_station: bool
    targets_correct_pad: bool
    carries_correct_container: bool


class ContainerYardTruckJudged(EventBase):
    """Emitted after the world rules on a ``move_truck`` call.

    The verdict is deterministic: the agent submits structured Pydantic
    args and the world checks them against the case ground truth.
    """

    event_type: Literal["container_yard_truck_judged"] = "container_yard_truck_judged"
    agent_id: str
    submitted_truck_role: Literal["inbound", "outbound"]
    submitted_station_name: str
    submitted_pad: str
    submitted_container_id: str
    verdict: ContainerYardTruckCommitVerdict
    overall_success: bool
    explanation: str


class ContainerYardCraneMoveVerdict(BaseModel):
    """World's per-criterion verdict on a structured ``crane_move`` call.

    ``parsed_source_kind`` / ``parsed_destination_kind`` classify each
    endpoint of the move; ``parsed_source_stack`` / ``parsed_destination_stack``
    carry the stack index when the corresponding kind is ``stack_tier``;
    they are ``None`` for truck endpoints. The world reads these
    structured fields when mutating state.
    """

    matches_expected_next_move: bool
    source_currently_holds_container: bool
    destination_currently_empty: bool
    parsed_source_kind: Literal["inbound_truck", "outbound_truck", "stack_tier"]
    parsed_source_stack: int | None
    parsed_destination_kind: Literal["inbound_truck", "outbound_truck", "stack_tier"]
    parsed_destination_stack: int | None

    @model_validator(mode="after")
    def _validate_kind_stack_pairing(self) -> Self:
        """Enforce ``parsed_*_stack`` is present iff the corresponding kind is ``stack_tier``."""
        if self.parsed_source_kind == "stack_tier" and self.parsed_source_stack is None:
            raise ValueError(
                "parsed_source_stack must be set when parsed_source_kind is stack_tier"
            )
        if self.parsed_source_kind != "stack_tier" and self.parsed_source_stack is not None:
            raise ValueError(
                "parsed_source_stack must be null when parsed_source_kind is a truck role"
            )
        if self.parsed_destination_kind == "stack_tier" and self.parsed_destination_stack is None:
            raise ValueError(
                "parsed_destination_stack must be set when parsed_destination_kind is stack_tier"
            )
        if (
            self.parsed_destination_kind != "stack_tier"
            and self.parsed_destination_stack is not None
        ):
            raise ValueError(
                "parsed_destination_stack must be null when parsed_destination_kind is a truck role"
            )
        return self


class ContainerYardCraneMoveJudged(EventBase):
    """Emitted after the world rules on a ``crane_move`` call.

    The verdict is deterministic: the agent submits structured location
    fields and the world matches them against the next-expected step in
    ``ContainerYardCaseStarted.expected_move_sequence`` and the live
    world state.
    """

    event_type: Literal["container_yard_crane_move_judged"] = "container_yard_crane_move_judged"
    agent_id: str
    move_index: int
    submitted_move: ContainerYardCraneMoveStep
    verdict: ContainerYardCraneMoveVerdict
    accepted: bool
    marker: str
    explanation: str
