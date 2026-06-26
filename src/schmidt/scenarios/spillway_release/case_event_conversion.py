"""Adapter that turns a ``SpillwayCase`` namedtuple into the event-log model.

The scenario keeps its ground truth as a plain ``NamedTuple`` (see
:mod:`spillway_cases`) for convenient in-process use; the event log
serializes round-start state as the ``SpillwayCaseStarted`` Pydantic model
(see :mod:`events`). This helper bridges the two whenever the scenario emits
the case-started event.
"""

from schmidt.scenarios.spillway_release.events import SpillwayCaseStarted
from schmidt.scenarios.spillway_release.spillway_cases import SpillwayCase


def case_started_event(round_number: int, case: SpillwayCase) -> SpillwayCaseStarted:
    """Build the full ``SpillwayCaseStarted`` event for ``case`` at ``round_number``."""
    return SpillwayCaseStarted(
        round_number=round_number,
        case_number=case.case_number,
        current_time_hours=case.current_time_hours,
        start_level=case.start_level,
        inflow=case.inflow,
        forecast_conditions=case.forecast_conditions,
        park_opens_at_hours=case.park_opens_at_hours,
        park_lockable=case.park_lockable,
        visitors=case.visitors,
        day_end_hours=case.day_end_hours,
        gate_count=case.gate_count,
        release_per_gate_per_hour=case.release_per_gate_per_hour,
        max_level=case.max_level,
        min_level=case.min_level,
        round_time_budget_seconds=case.round_time_budget_seconds,
    )
