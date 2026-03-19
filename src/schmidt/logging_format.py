"""JSON line formatter for Python's logging module.

Formats each log record as a single JSON line with timestamp, logger name,
level, and message fields. Used to write debug logs to a file in the run
directory for frontend display.
"""

import logging
from datetime import UTC, datetime

import orjson


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record to a JSON line."""
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        return orjson.dumps(entry).decode("utf-8")
