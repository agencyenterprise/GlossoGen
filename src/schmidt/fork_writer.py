"""Writes a truncated and edited JSONL event log for a forked simulation run.

Copies events from the source log up to a target message, optionally
replacing message text for specified message IDs. The resulting file is a
self-contained event log that can be used with ``--resume`` to continue the
simulation from that point.
"""

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import orjson

from schmidt.models.event import MessageSent, SimulationEvent, SimulationStarted

logger = logging.getLogger(__name__)


class ForkLogResult:
    """Result of writing a forked event log."""

    def __init__(self, events_written: int, fork_run_id: str) -> None:
        self.events_written = events_written
        self.fork_run_id = fork_run_id


def write_fork_log(
    source_events: list[SimulationEvent],
    target_message_id: str,
    message_edits: dict[str, str],
    output_path: Path,
) -> ForkLogResult:
    """Write a truncated JSONL log with optional message text edits.

    The first ``SimulationStarted`` event gets a new ``event_id`` so the
    forked run has a unique identity distinguishable from the source.

    Args:
        source_events: Full event list from the source simulation.
        target_message_id: Stop copying after (and including) the
            ``MessageSent`` event with this message ID.
        message_edits: Mapping of ``message_id`` to replacement text.
        output_path: Path to write the new JSONL file.

    Returns:
        A ``ForkLogResult`` with the number of events written and the new run ID.

    Raises:
        ValueError: If no ``MessageSent`` with ``target_message_id`` exists.
    """
    target_timestamp = _find_target_timestamp(
        events=source_events,
        target_message_id=target_message_id,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    fork_run_id = str(uuid4())

    with open(output_path, "wb") as f:
        for event in source_events:
            if event.timestamp > target_timestamp:
                break

            event_dict = event.model_dump(mode="json")

            if isinstance(event, SimulationStarted):
                event_dict["run_id"] = fork_run_id

            if isinstance(event, MessageSent) and event.message.message_id in message_edits:
                event_dict["message"]["text"] = message_edits[event.message.message_id]

            f.write(orjson.dumps(event_dict) + b"\n")
            written += 1

    logger.info(
        "Fork log written: %d events (run_id=%s) to %s",
        written,
        fork_run_id,
        output_path,
    )
    return ForkLogResult(events_written=written, fork_run_id=fork_run_id)


def _find_target_timestamp(
    events: list[SimulationEvent],
    target_message_id: str,
) -> datetime:
    """Find the timestamp of the MessageSent event with the given message_id.

    Raises ``ValueError`` if no matching event exists.
    """
    for event in events:
        if isinstance(event, MessageSent) and event.message.message_id == target_message_id:
            return event.timestamp

    raise ValueError(
        f"No MessageSent event with message_id={target_message_id!r} found in the log."
    )
