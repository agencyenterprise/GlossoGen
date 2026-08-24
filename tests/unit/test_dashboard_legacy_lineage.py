"""Dashboards saved before the fork-at-round rename keep answering.

A saved chart stores its query. One filtering on the pre-rename lineage terms
would match nothing against runs that now surface as ``fork_at_round`` with
``lineage.after_round``, so the stores translate on read. The value shifts are
exact: ``round_start = after_round + 1``, so a bound moves with its column.
"""

from datetime import UTC, datetime
from uuid import uuid4

from glossogen.dashboards.dashboard_models import (
    ChartEncoding,
    ChartKind,
    ChartSpec,
    Dashboard,
)
from glossogen.dashboards.legacy_lineage_translation import translate_legacy_lineage_terms
from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_models import (
    AnalysisQuerySpec,
    MeasureSpec,
    ResultSort,
)
from glossogen.run_analysis.dimension_filter import DimensionFilter, FilterOperator
from glossogen.run_analysis.measure_resolution import MeasureSource
from glossogen.run_export.export_request_models import FilterRunSelection

_SELECTION = FilterRunSelection(
    kind="filters",
    scenario=["veyru"],
    labels=[],
    run_id_contains=None,
    status=None,
    contains_agent_id=None,
)


def _chart(filters: list[DimensionFilter], group_by: list[str]) -> ChartSpec:
    """One chart over round_success with the given query slicing."""
    return ChartSpec(
        chart_id="chart-1",
        title="Post-fork success",
        kind=ChartKind.BAR,
        query=AnalysisQuerySpec(
            grain=AnalysisGrain.RUN,
            filters=filters,
            group_by=group_by,
            measures=[
                MeasureSpec(
                    source=MeasureSource.METRIC, key="round_success", aggregate=Aggregate.MEAN
                )
            ],
            sort=ResultSort.GROUP,
            sort_measure_index=0,
            limit=100,
        ),
        encoding=ChartEncoding(measure_index=0, y_measure_index=0, error_measure_index=None),
    )


def _dashboard(filters: list[DimensionFilter], chart: ChartSpec) -> Dashboard:
    """A stored dashboard around one chart."""
    return Dashboard(
        dashboard_id=uuid4(),
        name="forks",
        description="",
        selection=_SELECTION,
        filters=filters,
        charts=[chart],
        created_by="local-user",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_legacy_lineage_terms_translate_with_their_values() -> None:
    """Keys rename, the derivation value follows, and numeric bounds shift exactly."""
    dashboard = _dashboard(
        filters=[
            DimensionFilter(
                key="derivation_type",
                operator=FilterOperator.IN,
                values=["resume_at_round", "replace_agent"],
            )
        ],
        chart=_chart(
            filters=[
                DimensionFilter(
                    key="lineage.round_start",
                    operator=FilterOperator.GREATER_OR_EQUAL,
                    values=["15"],
                ),
                DimensionFilter(
                    key="lineage.rounds_after_resume",
                    operator=FilterOperator.IN,
                    values=["10", "not-a-number"],
                ),
            ],
            group_by=["lineage.round_start"],
        ),
    )

    translated = translate_legacy_lineage_terms(dashboard=dashboard)

    assert translated.filters[0].values == ["fork_at_round", "replace_agent"]
    chart_filters = translated.charts[0].query.filters
    assert chart_filters[0].key == "lineage.after_round"
    assert chart_filters[0].values == ["14"]
    assert chart_filters[1].key == "lineage.rounds_after"
    assert chart_filters[1].values == ["11", "not-a-number"]
    assert translated.charts[0].query.group_by == ["lineage.after_round"]


def test_the_resumed_at_column_renames_to_forked_at() -> None:
    """The provenance timestamp column renamed with the model, so its filters follow."""
    dashboard = _dashboard(
        filters=[],
        chart=_chart(
            filters=[
                DimensionFilter(
                    key="lineage.resumed_at",
                    operator=FilterOperator.IS_NOT_EMPTY,
                    values=[],
                )
            ],
            group_by=["lineage.resumed_at"],
        ),
    )

    translated = translate_legacy_lineage_terms(dashboard=dashboard)

    assert translated.charts[0].query.filters[0].key == "lineage.forked_at"
    assert translated.charts[0].query.group_by == ["lineage.forked_at"]


def test_a_current_dashboard_passes_through_untouched() -> None:
    """Translation is idempotent: the current vocabulary comes back as-is."""
    dashboard = _dashboard(
        filters=[
            DimensionFilter(
                key="derivation_type", operator=FilterOperator.IN, values=["fork_at_round"]
            )
        ],
        chart=_chart(
            filters=[
                DimensionFilter(
                    key="lineage.after_round",
                    operator=FilterOperator.GREATER_OR_EQUAL,
                    values=["14"],
                )
            ],
            group_by=["lineage.after_round"],
        ),
    )

    assert translate_legacy_lineage_terms(dashboard=dashboard) is dashboard
