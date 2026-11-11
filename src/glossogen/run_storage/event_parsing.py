"""Shared event parsing for JSONL log readers.

Provides ``parse_event`` and ``parse_event_bytes`` so all JSONL consumers
use the same deserialization path.

``round_number`` is required on every event but older JSONL logs predate
its promotion to ``EventBase`` and lack it on lifecycle events. When
parsing a single event in isolation (e.g. the first/last line of a log)
we default missing ``round_number`` to ``0``. Readers that walk a whole log
pass each line through ``RoundNumberBackfill`` first, which tracks the running
round across the file and backfills with the correct value.
"""

from typing import Any

import orjson

from glossogen.models.event import SIMULATION_EVENT_ADAPTER, SimulationEvent

EVENT_ADAPTER = SIMULATION_EVENT_ADAPTER


class RoundNumberBackfill:
    """Gives each event of a legacy log the round it was emitted in.

    Logs written before ``round_number`` was promoted to ``EventBase`` omit it.
    Walking the log in order, the round an event belongs to is the one most
    recently opened by a ``round_advanced``, and ``0`` before the first. One
    instance covers one pass over one log.
    """

    def __init__(self) -> None:
        self._running_round = 0

    def observe(self, record: dict[str, Any]) -> None:
        """Advance the running round when ``record`` is a ``round_advanced`` with an integer one."""
        if record.get("event_type") == "round_advanced":
            advanced = record.get("round_number")
            if isinstance(advanced, int):
                self._running_round = advanced

    def apply(self, record: dict[str, Any]) -> dict[str, Any]:
        """Observe ``record``, then return it with ``round_number`` set when it had none.

        A record that already carries one is returned as it is; one that lacks it
        is copied, so the caller's dict is never changed.
        """
        self.observe(record=record)
        if "round_number" in record:
            return record
        return {**record, "round_number": self._running_round}


def parse_event(raw: dict[str, Any]) -> SimulationEvent:
    """Validate a raw event dict into a typed SimulationEvent.

    Backfills two fields that older JSONL logs may omit:

    - the event's own ``round_number`` (promoted to ``EventBase`` after the
      original schema), defaulted to ``0`` for lifecycle events when missing;
    - the ``round_number`` on the nested ``message`` of a ``message_sent``
      event, defaulted to the parent event's ``round_number`` when missing.

    Single-event callers should rely on this default; full-log loaders that
    track the running round across the file (e.g.
    ``glossogen.run_storage.event_log_reader.load_events``) overwrite ``round_number``
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
