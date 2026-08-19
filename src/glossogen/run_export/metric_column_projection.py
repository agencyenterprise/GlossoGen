"""Evaluator scores as columns, and the rule for a cell with no number.

The column set is the union of the metric names the selected runs' reports
actually carry, not a registry of known metrics. A metric can emit names other
than its own (round success emits one per team; a scenario's dialog metric emits
two counts of its own), and a resume metric emits a name built at run time from
the round and agent it scored. Reading the names off the data is the only thing
that covers all of that.

Every table spends one column per metric, so a metric is a variable and never a
value in a `metric_name` column. That is what lets a round row be regressed
directly instead of pivoted first.

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

`metric_rounds.<name>` is the denominator that makes a fraction readable. A
`round_success` of `0.4667` is a different claim over 15 rounds than over 3, and
the counts behind it were previously legible only inside the unit string
`fraction of rounds succeeded (7/15)`. The numerator is the score times the
count for a fraction metric, and every per-round value is on the round table.
"""

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.run_export.csv_cell_text import render_cell, render_number

METRIC_COLUMN_PREFIX = "metric."
METRIC_SUMMARY_COLUMN_PREFIX = "metric_summary."
METRIC_UNIT_COLUMN_PREFIX = "metric_unit."
METRIC_NOTE_COLUMN_PREFIX = "metric_note."
METRIC_ROUNDS_COLUMN_PREFIX = "metric_rounds."


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
    return render_number(value=measurement.score)


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


def metric_round_count_cell(measurement: Measurement | None) -> str:
    """Render how many rounds a metric reported, or empty when it has no measurement.

    ``0`` here means the metric produced a run-level score and nothing per round,
    which most of them do. Empty means the metric did not run at all.
    """
    if measurement is None:
        return ""
    return str(len(measurement.per_round))


def observation_value_cell(observation: RoundObservation | AgentObservation | None) -> str:
    """Render one observation's value, or empty when the metric did not report it."""
    if observation is None:
        return ""
    return render_number(value=observation.value)


def observation_note_cell(observation: RoundObservation | AgentObservation | None) -> str:
    """Render one observation's note, or empty when the metric did not report it."""
    if observation is None:
        return ""
    return render_cell(text=observation.note)


def rounds_by_number(measurement: Measurement) -> dict[int, RoundObservation]:
    """Index a measurement's per-round observations by round number."""
    return {observation.round_number: observation for observation in measurement.per_round}


def agents_by_id(measurement: Measurement) -> dict[str, AgentObservation]:
    """Index a measurement's per-agent observations by agent id."""
    return {observation.agent_id: observation for observation in measurement.per_agent}
