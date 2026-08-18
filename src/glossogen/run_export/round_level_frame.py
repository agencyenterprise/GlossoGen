"""The long table: one row per run, metric, and round observed.

Rows come from each measurement's per-round observations, and a metric emits an
observation only for the rounds it has something to say about. So a missing
`(run, metric, round)` row means no observation, not a zero. A metric that flags
occurrences has per-round data on a minority of runs, and filling the gaps with
zeros would turn "not seen" into "seen zero times".

`score_unit` is carried per row, not hoisted into a legend, because it is
not constant per metric across runs: a unit can name the size of the vocabulary
the metric scored against, and that changes when the vocabulary does.
"""

from collections.abc import Iterator

from glossogen.run_export.csv_cell_text import render_cell
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.metric_column_projection import measurements_by_name
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

ROUND_LEVEL_FRAME_NAME = "round_level"

OBSERVATION_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "score_unit",
    "round_number",
    "value",
    "note",
)


def round_level_header(columns: list[str], repeat_run_columns: bool) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.extend(OBSERVATION_COLUMNS)
    return header


def build_round_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    metrics: list[str],
    repeat_run_columns: bool,
) -> CsvFrame:
    """Build the one-row-per-round-observation table for the selected metrics."""
    wanted = list(metrics)

    def rows() -> Iterator[list[str]]:
        for record in records:
            if record.report is None:
                continue
            context = run_context_cells(record=record)
            prefix = [context.get(key, "") for key in IDENTITY_COLUMNS]
            if repeat_run_columns:
                prefix.extend(
                    context.get(key, "") for key in columns if key not in IDENTITY_COLUMNS
                )
            measurements = measurements_by_name(measurements=record.report.measurements)
            for name in wanted:
                measurement = measurements.get(name)
                if measurement is None:
                    continue
                for observation in measurement.per_round:
                    yield prefix + [
                        name,
                        render_cell(text=measurement.score_unit),
                        str(observation.round_number),
                        str(observation.value),
                        render_cell(text=observation.note),
                    ]

    return CsvFrame(
        name=ROUND_LEVEL_FRAME_NAME,
        header=round_level_header(columns=columns, repeat_run_columns=repeat_run_columns),
        rows=rows(),
    )
