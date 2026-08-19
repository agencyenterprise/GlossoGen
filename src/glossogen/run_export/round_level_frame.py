"""The per-round table: one row per run and round, one column per metric.

A round is the observation and a metric is a variable, so `metric.perplexity`
and `metric.round_success` sit on the same row as columns. That row is a design
matrix row: `lmer(metric.perplexity ~ knob.round_time_budget_seconds + (1|run_id))`
reads it with no reshaping. Carrying the metric name in a column instead would
make every analysis start with a pivot.

A row exists for a `(run, round)` only when at least one selected metric reported
that round, so an absent row still means no observation rather than a zero. Within
a row, a metric that said nothing about the round leaves its cell empty, which is
the same claim written the other way. Nothing is ever filled with `0`.

`score_unit` is not on these rows. It is not constant per metric across runs (a
unit can name the size of the vocabulary the metric scored against, which changes
when the vocabulary does), and a wide row has no per-cell place to put it. It is
in the `columns.csv` legend, from the first run in the selection that carries the
metric, and on the run-level table under `metric_unit.<name>`.
"""

from collections.abc import Iterator

from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.metric_column_projection import (
    METRIC_COLUMN_PREFIX,
    METRIC_NOTE_COLUMN_PREFIX,
    measurements_by_name,
    observation_note_cell,
    observation_value_cell,
    rounds_by_number,
)
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

ROUND_LEVEL_FRAME_NAME = "round_level"

ROUND_NUMBER_COLUMN = "round_number"


def round_level_header(
    columns: list[str],
    metrics: list[str],
    repeat_run_columns: bool,
    include_metric_summaries: bool,
) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.append(ROUND_NUMBER_COLUMN)
    header.extend(f"{METRIC_COLUMN_PREFIX}{name}" for name in metrics)
    if include_metric_summaries:
        header.extend(f"{METRIC_NOTE_COLUMN_PREFIX}{name}" for name in metrics)
    return header


def build_round_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    metrics: list[str],
    repeat_run_columns: bool,
    include_metric_summaries: bool,
) -> CsvFrame:
    """Build the one-row-per-round table for the selected metrics."""
    wanted = list(metrics)

    def rows() -> Iterator[list[str]]:
        for record in records:
            if record.report is None:
                continue
            measurements = measurements_by_name(measurements=record.report.measurements)
            observed = {
                name: rounds_by_number(measurement=measurements[name])
                for name in wanted
                if name in measurements
            }
            round_numbers = sorted(
                {number for by_round in observed.values() for number in by_round}
            )
            if not round_numbers:
                continue

            context = run_context_cells(record=record)
            prefix = [context.get(key, "") for key in IDENTITY_COLUMNS]
            if repeat_run_columns:
                prefix.extend(
                    context.get(key, "") for key in columns if key not in IDENTITY_COLUMNS
                )

            for round_number in round_numbers:
                row = prefix + [str(round_number)]
                row.extend(
                    observation_value_cell(observation=observed.get(name, {}).get(round_number))
                    for name in wanted
                )
                if include_metric_summaries:
                    row.extend(
                        observation_note_cell(observation=observed.get(name, {}).get(round_number))
                        for name in wanted
                    )
                yield row

    return CsvFrame(
        name=ROUND_LEVEL_FRAME_NAME,
        header=round_level_header(
            columns=columns,
            metrics=metrics,
            repeat_run_columns=repeat_run_columns,
            include_metric_summaries=include_metric_summaries,
        ),
        rows=rows(),
    )
