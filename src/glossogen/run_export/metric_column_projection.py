"""Evaluator scores as columns, and the rule for a cell with no number.

The column set is the union of the metric names the selected runs' reports
actually carry, not a registry of known metrics. A metric can emit names other
than its own (round success emits one per team; a scenario's dialog metric emits
two counts of its own), and a resume metric emits a name built at run time from
the round and agent it scored. Reading the names off the data is the only thing
that covers all of that.

**An empty cell is not a zero.** A missing measurement means no number exists,
which happens three ways: the metric decided it did not apply to this run and
returned nothing, the metric was never run on this run, or the run has no report
at all. A present measurement whose score is `0.0` means the opposite: the metric
ran and counted zero, which is a real observation for the metrics that count
occurrences.

Defaulting a missing metric to `0` would merge those into one number and quietly
bias any average taken over the column. The three-way distinction is recoverable
from other columns: `has_evaluation` separates "no report" from "report without
this metric", and the export preview reports which runs had no report.
"""

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.run_export.csv_cell_text import render_cell

METRIC_COLUMN_PREFIX = "metric."
METRIC_SUMMARY_COLUMN_PREFIX = "metric_summary."
METRIC_UNIT_COLUMN_PREFIX = "metric_unit."


def measurements_by_name(measurements: list[Measurement]) -> dict[str, Measurement]:
    """Index a report's measurements by metric name, keeping the first of each."""
    indexed: dict[str, Measurement] = {}
    for measurement in measurements:
        if measurement.metric_name in indexed:
            continue
        indexed[measurement.metric_name] = measurement
    return indexed


def metric_score_cell(measurement: Measurement | None) -> str:
    """Render a metric's score, or empty when the run carries no such measurement.

    Empty means no number exists. It is never rendered as ``0``.
    """
    if measurement is None:
        return ""
    return str(measurement.score)


def metric_summary_cell(measurement: Measurement | None) -> str:
    """Render a metric's one-line rollup, or empty when there is no measurement."""
    if measurement is None:
        return ""
    return render_cell(text=measurement.summary)


def metric_unit_cell(measurement: Measurement | None) -> str:
    """Render a metric's score unit, or empty when there is no measurement."""
    if measurement is None:
        return ""
    return render_cell(text=measurement.score_unit)
