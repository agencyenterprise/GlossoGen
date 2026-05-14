"""Adapters that turn ``YardCase`` / ``CaseStep`` namedtuples into event-log models.

The scenario keeps its ground truth as plain ``NamedTuple`` instances
(see :mod:`yard_cases`) because they are convenient for in-process
mutation and indexing. The event log serializes round-start state as
Pydantic ``BaseModel`` instances (see :mod:`events`). The conversion
helpers here bridge the two representations whenever the scenario
emits a ``ContainerYardCaseStarted`` event or needs to surface a step
in a truck/crane verdict.
"""

from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCaseStarted,
    ContainerYardCaseStep,
    ContainerYardCraneStation,
    ContainerYardManifestEntry,
    ContainerYardStackPosition,
    ContainerYardStackSnapshot,
    ContainerYardTruckAssignment,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import CaseStep, TruckAssignment, YardCase


def truck_assignment_to_event(assignment: TruckAssignment) -> ContainerYardTruckAssignment:
    """Convert the case namedtuple form to the event-log BaseModel form."""
    return ContainerYardTruckAssignment(
        truck_role=assignment.truck_role,
        station_name=assignment.station_name,
        container_id=assignment.container_id,
    )


def correct_station_pads_for_step(case: YardCase, step: CaseStep) -> list[str]:
    """Return the list of transfer pads at the step's correct crane station."""
    for station in case.active_crane_stations:
        if station.station_name == step.correct_crane_station:
            return list(station.pads)
    raise ValueError(
        f"correct station {step.correct_crane_station} not found among active stations"
    )


def case_step_to_event(step: CaseStep) -> ContainerYardCaseStep:
    """Convert the case namedtuple step into the event-log BaseModel form."""
    return ContainerYardCaseStep(
        step_index=step.step_index,
        incoming_container_id=step.incoming_container_id,
        target_position=ContainerYardStackPosition(
            stack=step.target_position.stack,
            tier=step.target_position.tier,
        ),
        correct_crane_station=step.correct_crane_station,
        truck_assignments=[
            truck_assignment_to_event(assignment=assignment)
            for assignment in step.truck_assignments
        ],
        expected_move_sequence=list(step.expected_move_sequence),
    )


def case_started_event(round_number: int, case: YardCase) -> ContainerYardCaseStarted:
    """Build the full ``ContainerYardCaseStarted`` event for ``case`` at ``round_number``."""
    return ContainerYardCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        active_crane_stations=[
            ContainerYardCraneStation(
                station_name=station.station_name,
                pads=list(station.pads),
                reachable_stacks=list(station.reachable_stacks),
            )
            for station in case.active_crane_stations
        ],
        initial_stacks=[
            ContainerYardStackSnapshot(
                stack=stack_index,
                containers_bottom_to_top=list(containers),
            )
            for stack_index, containers in sorted(case.initial_stacks.items())
        ],
        time_budget_seconds=case.time_budget_seconds,
        steps=[case_step_to_event(step=step) for step in case.steps],
        manifest=[
            ContainerYardManifestEntry(
                container_id=entry.container_id,
                target_position=ContainerYardStackPosition(
                    stack=entry.target_position.stack,
                    tier=entry.target_position.tier,
                ),
            )
            for entry in case.manifest
        ],
    )
