"""The message table: one row per channel message, with what it said and how it reads.

The finest observation a run holds, and the one a language study is actually
about. The other three tables aggregate it: `mean_chars_per_message` is the mean
of the `chars` column, `language_repetition` the mean of `repetition_factor`.
Having the rows means a distribution can be looked at instead of a mean, and a
message can be read next to its own numbers.

Every channel is exported, not only the primary one, with `channel_id` and
`is_primary` to filter on. A scenario's other channels carry the coordination
that explains what happened on the budgeted one (veyru's postmortem is where a
protocol gets agreed), so dropping them would decide for the reader what counts
as data.

`team_id` is on these rows even though a `Measurement` has no such field: the
scenario's primary-channel declaration ties a channel to a team, so at message
level the team is known without parsing it back out of a metric name.
"""

import logging
from collections.abc import Iterator

from glossogen.run_export.agent_identity_columns import agent_model_by_id
from glossogen.run_export.csv_cell_text import render_cell, render_number
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_message_records import ExportMessage, load_run_messages
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

logger = logging.getLogger(__name__)

MESSAGE_LEVEL_FRAME_NAME = "message_level"

MESSAGE_COLUMNS: tuple[str, ...] = (
    "round_number",
    "channel_id",
    "is_primary_channel",
    "team_id",
    "message_index_in_round",
    "message_id",
    "sender_agent_id",
    "sender_role",
    "sender_model",
    "sender_provider",
    "sender_display_name",
    "timestamp",
    "chars",
    "character_entropy_bits",
    "gzip_compression_ratio",
    "repetition_factor",
    "text",
    "delivered_text",
)


# The numeric columns a reader needs a unit for. The rest are identifiers or
# text, where the column name is the whole story.
MESSAGE_COLUMN_UNITS: dict[str, str] = {
    "chars": "characters",
    "character_entropy_bits": "bits/char (lower = more repetitive)",
    "gzip_compression_ratio": "compressed/original bytes (lower = more compressible)",
    "repetition_factor": "encodings per information unit (x; 1.0 = no repetition)",
}


def message_level_header(columns: list[str], repeat_run_columns: bool) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.extend(MESSAGE_COLUMNS)
    return header


def _message_cells(
    message: ExportMessage,
    primary_resolved: bool,
    role: str,
    model: str,
    provider: str,
) -> list[str]:
    """Render one message's own columns."""
    is_primary = ""
    team_id = ""
    if primary_resolved:
        is_primary = str(message.is_primary)
        team_id = render_cell(text=message.team_id)
    return [
        str(message.round_number),
        render_cell(text=message.channel_id),
        is_primary,
        team_id,
        str(message.index_in_round),
        render_cell(text=message.message_id),
        render_cell(text=message.sender_agent_id),
        render_cell(text=role),
        render_cell(text=model),
        render_cell(text=provider),
        render_cell(text=message.sender_display_name),
        message.timestamp.isoformat(),
        str(message.chars),
        render_number(value=message.character_entropy_bits),
        render_number(value=message.gzip_compression_ratio),
        render_number(value=message.repetition_factor),
        render_cell(text=message.text),
        render_cell(text=message.delivered_text),
    ]


def build_message_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    repeat_run_columns: bool,
) -> CsvFrame:
    """Build the one-row-per-message table.

    Each run's event log is read as its rows are emitted, so only one run's
    events are held at a time.
    """

    def rows() -> Iterator[list[str]]:
        for record in records:
            roster = agent_model_by_id(agent_models=record.summary.agent_models)
            context = run_context_cells(record=record)
            prefix = [context.get(key, "") for key in IDENTITY_COLUMNS]
            if repeat_run_columns:
                prefix.extend(
                    context.get(key, "") for key in columns if key not in IDENTITY_COLUMNS
                )
            try:
                run_messages = load_run_messages(summary=record.summary)
            except OSError:
                logger.exception(
                    "Could not read the event log for %s; exporting the other runs' messages",
                    record.summary.run_id,
                )
                continue
            for message in run_messages.messages:
                agent = roster.get(message.sender_agent_id)
                role = ""
                model = ""
                provider = ""
                if agent is not None:
                    role = agent.role_name
                    model = agent.model
                    provider = agent.provider
                yield prefix + _message_cells(
                    message=message,
                    primary_resolved=run_messages.primary_resolved,
                    role=role,
                    model=model,
                    provider=provider,
                )

    return CsvFrame(
        name=MESSAGE_LEVEL_FRAME_NAME,
        header=message_level_header(columns=columns, repeat_run_columns=repeat_run_columns),
        rows=rows(),
    )
