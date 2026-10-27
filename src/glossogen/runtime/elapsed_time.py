"""Helpers for expressing message times as elapsed seconds since simulation start.

Agents receive channel-message times as a float number of seconds since the
simulation began (millisecond precision) rather than a wall-clock ISO string.
This keeps the context compact and aligns with time-budget scenarios where
elapsed time is the meaningful quantity.
"""

from datetime import datetime

from glossogen.models.event import SimulationEvent, SimulationStarted


def elapsed_seconds_since_start(when: datetime, start: datetime) -> float:
    """Return seconds (millisecond precision) between ``start`` and ``when``."""
    return round((when - start).total_seconds(), 3)


def find_simulation_start_time(events: list[SimulationEvent]) -> datetime:
    """Return the timestamp of the earliest ``SimulationStarted`` event.

    Used to anchor elapsed-time conversion when reconstructing history from a
    JSONL log. Raises ``ValueError`` when no ``SimulationStarted`` event exists.
    """
    for event in events:
        if isinstance(event, SimulationStarted):
            return event.timestamp
    raise ValueError("No SimulationStarted event found; cannot anchor elapsed time.")
