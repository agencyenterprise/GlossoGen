"""Adapters that turn ``DiffCase`` namedtuples into event-log models.

The scenario keeps its ground truth as plain ``NamedTuple`` instances (see
:mod:`scene_generation`). The event log serializes round-start state as
Pydantic ``BaseModel`` instances (see :mod:`events`). The helpers here bridge
the two whenever the scenario emits a ``SpotTheDifferenceCaseStarted`` event.
"""

from glossogen.scenarios.spot_the_difference.events import (
    SpotObject,
    SpotPlantedDifference,
    SpotTheDifferenceCaseStarted,
)
from glossogen.scenarios.spot_the_difference.scene_generation import (
    DiffCase,
    PlantedDifference,
    SceneObject,
    region_of,
)


def object_to_event(obj: SceneObject, grid_size: int) -> SpotObject:
    """Convert a case-layer scene object to its event-log form."""
    return SpotObject(
        shape=obj.shape,
        color=obj.color,
        size=obj.size,
        column=obj.column,
        row=obj.row,
        region=region_of(column=obj.column, row=obj.row, grid_size=grid_size),
    )


def _optional_object_to_event(obj: SceneObject | None, grid_size: int) -> SpotObject | None:
    """Convert an optional scene object, preserving ``None``."""
    if obj is None:
        return None
    return object_to_event(obj=obj, grid_size=grid_size)


def difference_to_event(difference: PlantedDifference, grid_size: int) -> SpotPlantedDifference:
    """Convert a case-layer planted difference to its event-log form."""
    return SpotPlantedDifference(
        kind=difference.kind.value,
        description=difference.description,
        scene_a_object=_optional_object_to_event(
            obj=difference.scene_a_object, grid_size=grid_size
        ),
        scene_b_object=_optional_object_to_event(
            obj=difference.scene_b_object, grid_size=grid_size
        ),
        attribute_name=difference.attribute_name,
    )


def case_started_event(round_number: int, case: DiffCase) -> SpotTheDifferenceCaseStarted:
    """Build the full ``SpotTheDifferenceCaseStarted`` event for ``case``."""
    grid_size = case.grid_size
    return SpotTheDifferenceCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        grid_size=grid_size,
        round_time_budget_seconds=case.round_time_budget_seconds,
        difference_count=case.difference_count,
        scene_a=[object_to_event(obj=obj, grid_size=grid_size) for obj in case.scene_a],
        scene_b=[object_to_event(obj=obj, grid_size=grid_size) for obj in case.scene_b],
        differences=[
            difference_to_event(difference=diff, grid_size=grid_size) for diff in case.differences
        ],
    )
