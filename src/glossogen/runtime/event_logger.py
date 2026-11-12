"""Async event logger that writes simulation events as newline-delimited JSON to a file.

Publishes each logged event to the ``EventBus`` it is constructed with, for
real-time delivery to SSE subscribers. Logs only the event classes it is built
with, the platform's and the running scenario's declared ones, so every line it
writes is one a reader of the run can parse. An ``UnrecognizedEvent``, which a
reader builds from a line it could not parse, is refused too: a derived run keeps
its source's lines through ``rewrite_run_jsonl`` and never logs one through here.
"""

import asyncio
import logging
from pathlib import Path

import aiofiles
import orjson

from glossogen.models.event import SimulationEvent, UnrecognizedEvent, fixed_event_type
from glossogen.models.event_base import EventBase
from glossogen.runtime.event_bus import EventBus

logger = logging.getLogger(__name__)


class UndeclaredEventType(TypeError):
    """Raised when an event's class is not one the logger was built to accept."""


class EventLogger:
    """Writes ``SimulationEvent`` objects as newline-delimited JSON (JSONL) to a binary file.

    ``allowed_event_types`` are the classes it logs: the platform's events and the
    ones the running scenario declares in ``event_types()``
    (:func:`glossogen.scenario_contract.event_types.loggable_event_types`). A run
    is read back with exactly those, so any other class is refused.
    """

    def __init__(
        self,
        log_path: Path,
        event_bus: EventBus,
        allowed_event_types: frozenset[type[EventBase]],
    ) -> None:
        """Store the target log file path. The file is not opened until ``open()`` is called."""
        self._log_path = log_path
        self._allowed_event_types = allowed_event_types
        self._file: aiofiles.threadpool.binary.AsyncBufferedIOBase | None = None
        self._event_bus = event_bus
        self._write_lock = asyncio.Lock()

    async def open(self) -> None:
        """Create parent directories if needed and open the log file for writing.

        Truncates any existing file so each simulation run produces a clean log.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = await aiofiles.open(self._log_path, mode="wb")
        logger.info("Event log opened: %s", self._log_path)

    async def open_for_append(self) -> None:
        """Open the log file in append mode for resuming a simulation.

        Does not truncate the existing content. Raises ``FileNotFoundError``
        if the log file does not exist.
        """
        if not self._log_path.exists():
            raise FileNotFoundError(f"Cannot resume: log file not found at {self._log_path}")
        self._file = await aiofiles.open(self._log_path, mode="ab")
        logger.info("Event log opened for append (resume): %s", self._log_path)

    async def log(self, event: SimulationEvent) -> None:
        """Serialize ``event`` to JSON, write it as a single line, and flush.

        Also publishes the event to the event bus for live streaming.
        Raises :class:`UndeclaredEventType` for an event class the logger does not
        accept, and ``RuntimeError`` if the logger has not been opened.
        """
        if isinstance(event, UnrecognizedEvent):
            raise UndeclaredEventType(
                f"Refusing to log an UnrecognizedEvent (event_type {event.event_type!r}): "
                "it is a line read back from a run's log, not an event of this run. A "
                "derived run keeps its source's lines through rewrite_run_jsonl instead."
            )
        event_cls = type(event)
        if event_cls not in self._allowed_event_types:
            raise UndeclaredEventType(
                f"Refusing to log {event_cls.__module__}.{event_cls.__qualname__} "
                f"(event_type {fixed_event_type(event_cls=event_cls)!r}): it is neither "
                "a platform event nor one the running scenario returns from "
                "event_types(), so a reader of this run would read it as an "
                "UnrecognizedEvent. Add it to the scenario's event_types()."
            )
        if self._file is None:
            raise RuntimeError("EventLogger is not open. Call open() first.")
        event_dict = event.model_dump(mode="json")
        data = orjson.dumps(event_dict) + b"\n"
        async with self._write_lock:
            await self._file.write(data)
            await self._file.flush()
        self._event_bus.publish(event=event_dict)

    async def close(self) -> None:
        """Close the underlying file handle if it is open and reset internal state."""
        if self._file is not None:
            await self._file.close()
            self._file = None
            logger.info("Event log closed: %s", self._log_path)
