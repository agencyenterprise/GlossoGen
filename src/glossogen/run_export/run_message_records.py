"""One run's channel messages, scored and ready to become table rows.

Reads the run's JSONL, which no other frame does. That is why the message table
is opt-in: the reports the other frames read are small, and an event log is not.
Messages are loaded one run at a time from inside the row generator, so a
500-run export holds one run's events at a time rather than all of them.

Only the two event types this table is built from are parsed, and a line that
fails validation is skipped. An export spanning a scenario's whole history reads
logs written against older versions of its events, and one of those no longer
validating must not cost the export every other run's messages. See
`message_event_scan`.

Text is the pristine text the sender composed, resolved through the same index
the surprisal metrics use, so a scenario that rewrites outgoing messages (veyru's
channel noise) does not make the exported text disagree with the scores computed
over it. What the channel actually delivered is kept beside it, because under a
transform the difference is the experiment.

The three per-message numbers are recomputed here rather than read from a report.
They are deterministic, stdlib-only, and defined per message, while a report
carries only their run-level mean. Surprisal (`perplexity`,
`english_ngram_surprisal`) is deliberately not among them: it needs the
`metrics-ml` extra, which a server that only browses runs does not install, and
an export that fails on a missing torch would be worse than one that omits a
column.
"""

from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.character_entropy import character_entropy_bits
from glossogen.evaluation.metric_core.gzip_compression import gzip_compression_ratio
from glossogen.evaluation.metric_core.pristine_text_index import (
    build_pristine_text_index,
    pristine_text_for,
)
from glossogen.run_export.message_event_scan import scan_message_events
from glossogen.run_export.message_repetition_sidecar import read_repetition_by_message_id
from glossogen.run_export.primary_channel_resolution import resolve_primary_channels
from glossogen.server.runs.models import RunSummary


class ExportMessage(NamedTuple):
    """One channel message, with everything the table reports about it."""

    round_number: int
    index_in_round: int
    channel_id: str
    is_primary: bool
    team_id: str
    message_id: str
    sender_agent_id: str
    sender_display_name: str
    timestamp: datetime
    text: str
    delivered_text: str
    chars: int
    character_entropy_bits: float
    gzip_compression_ratio: float
    repetition_factor: float | None


class RunMessages(NamedTuple):
    """A run's messages, and whether its primary channels could be resolved.

    When ``primary_resolved`` is False, every message's ``is_primary`` and
    ``team_id`` say nothing and the table leaves both cells empty.
    ``skipped_event_count`` is how many events in the log could not be parsed.
    """

    primary_resolved: bool
    messages: list[ExportMessage]
    skipped_event_count: int


def log_path_for(summary: RunSummary) -> Path:
    """Return where the run's JSONL event log lives on disk."""
    return Path(summary.run_dir) / f"{summary.scenario_name}.jsonl"


def load_run_messages(summary: RunSummary) -> RunMessages:
    """Read one run's messages off disk, scored and ordered as the table emits them."""
    scan = scan_message_events(log_path=log_path_for(summary=summary))
    pristine = build_pristine_text_index(events=scan.send_results)
    repetition = read_repetition_by_message_id(run_dir=Path(summary.run_dir))
    primary = resolve_primary_channels(
        scenario_name=summary.scenario_name,
        scenario_config=summary.scenario_config,
    )

    index_by_round_channel: dict[tuple[int, str], int] = {}
    messages: list[ExportMessage] = []
    for event in scan.messages:
        message = event.message
        key = (message.round_number, message.channel_id)
        index_by_round_channel[key] = index_by_round_channel.get(key, 0) + 1
        text = pristine_text_for(index=pristine, message=event)
        messages.append(
            ExportMessage(
                round_number=message.round_number,
                index_in_round=index_by_round_channel[key],
                channel_id=message.channel_id,
                is_primary=message.channel_id in primary.team_by_channel,
                team_id=primary.team_by_channel.get(message.channel_id, ""),
                message_id=message.message_id,
                sender_agent_id=message.sender_agent_id,
                sender_display_name=message.sender_display_name,
                timestamp=message.timestamp,
                text=text,
                delivered_text=message.text,
                chars=len(text),
                character_entropy_bits=character_entropy_bits(text=text),
                gzip_compression_ratio=gzip_compression_ratio(text=text),
                repetition_factor=repetition.get(message.message_id),
            )
        )
    return RunMessages(
        primary_resolved=primary.resolved,
        messages=messages,
        skipped_event_count=scan.skipped_count,
    )
