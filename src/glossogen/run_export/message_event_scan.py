"""Reading the two event types the message table needs, and tolerating every other.

The other frames read evaluation reports, which are small and written by this
version of the code. This one reads event logs, which are large and were written
by whatever version was current when the run happened. Those two facts change
what a reader has to survive.

A run recorded before a scenario event gained a required field no longer
validates against today's model. Parsing every line through the full event union
therefore fails an export of old runs on an event the message table would have
thrown away: a `container_yard_case_started` missing a field says nothing about
any message. Only `message_sent` and `tool_result_received` are validated, and a
line that fails is counted and skipped rather than raised.

Skipping is safe here in a way it is not for evaluation. A dropped message is a
missing row in a table whose rows are messages, and the count is logged. A
metric silently scoring a run with messages missing would report a number that
looks the same as a correct one.

`round_number` is backfilled the way the full loader does it, by tracking the
most recent `round_advanced` across the file, since logs predating its promotion
to `EventBase` omit it.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, cast

import orjson

from glossogen.event_parsing import parse_event
from glossogen.models.event import MessageSent, SimulationEvent, ToolResultReceived

logger = logging.getLogger(__name__)

_WANTED_EVENT_TYPES = frozenset({"message_sent", "tool_result_received"})
_ROUND_ADVANCED = "round_advanced"


class MessageEventScan(NamedTuple):
    """One run's message events, the tool results that carry pristine text, and what was dropped.

    ``send_results`` are ``ToolResultReceived`` events, handed to the pristine
    text index as-is. ``skipped_count`` is how many wanted lines failed to
    validate, which is zero for any run written by a current version.
    """

    messages: list[MessageSent]
    send_results: list[SimulationEvent]
    skipped_count: int


def scan_message_events(log_path: Path) -> MessageEventScan:
    """Read ``log_path`` and return only the events the message table is built from."""
    messages: list[MessageSent] = []
    send_results: list[SimulationEvent] = []
    skipped = 0
    running_round = 0

    with open(log_path, mode="rb") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = orjson.loads(stripped)
            except orjson.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(raw, dict):
                skipped += 1
                continue
            event_raw = cast(dict[str, Any], raw)
            event_type = event_raw.get("event_type")
            if event_type == _ROUND_ADVANCED:
                advanced = event_raw.get("round_number")
                if isinstance(advanced, int):
                    running_round = advanced
                continue
            if event_type not in _WANTED_EVENT_TYPES:
                continue
            if "round_number" not in event_raw:
                event_raw = {**event_raw, "round_number": running_round}
            try:
                event = parse_event(raw=event_raw)
            except Exception:
                skipped += 1
                continue
            if isinstance(event, MessageSent):
                messages.append(event)
            elif isinstance(event, ToolResultReceived):
                send_results.append(event)

    if skipped > 0:
        logger.warning(
            "Skipped %d unparseable message or tool-result event(s) in %s", skipped, log_path
        )
    return MessageEventScan(messages=messages, send_results=send_results, skipped_count=skipped)
