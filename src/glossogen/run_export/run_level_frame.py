"""The wide table: one row per run.

Columns are the run's context (metadata, knobs, labels, agents, lineage) followed
by one score column per selected metric. This is the table a regression is run
on, so the identity columns lead and the requested columns follow in the order
they were asked for.
"""

from collections.abc import Iterator

from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.metric_column_projection import (
    METRIC_COLUMN_PREFIX,
    METRIC_SUMMARY_COLUMN_PREFIX,
    METRIC_UNIT_COLUMN_PREFIX,
    measurements_by_name,
    metric_score_cell,
    metric_summary_cell,
    metric_unit_cell,
)
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

RUN_LEVEL_FRAME_NAME = "run_level"


def run_level_header(
    columns: list[str],
    metrics: list[str],
    include_metric_summaries: bool,
) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.extend(f"{METRIC_COLUMN_PREFIX}{name}" for name in metrics)
    if include_metric_summaries:
        header.extend(f"{METRIC_UNIT_COLUMN_PREFIX}{name}" for name in metrics)
        header.extend(f"{METRIC_SUMMARY_COLUMN_PREFIX}{name}" for name in metrics)
    return header


def _row(
    record: ExportRunRecord,
    columns: list[str],
    metrics: list[str],
    include_metric_summaries: bool,
) -> list[str]:
    """Render one run's row."""
    context = run_context_cells(record=record)
    measurements = {}
    if record.report is not None:
        measurements = measurements_by_name(measurements=record.report.measurements)

    row = [context.get(key, "") for key in IDENTITY_COLUMNS]
    row.extend(context.get(key, "") for key in columns if key not in IDENTITY_COLUMNS)
    row.extend(metric_score_cell(measurement=measurements.get(name)) for name in metrics)
    if include_metric_summaries:
        row.extend(metric_unit_cell(measurement=measurements.get(name)) for name in metrics)
        row.extend(metric_summary_cell(measurement=measurements.get(name)) for name in metrics)
    return row


def build_run_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    metrics: list[str],
    include_metric_summaries: bool,
) -> CsvFrame:
    """Build the one-row-per-run table."""

    def rows() -> Iterator[list[str]]:
        for record in records:
            yield _row(
                record=record,
                columns=columns,
                metrics=metrics,
                include_metric_summaries=include_metric_summaries,
            )

    return CsvFrame(
        name=RUN_LEVEL_FRAME_NAME,
        header=run_level_header(
            columns=columns,
            metrics=metrics,
            include_metric_summaries=include_metric_summaries,
        ),
        rows=rows(),
    )
