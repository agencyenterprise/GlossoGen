"""Pydantic event types specific to the container_yard_stacking scenario.

A container carries no ID — it is a bundle of attributes. Each round a batch
of containers arrives in intake slots and must be relocated to assigned
target bays. The event log serializes the per-round ground truth (the
occupancy row and the batch assignment) plus the deterministic verdict on
every ``move_container`` call.
"""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase


class ContainerYardAttribute(BaseModel):
    """One (dimension, value) pair of a container's attribute bundle."""

    name: str
    value: str


class ContainerYardContainer(BaseModel):
    """A yard container described entirely by its ordered attribute bundle."""

    attributes: list[ContainerYardAttribute]


class ContainerYardSlot(BaseModel):
    """One slot in the yard and the container in it (or empty)."""

    slot: int
    container: ContainerYardContainer | None


class ContainerYardBatchItem(BaseModel):
    """One container in the round's batch: its attributes, intake slot, and target bay."""

    container: ContainerYardContainer
    intake_slot: int
    target_slot: int


class ContainerYardCaseStarted(EventBase):
    """Emitted once at round start with the full ground-truth case.

    The whole batch is known at round start: the spotter sees each item's
    attributes + ``intake_slot``, the planner sees each item's attributes +
    ``target_slot``, and the crane sees only ``initial_row`` occupancy.
    """

    event_type: Literal["container_yard_case_started"] = "container_yard_case_started"
    case_number: int
    round_time_budget_seconds: int
    yard_slot_count: int
    initial_row: list[ContainerYardSlot]
    batch: list[ContainerYardBatchItem]


class ContainerYardMoveVerdict(BaseModel):
    """World's per-criterion verdict on a ``move_container`` call.

    ``from_slot_occupied`` / ``to_slot_empty`` are the structural checks (a
    violation is a soft reject the operator can retry).
    ``from_slot_correct`` / ``to_slot_correct`` compare against the batch
    assignment (a structurally valid but incorrect move fails the round).
    """

    from_slot_occupied: bool
    to_slot_empty: bool
    from_slot_correct: bool
    to_slot_correct: bool


class ContainerYardMoveJudged(EventBase):
    """Emitted after the world rules on a ``move_container`` call.

    The verdict is deterministic: the operator submits a source slot and a
    destination slot and the world compares them to the batch container's
    intake slot and target bay and the live row state.
    """

    event_type: Literal["container_yard_move_judged"] = "container_yard_move_judged"
    agent_id: str
    step_index: int
    submitted_from_slot: int
    submitted_to_slot: int
    verdict: ContainerYardMoveVerdict
    accepted: bool
    soft_rejected: bool
    marker: str
    explanation: str
