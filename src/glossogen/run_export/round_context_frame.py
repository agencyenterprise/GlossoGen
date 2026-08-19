"""The round-context table: one row per run and round, one column per agent's briefing.

The shape a hand-written exporter produces, generically. Research carries the
round-start briefing as `field_observer_round_event` and `engineer_round_event`,
named per scenario; here the columns are `injection.<agent_id>`, built from the
roster each run recorded. A sheet reading one agent's briefing finds it in a
column rather than having to pivot a per-injection table to get there.

Round-start and postmortem briefings are separate column families rather than two
values sharing a cell. The event does not say which phase delivered it, so the
scan tracks the phase across the log: measured here, every `(round, agent)` cell
carries exactly one of each, so `injection.<agent_id>` is the round-start
briefing and nothing else, which is what the research column holds.

Kept out of `round_level.csv` even though both are keyed on `(run, round)`. These
cells are the largest text in the export, and a table people join to and filter
on should not carry them: repeating them was ~86% of a file in the exporter this
mirrors. Join on `run_id` + `round_number`.

The columns come from the rosters, which are on the run summaries, so the header
is known before any log is opened. A briefing for an agent id no roster carries
would have no column, so it is counted and logged rather than dropped in silence.
"""

import logging
from collections.abc import Iterator

from glossogen.run_export.agent_identity_columns import agent_model_by_id
from glossogen.run_export.csv_cell_text import render_cell
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_message_records import ExportInjection, load_run_injections
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

logger = logging.getLogger(__name__)

ROUND_CONTEXT_FRAME_NAME = "round_context"

ROUND_NUMBER_COLUMN = "round_number"
INJECTION_COLUMN_PREFIX = "injection."
POSTMORTEM_INJECTION_COLUMN_PREFIX = "postmortem_injection."

# Two briefings in one phase would otherwise overwrite each other. Not observed
# in any run here, so this is the answer to a question the data has not asked.
_MULTIPLE_IN_PHASE_SEPARATOR = " || "


def agent_ids_in(records: list[ExportRunRecord]) -> list[str]:
    """Return every agent id the selection's rosters carry, sorted."""
    ids: set[str] = set()
    for record in records:
        ids.update(agent_model_by_id(agent_models=record.summary.agent_models))
    return sorted(ids)


def round_context_header(
    columns: list[str],
    agent_ids: list[str],
    repeat_run_columns: bool,
) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.append(ROUND_NUMBER_COLUMN)
    header.extend(f"{INJECTION_COLUMN_PREFIX}{agent_id}" for agent_id in agent_ids)
    header.extend(f"{POSTMORTEM_INJECTION_COLUMN_PREFIX}{agent_id}" for agent_id in agent_ids)
    return header


def _cells_by_round(
    injections: list[ExportInjection],
    run_id: str,
) -> dict[int, dict[str, str]]:
    """Group a run's injections into one cell per round, agent, and phase."""
    by_round: dict[int, dict[str, str]] = {}
    for injection in injections:
        prefix = INJECTION_COLUMN_PREFIX
        if injection.in_postmortem:
            prefix = POSTMORTEM_INJECTION_COLUMN_PREFIX
        column = f"{prefix}{injection.agent_id}"
        cells = by_round.setdefault(injection.round_number, {})
        text = render_cell(text=injection.text)
        if column in cells:
            logger.info(
                "%s delivered more than one %s injection to %s in round %d; joining them",
                run_id,
                prefix.rstrip("."),
                injection.agent_id,
                injection.round_number,
            )
            cells[column] = f"{cells[column]}{_MULTIPLE_IN_PHASE_SEPARATOR}{text}"
            continue
        cells[column] = text
    return by_round


def build_round_context_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    repeat_run_columns: bool,
) -> CsvFrame:
    """Build the one-row-per-round table of the briefings each agent was given.

    Each run's event log is read as its rows are emitted, so only one run's
    events are held at a time.
    """
    agent_ids = agent_ids_in(records=records)
    injection_columns = [f"{INJECTION_COLUMN_PREFIX}{agent_id}" for agent_id in agent_ids]
    injection_columns.extend(
        f"{POSTMORTEM_INJECTION_COLUMN_PREFIX}{agent_id}" for agent_id in agent_ids
    )
    known = set(injection_columns)

    def rows() -> Iterator[list[str]]:
        for record in records:
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
                    "Could not read the event log for %s; exporting the other runs' briefings",
                    record.summary.run_id,
                )
                continue
            by_round = _cells_by_round(injections=injections, run_id=record.summary.run_id)
            for round_number in sorted(by_round):
                cells = by_round[round_number]
                unknown = set(cells) - known
                if unknown:
                    logger.warning(
                        "%s briefed %s in round %d, which its roster does not carry, so those "
                        "briefings have no column",
                        record.summary.run_id,
                        ", ".join(sorted(unknown)),
                        round_number,
                    )
                yield (
                    prefix
                    + [str(round_number)]
                    + [cells.get(column, "") for column in injection_columns]
                )

    return CsvFrame(
        name=ROUND_CONTEXT_FRAME_NAME,
        header=round_context_header(
            columns=columns,
            agent_ids=agent_ids,
            repeat_run_columns=repeat_run_columns,
        ),
        rows=rows(),
    )
