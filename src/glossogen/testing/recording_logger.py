"""An event logger that keeps what it was given in memory.

Stands in for the run's event log where a test drives a scenario or a runtime
directly and then reads back what was logged, with no run directory involved.
"""

from typing import Any


class RecordingLogger:
    """Keeps logged events in memory, in the order they were logged."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        """Keep ``event``, as the real logger would write it."""
        self.events.append(event)
