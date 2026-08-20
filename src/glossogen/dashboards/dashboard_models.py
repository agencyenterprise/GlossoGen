"""A saved analysis: which runs, which filters, and the charts drawn over them.

A dashboard holds the selection and the filters once, and every chart inherits them.
Re-pointing a whole study at another cohort is then one field changing rather than
every chart being rewritten, and a chart added later is automatically about the same
runs as the ones beside it. A chart narrows further with filters of its own, which are
applied on top.

Charts carry the query that produced them, not the numbers. Reopening a dashboard
re-runs the queries, so a cohort that gained runs, or reports that were evaluated
since, show up without anyone rebuilding anything.
"""

from datetime import datetime
from enum import Enum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, model_validator

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

    ``measure_index`` is the measure a bar, line, or heatmap draws when the query
    groups by two keys and the second is the series. ``y_measure_index`` is the
    scatter's second axis. Both index into the query's ``measures`` list, so a
    reordered query keeps its chart pointing at the same position rather than at a
    name that may no longer be there.

    ``error_measure_index`` names a second measure over the same metric, usually its
    standard error, drawn as error bars on the measure at ``measure_index``. It is
    ``None`` when the chart carries none, which is not the same as zero spread: a bar
    with no error bars says nothing about its spread, and one with a zero-length bar
    says the spread was measured and was zero.

    It is the one field here with a default, and the reason is that this model is
    stored. A dashboard saved last month has to keep opening after a field is added,
    and a required field would turn every one of them into a validation error on read.
    Fields added to a stored spec from here on carry the same kind of default.
    """

    measure_index: int
    y_measure_index: int
    error_measure_index: int | None = None


class ChartSpec(BaseModel):
    """One chart: a title, a form, and the query behind it.

    The encoding is validated against the query it belongs to. An index pointing past
    the measures is not a visible error: every cell it reads comes back missing, so
    the chart draws an empty frame under a header still reporting its groups and runs.
    That is worse than a refusal, and it is what a saved chart does after a measure is
    removed from it.
    """

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


class Dashboard(BaseModel):
    """A stored dashboard, with who made it and when it last changed."""

    dashboard_id: UUID
    name: str
    description: str
    selection: RunSelection
    filters: list[DimensionFilter]
    charts: list[ChartSpec]
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
