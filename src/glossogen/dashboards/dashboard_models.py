"""Models for saved analysis selections, filters, and chart queries.

Dashboard-level filters apply to every chart; a chart may add its own filters. Only
the queries are stored, so clients execute them again when opening the dashboard.
"""

from datetime import datetime
from enum import Enum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from glossogen.run_analysis.analysis_query_models import AnalysisQuerySpec
from glossogen.run_analysis.dimension_filter import DimensionFilter
from glossogen.run_export.export_request_models import RunSelection


class ChartKind(str, Enum):
    """How one chart draws its result."""

    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    HEATMAP = "heatmap"
    TABLE = "table"


class ChartEncoding(BaseModel):
    """Which of a query's measures the chart's axes read.

    All indexes address ``query.measures``. ``y_measure_index`` is the scatter plot's
    second axis. ``error_measure_index`` optionally supplies error bars for
    ``measure_index`` and defaults to ``None`` for stored dashboards created before
    that field existed.
    """

    measure_index: int
    y_measure_index: int
    error_measure_index: int | None = None


class ChartSpec(BaseModel):
    """One chart, including its query and measure indexes."""

    chart_id: str
    title: str
    kind: ChartKind
    query: AnalysisQuerySpec
    encoding: ChartEncoding

    @model_validator(mode="after")
    def check_encoding(self) -> Self:
        """Refuse an encoding that names a measure this chart's query does not have."""
        count = len(self.query.measures)
        indexes = [
            ("measure_index", self.encoding.measure_index),
            ("y_measure_index", self.encoding.y_measure_index),
        ]
        error_index = self.encoding.error_measure_index
        if error_index is not None:
            indexes.append(("error_measure_index", error_index))
        for name, index in indexes:
            if not 0 <= index < count:
                raise ValueError(f"{name} is {index}, but {self.title!r} has {count} measures.")

        # The error measure is drawn on another measure rather than as a series of its
        # own, so it is subtracted from what gets drawn. Naming the measure it sits on
        # leaves nothing: axes with nothing between them, under a header still
        # reporting the groups and runs behind them. A chart with one measure can only
        # name that one, so this covers that case too.
        if error_index is None:
            return self
        if error_index == self.encoding.measure_index:
            raise ValueError(
                f"{self.title!r} draws error bars from the measure they sit on, which "
                "removes it from the chart and leaves nothing to draw. Add the spread "
                "as a second measure and point error_measure_index at that one."
            )
        return self


class DashboardContent(BaseModel):
    """Everything a dashboard is, before it has an identity or a history."""

    name: str
    description: str
    selection: RunSelection
    filters: list[DimensionFilter]
    charts: list[ChartSpec]

    @field_validator("charts")
    @classmethod
    def check_chart_ids(cls, charts: list[ChartSpec]) -> list[ChartSpec]:
        """Require chart ids to be unique within the dashboard."""
        ids = [chart.chart_id for chart in charts]
        if len(ids) != len(set(ids)):
            raise ValueError("Chart ids must be unique within a dashboard.")
        return charts


class Dashboard(DashboardContent):
    """A stored dashboard, with who made it and when it last changed."""

    dashboard_id: UUID
    created_by: str
    created_at: datetime
    updated_at: datetime


class DashboardSummary(BaseModel):
    """One row of the dashboard list, without the charts."""

    dashboard_id: UUID
    name: str
    description: str
    chart_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime


def summarize(dashboard: Dashboard) -> DashboardSummary:
    """Describe a dashboard without its charts."""
    return DashboardSummary(
        dashboard_id=dashboard.dashboard_id,
        name=dashboard.name,
        description=dashboard.description,
        chart_count=len(dashboard.charts),
        created_by=dashboard.created_by,
        created_at=dashboard.created_at,
        updated_at=dashboard.updated_at,
    )
