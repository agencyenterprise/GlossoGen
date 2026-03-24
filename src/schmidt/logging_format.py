"""JSON line formatter and EventBus log handler for Python's logging module.

Provides ``JsonLineFormatter`` for writing debug logs as JSON lines to a file,
and ``EventBusLogHandler`` for publishing log records to the EventBus so the
frontend can display them in real time via SSE.
"""

import logging
import traceback
from datetime import UTC, datetime

import orjson

from schmidt.event_bus import EventBus
from schmidt.server.streaming_event import DebugLogEmitted


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to a JSON line, including exception tracebacks."""
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            tb_lines = traceback.format_exception(*record.exc_info)
            message = message + "\n" + "".join(tb_lines).rstrip()
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "message": message,
        }
        return orjson.dumps(entry).decode("utf-8")


class EventBusLogHandler(logging.Handler):
    """Logging handler that publishes each log record to an EventBus.

    Emits ``DebugLogEmitted`` events so the simulation's embedded server
    can stream debug logs to the frontend in real time.
    """

    def __init__(self, event_bus: EventBus) -> None:
        """Create a handler that publishes to the given event bus."""
        super().__init__()
        self._event_bus = event_bus

    def emit(self, record: logging.LogRecord) -> None:
        """Publish a log record to the event bus as a DebugLogEmitted event."""
        event = DebugLogEmitted(
            timestamp=datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            logger_name=record.name,
            level=record.levelname,
            message=record.getMessage(),
        )
        self._event_bus.publish(event=event.model_dump(mode="json"))
