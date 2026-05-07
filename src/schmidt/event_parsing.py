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
    """Validate a raw event dict into a typed SimulationEvent.

    Backfills two fields that older JSONL logs may omit:

    - the event's own ``round_number`` (promoted to ``EventBase`` after the
      original schema), defaulted to ``0`` for lifecycle events when missing;
    - the ``round_number`` on the nested ``message`` of a ``message_sent``
      event, defaulted to the parent event's ``round_number`` when missing.

    Single-event callers should rely on this default; full-log loaders that
    track the running round across the file (e.g.
    ``schmidt.evaluation.log_reader.load_events``) overwrite ``round_number``
    with the round most recently advanced before the event.
    """
    if "round_number" not in raw:
        raw = {**raw, "round_number": 0}
    if raw.get("event_type") == "message_sent":
        message = raw.get("message")
        if isinstance(message, dict) and "round_number" not in message:
            raw = {**raw, "message": {**message, "round_number": raw["round_number"]}}
    return EVENT_ADAPTER.validate_python(raw)


def parse_event_bytes(raw_bytes: bytes) -> SimulationEvent:
    """Parse raw JSON bytes into a typed SimulationEvent."""
    raw = orjson.loads(raw_bytes)
    return parse_event(raw=raw)
