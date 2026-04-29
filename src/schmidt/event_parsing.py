"""Shared event parsing for JSONL log readers.

Provides ``parse_event`` and ``parse_event_bytes`` so all JSONL consumers
use the same deserialization path.

``round_number`` is required on every event but older JSONL logs predate
its promotion to ``EventBase`` and lack it on lifecycle events. When
parsing a single event in isolation (e.g. the first/last line of a log)
we default missing ``round_number`` to ``0``; full-log loaders should
use ``schmidt.evaluation.log_reader.load_events`` instead, which tracks
the running round across the file and backfills with the correct value.
"""

from typing import Any

import orjson
from pydantic import TypeAdapter

from schmidt.models.event import SimulationEvent

EVENT_ADAPTER: TypeAdapter[SimulationEvent] = TypeAdapter(SimulationEvent)


def parse_event(raw: dict[str, Any]) -> SimulationEvent:
    """Validate a raw event dict into a typed SimulationEvent."""
    if "round_number" not in raw:
        raw = {**raw, "round_number": 0}
    return EVENT_ADAPTER.validate_python(raw)


def parse_event_bytes(raw_bytes: bytes) -> SimulationEvent:
    """Parse raw JSON bytes into a typed SimulationEvent."""
    raw = orjson.loads(raw_bytes)
    return parse_event(raw=raw)
