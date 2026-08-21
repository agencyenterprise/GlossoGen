"""Reading measures and filters off the command line.

Both are colon-separated, because the parts are ordered and a shell should not need
quoting for the common case: ``round_success:mean`` and
``knob.round_time_budget_seconds:gte:1000``. A measure may name its source first
(``run_column:total_cost_usd:mean``); left out, it is a metric, which is what almost
every question is about.

An unparsable spec names what it could not read and lists the valid values, since a
typo in an aggregate would otherwise surface as an empty chart.
"""

from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_query_models import MeasureSpec
from glossogen.run_analysis.dimension_filter import DimensionFilter, FilterOperator
from glossogen.run_analysis.measure_resolution import MeasureSource


class AnalysisSpecError(ValueError):
    """A measure or filter argument that could not be read."""


def _aggregate(text: str) -> Aggregate:
    """Parse an aggregate name."""
    try:
        return Aggregate(text)
    except ValueError as exc:
        valid = ", ".join(aggregate.value for aggregate in Aggregate)
        raise AnalysisSpecError(f"Unknown aggregate {text!r}. Choose from: {valid}") from exc


def _source(text: str) -> MeasureSource:
    """Parse a measure source name."""
    try:
        return MeasureSource(text)
    except ValueError as exc:
        valid = ", ".join(source.value for source in MeasureSource)
        raise AnalysisSpecError(f"Unknown measure source {text!r}. Choose from: {valid}") from exc


def parse_measure(text: str) -> MeasureSpec:
    """Parse ``[source:]key:aggregate`` into a measure spec."""
    parts = text.split(":")
    if len(parts) == 2:
        return MeasureSpec(
            source=MeasureSource.METRIC,
            key=parts[0],
            aggregate=_aggregate(text=parts[1]),
        )
    if len(parts) == 3:
        return MeasureSpec(
            source=_source(text=parts[0]),
            key=parts[1],
            aggregate=_aggregate(text=parts[2]),
        )
    raise AnalysisSpecError(
        f"Could not read the measure {text!r}. Write it as key:aggregate, "
        "or source:key:aggregate."
    )


def parse_filter(text: str) -> DimensionFilter:
    """Parse ``key:operator[:value,value]`` into a filter."""
    parts = text.split(":", 2)
    if len(parts) < 2:
        raise AnalysisSpecError(
            f"Could not read the filter {text!r}. Write it as key:operator:value."
        )
    try:
        operator = FilterOperator(parts[1])
    except ValueError as exc:
        valid = ", ".join(candidate.value for candidate in FilterOperator)
        raise AnalysisSpecError(
            f"Unknown filter operator {parts[1]!r}. Choose from: {valid}"
        ) from exc

    values: list[str] = []
    if len(parts) == 3:
        values = [value for value in parts[2].split(",") if value != ""]
    if not values and operator not in (FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY):
        raise AnalysisSpecError(f"The filter {text!r} needs a value to compare against.")
    return DimensionFilter(key=parts[0], operator=operator, values=values)
