"""Shared event parsing for JSONL log readers.

Provides ``parse_event`` and ``parse_event_bytes`` so all JSONL consumers
use the same deserialization path.
"""

from typing import Any

import orjson
from pydantic import TypeAdapter

from schmidt.models.event import SimulationEvent

EVENT_ADAPTER: TypeAdapter[SimulationEvent] = TypeAdapter(SimulationEvent)


def parse_event(raw: dict[str, Any]) -> SimulationEvent:
    """Validate a raw event dict into a typed SimulationEvent."""
    return EVENT_ADAPTER.validate_python(raw)


def parse_event_bytes(raw_bytes: bytes) -> SimulationEvent:
    """Parse raw JSON bytes into a typed SimulationEvent."""
    raw = orjson.loads(raw_bytes)
    return parse_event(raw=raw)
