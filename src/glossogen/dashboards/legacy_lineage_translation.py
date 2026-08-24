"""Reading dashboards saved before the fork-at-round rename.

A saved chart stores its query, and a query filtering on
``derivation_type = "resume_at_round"`` or slicing by ``lineage.round_start``
matches nothing once runs surface as ``fork_at_round`` with
``lineage.after_round``. Both stores translate on read: the key renames are
mechanical, and the value shifts are exact arithmetic
(``round_start = after_round + 1``, ``rounds_after = rounds_after_swap + 1``),
so a numeric bound moves with its column. A ``contains`` value cannot be
translated and is left as written.
"""

from glossogen.dashboards.dashboard_models import ChartSpec, Dashboard
from glossogen.run_analysis.dimension_filter import DimensionFilter, FilterOperator

_KEY_RENAMES = {
    "lineage.round_start": "lineage.after_round",
    "lineage.rounds_after_swap": "lineage.rounds_after",
    "lineage.rounds_after_resume": "lineage.rounds_after",
}
_VALUE_SHIFTS = {
    "lineage.round_start": -1,
    "lineage.rounds_after_swap": 1,
    "lineage.rounds_after_resume": 1,
}
_NUMERIC_OPERATORS = frozenset(
    {
        FilterOperator.IN,
        FilterOperator.NOT_IN,
        FilterOperator.GREATER_OR_EQUAL,
        FilterOperator.LESS_OR_EQUAL,
    }
)
_LEGACY_DERIVATION_VALUE = "resume_at_round"
_CURRENT_DERIVATION_VALUE = "fork_at_round"


def _shift_value(value: str, shift: int) -> str:
    """Move a numeric filter value with its renamed column; leave text alone."""
    try:
        return str(int(value) + shift)
    except ValueError:
        return value


def _translate_filter(condition: DimensionFilter) -> DimensionFilter:
    """Return the condition under the current lineage vocabulary."""
    values = list(condition.values)
    if condition.key == "derivation_type":
        values = [
            _CURRENT_DERIVATION_VALUE if value == _LEGACY_DERIVATION_VALUE else value
            for value in values
        ]
    if condition.key in _VALUE_SHIFTS and condition.operator in _NUMERIC_OPERATORS:
        shift = _VALUE_SHIFTS[condition.key]
        values = [_shift_value(value=value, shift=shift) for value in values]
    key = _KEY_RENAMES.get(condition.key, condition.key)
    if key == condition.key and values == condition.values:
        return condition
    return DimensionFilter(key=key, operator=condition.operator, values=values)


def _translate_chart(chart: ChartSpec) -> ChartSpec:
    """Return the chart with its query's filters and group-by keys translated."""
    query = chart.query
    filters = [_translate_filter(condition=condition) for condition in query.filters]
    group_by = [_KEY_RENAMES.get(key, key) for key in query.group_by]
    if filters == query.filters and group_by == query.group_by:
        return chart
    return chart.model_copy(
        update={"query": query.model_copy(update={"filters": filters, "group_by": group_by})}
    )


def translate_legacy_lineage_terms(dashboard: Dashboard) -> Dashboard:
    """Return the dashboard with pre-rename lineage terms translated.

    Idempotent: a dashboard already using the current vocabulary comes back
    unchanged, object identity included.
    """
    filters = [_translate_filter(condition=condition) for condition in dashboard.filters]
    charts = [_translate_chart(chart=chart) for chart in dashboard.charts]
    if filters == dashboard.filters and charts == dashboard.charts:
        return dashboard
    return dashboard.model_copy(update={"filters": filters, "charts": charts})
