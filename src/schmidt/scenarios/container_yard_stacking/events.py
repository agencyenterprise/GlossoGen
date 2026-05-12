"""Pydantic event types specific to the container_yard_stacking scenario."""

from typing import Literal

from pydantic import BaseModel

from schmidt.models.event_base import EventBase


class ContainerYardContainer(BaseModel):
    """The incoming container's manifest seen by the yard operator."""

    container_id: str
    size_class: str
    weight_tons: float
    departure_group: str


class ContainerYardStackPosition(BaseModel):
    """A target slot in the yard expressed as block / bay / stack / tier."""

    block: str
    bay: str
    stack: int
    tier: int


class ContainerYardCraneStation(BaseModel):
    """A crane station active this round and the stack indices it can reach."""

    station_name: str
    transfer_pad: str
    reachable_stacks: list[int]


class ContainerYardCraneMoveStep(BaseModel):
    """One step in the expected crane plan or in the agent's submitted history."""

    move_index: int
    container_id: str
    source: str
    destination: str


class ContainerYardStackSnapshot(BaseModel):
    """One stack's bottom-to-top container IDs at a point in time."""

    stack: int
    containers_bottom_to_top: list[str]


class ContainerYardCaseStarted(EventBase):
    """Emitted once at round start with full ground-truth case data."""

    event_type: Literal["container_yard_case_started"] = "container_yard_case_started"
    case_number: int
    incoming_container: ContainerYardContainer
    active_crane_stations: list[ContainerYardCraneStation]
    correct_crane_station: str
    correct_transfer_pad: str
    initial_stacks: list[ContainerYardStackSnapshot]
    target_position: ContainerYardStackPosition
    temp_slot_names: list[str]
    expected_move_sequence: list[ContainerYardCraneMoveStep]
    time_budget_seconds: int


class ContainerYardTruckJudgment(BaseModel):
    """Structured per-criterion verdict from the truck destination judge."""

    targets_correct_station: bool
    targets_correct_pad: bool
    carries_correct_container: bool


class ContainerYardTruckJudged(EventBase):
    """Emitted after the truck judge rules on a ``move_truck_to_crane_spot`` call."""

    event_type: Literal["container_yard_truck_judged"] = "container_yard_truck_judged"
    agent_id: str
    expected_station: str
    expected_pad: str
    expected_container_id: str
    submitted_destination_text: str
    judgment: ContainerYardTruckJudgment
    overall_success: bool
    judge_explanation: str


class ContainerYardCraneMoveJudgment(BaseModel):
    """Structured per-criterion verdict from the crane move judge."""

    matches_expected_next_move: bool
    source_currently_holds_container: bool
    destination_currently_empty: bool


class ContainerYardCraneMoveJudged(EventBase):
    """Emitted after the crane move judge rules on a ``crane_move`` call."""

    event_type: Literal["container_yard_crane_move_judged"] = "container_yard_crane_move_judged"
    agent_id: str
    move_index: int
    expected_next_move: ContainerYardCraneMoveStep
    submitted_action_text: str
    parsed_move: ContainerYardCraneMoveStep
    judgment: ContainerYardCraneMoveJudgment
    accepted: bool
    marker: str
    judge_explanation: str
