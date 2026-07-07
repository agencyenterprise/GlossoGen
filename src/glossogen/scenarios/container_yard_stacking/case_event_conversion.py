"""Adapters that turn ``YardCase`` namedtuples into event-log models.

The scenario keeps its ground truth as plain ``NamedTuple`` instances (see
:mod:`yard_cases`). The event log serializes round-start state as Pydantic
``BaseModel`` instances (see :mod:`events`). The helpers here bridge the two
whenever the scenario emits a ``ContainerYardCaseStarted`` event.
"""

from glossogen.scenarios.container_yard_stacking.container_attributes import (
    Container,
    attribute_pairs,
)
from glossogen.scenarios.container_yard_stacking.events import (
    ContainerYardAttribute,
    ContainerYardBatchItem,
    ContainerYardCaseStarted,
    ContainerYardContainer,
    ContainerYardSlot,
)
from glossogen.scenarios.container_yard_stacking.yard_cases import CaseStep, YardCase


def container_to_event(container: Container) -> ContainerYardContainer:
    """Convert a case-layer container to its event-log form."""
    return ContainerYardContainer(
        attributes=[
            ContainerYardAttribute(name=name, value=value)
            for name, value in attribute_pairs(container=container)
        ]
    )


def batch_item_to_event(step: CaseStep) -> ContainerYardBatchItem:
    """Convert a case-layer batch step to its event-log form."""
    return ContainerYardBatchItem(
        container=container_to_event(container=step.container),
        intake_slot=step.intake_slot,
        target_slot=step.target_slot,
    )


def row_to_event(row: dict[int, Container | None]) -> list[ContainerYardSlot]:
    """Convert the case-layer row dict to an ordered list of event-log slots."""
    slots: list[ContainerYardSlot] = []
    for slot in sorted(row.keys()):
        container = row[slot]
        if container is None:
            slots.append(ContainerYardSlot(slot=slot, container=None))
        else:
            slots.append(
                ContainerYardSlot(slot=slot, container=container_to_event(container=container))
            )
    return slots


def case_started_event(round_number: int, case: YardCase) -> ContainerYardCaseStarted:
    """Build the full ``ContainerYardCaseStarted`` event for ``case`` at ``round_number``."""
    return ContainerYardCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        round_time_budget_seconds=case.round_time_budget_seconds,
        yard_slot_count=case.yard_slot_count,
        initial_row=row_to_event(row=case.initial_row),
        batch=[batch_item_to_event(step=step) for step in case.steps],
    )
