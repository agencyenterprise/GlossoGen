"""Reading the few event types the log-backed tables need, and tolerating every other.

The other frames read evaluation reports, which are small and written by this
version of the code. This one reads event logs, which are large and were written
by whatever version was current when the run happened. Those two facts change
what a reader has to survive.

A run recorded before a scenario event gained a required field no longer
validates against today's model. Parsing every line through the full event union
therefore fails an export of old runs on an event these tables would have thrown
away: a `container_yard_case_started` missing a field says nothing about any
message. Only the event types they are built from are validated, and a line that
fails is counted and skipped rather than raised.

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
from typing import NamedTuple

from glossogen.models.event import (
    ChannelCreated,
    InjectionDelivered,
    MessageSent,
    SimulationEvent,
    ToolResultReceived,
)
from glossogen.run_storage.event_parsing import RoundNumberBackfill, parse_event
from glossogen.run_storage.jsonl_lines import MalformedLine, iter_json_objects_skipping_malformed

logger = logging.getLogger(__name__)

_WANTED_EVENT_TYPES = frozenset(
    {"message_sent", "tool_result_received", "injection_delivered", "channel_created"}
)
_ROUND_ADVANCED = "round_advanced"
_POSTMORTEM_STARTED = "postmortem_started"


class ScannedInjection(NamedTuple):
    """One delivered injection, and which phase of its round delivered it.

    A round briefs its agents at the start and, in scenarios that run one, again
    for the postmortem. The event itself does not say which, so the phase is
    tracked across the file from ``postmortem_started`` and reset on each
    ``round_advanced``. That is what lets the round-start briefing be its own
    column instead of two different prompts sharing one cell.
    """

    event: InjectionDelivered
    in_postmortem: bool


class MessageEventScan(NamedTuple):
    """One run's messages, injections, the tool results carrying pristine text, and what dropped.

    ``send_results`` are ``ToolResultReceived`` events, handed to the pristine
    text index as-is. ``created_channels`` are the channels the run created, such
    as direct channels, which a primary channel can include. ``skipped_count`` is
    how many wanted lines failed to validate, which is zero for any run written
    by a current version.
    """

    messages: list[MessageSent]
    send_results: list[SimulationEvent]
    injections: list[ScannedInjection]
    created_channels: list[ChannelCreated]
    skipped_count: int


def scan_message_events(log_path: Path) -> MessageEventScan:
    """Read ``log_path`` and return only the events the log-backed tables are built from."""
    messages: list[MessageSent] = []
    send_results: list[SimulationEvent] = []
    injections: list[ScannedInjection] = []
    created_channels: list[ChannelCreated] = []
    skipped = 0
    round_numbers = RoundNumberBackfill()
    in_postmortem = False

    def count_malformed(_line: MalformedLine) -> None:
        nonlocal skipped
        skipped += 1

    with open(log_path, mode="rb") as handle:
        for record in iter_json_objects_skipping_malformed(
            lines=handle, on_malformed=count_malformed
        ):
            event_type = record.get("event_type")
            if event_type == _ROUND_ADVANCED:
                round_numbers.observe(record=record)
                in_postmortem = False
                continue
            if event_type == _POSTMORTEM_STARTED:
                in_postmortem = True
                continue
            if event_type not in _WANTED_EVENT_TYPES:
                continue
            try:
                event = parse_event(raw=round_numbers.apply(record=record))
            except Exception:
                skipped += 1
                continue
            if isinstance(event, MessageSent):
                messages.append(event)
            elif isinstance(event, ToolResultReceived):
                send_results.append(event)
            elif isinstance(event, InjectionDelivered):
                injections.append(ScannedInjection(event=event, in_postmortem=in_postmortem))
            elif isinstance(event, ChannelCreated):
                created_channels.append(event)

    if skipped > 0:
        logger.warning("Skipped %d unparseable event(s) in %s", skipped, log_path)
    return MessageEventScan(
        messages=messages,
        send_results=send_results,
        injections=injections,
        created_channels=created_channels,
        skipped_count=skipped,
    )
