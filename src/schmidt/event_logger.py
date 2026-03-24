"""Async event logger that writes simulation events as newline-delimited JSON to a file.

Publishes each logged event to an ``EventBus`` for real-time delivery to SSE
subscribers when a bus is provided at construction time.
"""

import logging
from pathlib import Path

import aiofiles
import orjson

from schmidt.event_bus import EventBus
from schmidt.models.event import SimulationEvent

logger = logging.getLogger(__name__)


class EventLogger:
    """Writes ``SimulationEvent`` objects as newline-delimited JSON (JSONL) to a binary file."""

    def __init__(self, log_path: Path, event_bus: EventBus) -> None:
        """Store the target log file path. The file is not opened until ``open()`` is called."""
        self._log_path = log_path
        self._file: aiofiles.threadpool.binary.AsyncBufferedIOBase | None = None
        self._event_bus = event_bus

    @property
    def is_open(self) -> bool:
        """Whether the log file is currently open for writing."""
        return self._file is not None

    async def open(self) -> None:
        """Create parent directories if needed and open the log file for writing.

        Truncates any existing file so each simulation run produces a clean log.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = await aiofiles.open(self._log_path, mode="wb")
        logger.info("Event log opened: %s", self._log_path)

    async def log(self, event: SimulationEvent) -> None:
        """Serialize ``event`` to JSON, write it as a single line, and flush.

        Also publishes the event to the event bus for live streaming.
        Raises ``RuntimeError`` if the logger has not been opened.
        """
        if self._file is None:
            raise RuntimeError("EventLogger is not open. Call open() first.")
        event_dict = event.model_dump(mode="json")
        data = orjson.dumps(event_dict) + b"\n"
        await self._file.write(data)
        await self._file.flush()
        self._event_bus.publish(event=event_dict)

    async def close(self) -> None:
        """Close the underlying file handle if it is open and reset internal state."""
        if self._file is not None:
            await self._file.close()
            self._file = None
            logger.info("Event log closed: %s", self._log_path)
