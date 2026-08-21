"""Answering one query: filter the table, group it, aggregate each group.

Groups are ordered numerically when their values are numbers. A knob sweep over
800, 2000, and 10000 charts in that order rather than in the order a string sort
would give it, and no client has to re-sort what it received.

A group's aggregate is computed over the observations that had a number. The two
counts beside it say how many that was and how many were missing, which is the
whole empty-versus-zero rule carried into the answer.
"""

from glossogen.run_analysis.aggregation import aggregate_values, present_values
from glossogen.run_analysis.analysis_limits import MAX_RESULT_ROWS
from glossogen.run_analysis.analysis_query_models import AnalysisQuerySpec, MeasureSpec, ResultSort
from glossogen.run_analysis.analysis_result_models import (
    AggregateCell,
    AnalysisResult,
    AnalysisResultRow,
    measure_result_entry,
)
from glossogen.run_analysis.analysis_run_record import AnalysisRunRecord
from glossogen.run_analysis.dimension_filter import apply_filters, parse_number
from glossogen.run_analysis.measure_resolution import field_key
from glossogen.run_analysis.metric_inventory import measure_unit, metric_units
from glossogen.run_analysis.observation_row import ObservationRow
from glossogen.run_analysis.observation_table import build_observation_table

# Sorts numbers before text, so a mixed column ("800", "2000", "default") keeps
# its numeric part in numeric order instead of scattering it through the strings.
_NUMBERS_FIRST = 0
_TEXT_AFTER_NUMBERS = 1


def _natural_key(group_values: list[str]) -> tuple[tuple[int, float, str], ...]:
    """Return an ordering key that reads numeric cells as numbers."""
    key: list[tuple[int, float, str]] = []
    for value in group_values:
        number = parse_number(text=value)
        if number is None:
            key.append((_TEXT_AFTER_NUMBERS, 0.0, value))
            continue
        key.append((_NUMBERS_FIRST, number, ""))
    return tuple(key)


def _cell(rows: list[ObservationRow], measure: MeasureSpec) -> AggregateCell:
    """Aggregate one measure over one group's rows."""
    values = [rows_measure(row=row, measure=measure) for row in rows]
    present = present_values(values=values)
    return AggregateCell(
        value=aggregate_values(values=present, aggregate=measure.aggregate),
        observation_count=len(present),
        missing_count=len(values) - len(present),
    )


def rows_measure(row: ObservationRow, measure: MeasureSpec) -> float | None:
    """Read one measure's value off one row."""
    return row.measures.get(field_key(field=measure.field()))


def _group_rows(
    rows: list[ObservationRow],
    group_by: list[str],
) -> dict[tuple[str, ...], list[ObservationRow]]:
    """Bucket rows by their group-by cells, keeping first-seen order."""
    grouped: dict[tuple[str, ...], list[ObservationRow]] = {}
    for row in rows:
        key = tuple(row.dimensions.get(dimension, "") for dimension in group_by)
        grouped.setdefault(key, []).append(row)
    return grouped


def _sorted_rows(rows: list[AnalysisResultRow], spec: AnalysisQuerySpec) -> list[AnalysisResultRow]:
    """Order the result rows as the spec asks."""
    if spec.sort is ResultSort.GROUP:
        return sorted(rows, key=lambda row: _natural_key(group_values=row.group_values))

    descending = spec.sort is ResultSort.MEASURE_DESCENDING

    def measure_key(row: AnalysisResultRow) -> tuple[int, float]:
        """Sort by one measure, with groups that computed nothing last either way."""
        value = row.cells[spec.sort_measure_index].value
        if value is None:
            return (1, 0.0)
        if descending:
            return (0, -value)
        return (0, value)

    return sorted(rows, key=measure_key)


def _score_units(records: list[AnalysisRunRecord], spec: AnalysisQuerySpec) -> list[str]:
    """Return each requested measure's unit, in request order."""
    units = metric_units(records=records)
    return [
        measure_unit(field=measure.field(), grain=spec.grain, units=units)
        for measure in spec.measures
    ]


def run_analysis_query(
    records: list[AnalysisRunRecord],
    spec: AnalysisQuerySpec,
) -> AnalysisResult:
    """Answer one query over the loaded runs."""
    table = build_observation_table(records=records, grain=spec.grain, fields=spec.fields())
    rows = apply_filters(rows=table, filters=spec.filters)

    result_rows = [
        AnalysisResultRow(
            group_values=list(key),
            run_count=len({row.run_id for row in group}),
            cells=[_cell(rows=group, measure=measure) for measure in spec.measures],
        )
        for key, group in _group_rows(rows=rows, group_by=spec.group_by).items()
    ]
    ordered = _sorted_rows(rows=result_rows, spec=spec)
    ceiling = min(spec.limit, MAX_RESULT_ROWS)

    units = _score_units(records=records, spec=spec)
    return AnalysisResult(
        grain=spec.grain,
        group_by=list(spec.group_by),
        measures=[
            measure_result_entry(measure=measure, score_unit=unit)
            for measure, unit in zip(spec.measures, units, strict=True)
        ],
        rows=ordered[:ceiling],
        run_count=len({row.run_id for row in rows}),
        observation_count=len(rows),
        truncated=len(ordered) > ceiling,
        missing_run_ids=[],
    )
