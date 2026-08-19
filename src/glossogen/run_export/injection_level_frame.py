"""The injection table: one row per briefing an agent was handed at a round boundary.

This is the per-round prompt, and it is half of what a round is: what the agent
knew going in, against what it then said on the channel. Without it a message
table shows the answers with the questions missing, and any read of why a round
went the way it did is guesswork.

A hand-written exporter carries this as one column per role on a per-round frame,
which needs the scenario's roles named in advance. One row per delivered
injection needs nothing named: the agent is a column, so a scenario with five
roles and one with two both land in the same shape, and a run whose roster
changed mid-flight is just more rows.

Kept out of the message table rather than joined onto it. An injection is not a
message and has no channel, and repeating a briefing on every message of its
round is what made the hand-written version split the frame in the first place.
Join on `run_id` + `round_number` + `agent_id`.
"""

import logging
from collections.abc import Iterator

from glossogen.run_export.agent_identity_columns import agent_model_by_id
from glossogen.run_export.csv_cell_text import render_cell
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_message_records import load_run_injections
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

logger = logging.getLogger(__name__)

INJECTION_LEVEL_FRAME_NAME = "injection_level"

INJECTION_COLUMNS: tuple[str, ...] = (
    "round_number",
    "agent_id",
    "agent_role",
    "agent_model",
    "agent_provider",
    "injection_index_in_round",
    "chars",
    "text",
)


def injection_level_header(columns: list[str], repeat_run_columns: bool) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.extend(INJECTION_COLUMNS)
    return header


def build_injection_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    repeat_run_columns: bool,
) -> CsvFrame:
    """Build the one-row-per-injection table.

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
                injections = load_run_injections(summary=record.summary)
            except OSError:
                logger.exception(
                    "Could not read the event log for %s; exporting the other runs' injections",
                    record.summary.run_id,
                )
                continue
            for injection in injections:
                agent = roster.get(injection.agent_id)
                role = ""
                model = ""
                provider = ""
                if agent is not None:
                    role = agent.role_name
                    model = agent.model
                    provider = agent.provider
                yield prefix + [
                    str(injection.round_number),
                    render_cell(text=injection.agent_id),
                    render_cell(text=role),
                    render_cell(text=model),
                    render_cell(text=provider),
                    str(injection.index_in_round),
                    str(injection.chars),
                    render_cell(text=injection.text),
                ]

    return CsvFrame(
        name=INJECTION_LEVEL_FRAME_NAME,
        header=injection_level_header(columns=columns, repeat_run_columns=repeat_run_columns),
        rows=rows(),
    )
