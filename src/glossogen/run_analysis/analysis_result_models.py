"""What an analysis answers with.

Every aggregate travels with the number of observations behind it and the number
that were missing. A mean of 0.62 over 45 rounds and a mean of 0.62 over one are
different claims, and a chart that shows only the bar cannot tell them apart.

``value`` is ``None`` when nothing could be computed: no observation existed, or
the aggregate needed more than one. It is never zero standing in for absence.
"""

from pydantic import BaseModel

from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_models import MeasureSpec
from glossogen.run_export.export_column_catalog import humanize_column_key


class AggregateCell(BaseModel):
    """One measure's aggregate within one group, with what it was computed over."""

    value: float | None
    observation_count: int
    missing_count: int


class AnalysisResultRow(BaseModel):
    """One group: its values for the group-by keys, then one cell per measure."""

    group_values: list[str]
    run_count: int
    cells: list[AggregateCell]


class AnalysisResultMeasure(BaseModel):
    """A measure as it appears in the result, labelled for an axis."""

    column_key: str
    label: str
    score_unit: str
    aggregate: str


class AnalysisResult(BaseModel):
    """The answer to one query.

    ``truncated`` says the row ceiling clipped the answer, so a client can say the
    chart is partial rather than showing a confident subset.

    ``missing_run_ids`` names runs the selection asked for that no longer resolve.
    A saved dashboard outlives the runs it was built on, so a deleted run has to be
    reported rather than silently dropped from the numbers.
    """

    grain: AnalysisGrain
    group_by: list[str]
    measures: list[AnalysisResultMeasure]
    rows: list[AnalysisResultRow]
    run_count: int
    observation_count: int
    truncated: bool
    missing_run_ids: list[str]


class AnalysisDimensionValue(BaseModel):
    """One value a dimension takes in the selection, and how many rows carry it."""

    value: str
    observation_count: int


class AnalysisDimension(BaseModel):
    """One dimension a selection can be grouped or filtered by.

    ``values`` is capped, and ``distinct_count`` says how many there really are, so
    a picker can offer the common ones and say what it left out.
    """

    key: str
    label: str
    group: str
    rows_with_value: int
    distinct_count: int
    values: list[AnalysisDimensionValue]


class AnalysisMeasureField(BaseModel):
    """One measurable quantity a selection carries."""

    source: str
    key: str
    label: str
    score_unit: str
    rows_with_value: int


class AnalysisFieldCatalog(BaseModel):
    """Everything a client needs to build a query over one selection.

    Computed from the same table the query reads, so a dimension offered here is
    one a group-by can actually key on, and a measure offered is one that has
    numbers in it.
    """

    grain: AnalysisGrain
    run_count: int
    observation_count: int
    runs_without_report: list[str]
    missing_run_ids: list[str]
    dimensions: list[AnalysisDimension]
    measures: list[AnalysisMeasureField]
    max_dimension_values: int
    max_group_by_keys: int
    max_result_rows: int


def measure_result_entry(measure: MeasureSpec, score_unit: str) -> AnalysisResultMeasure:
    """Describe one requested measure as it appears in the result."""
    return AnalysisResultMeasure(
        column_key=measure.column_key(),
        label=humanize_column_key(key=measure.key),
        score_unit=score_unit,
        aggregate=measure.aggregate.value,
    )
