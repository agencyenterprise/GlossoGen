"""Saving, listing, reloading, and deleting a dashboard.

The suite runs with no ``DATABASE_URL``, so these drive the filesystem store, which
is what a single-tenant checkout uses. Both stores implement one contract and the
router only ever calls through it, so what is pinned here is that contract: group
scoping, one name per group, and a dashboard that survives being written and read
back with its charts intact.

The Postgres store's own SQL is exercised by the migration and by running the server
against a database; there is no live database in this suite to point it at.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from glossogen.dashboards.dashboard_models import (
    ChartEncoding,
    ChartKind,
    ChartSpec,
    DashboardContent,
)
from glossogen.dashboards.dashboard_store import DashboardNameTaken
from glossogen.dashboards.filesystem_dashboard_store import FilesystemDashboardStore
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

SELECTION = FilterRunSelection(
    kind="filters",
    scenario=["veyru"],
    labels=["channel_noise"],
    run_id_contains=None,
    status=None,
    contains_agent_id=None,
)


def chart(title: str) -> ChartSpec:
    """One saved chart: a grouped mean of round success."""
    return ChartSpec(
        chart_id="chart-1",
        title=title,
        kind=ChartKind.BAR,
        query=AnalysisQuerySpec(
            grain=AnalysisGrain.RUN,
            filters=[],
            group_by=["knob.channel_noise_level"],
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


def content(name: str) -> DashboardContent:
    """A dashboard carrying one chart and one dashboard-level filter."""
    return DashboardContent(
        name=name,
        description="How noise moves round success",
        selection=SELECTION,
        filters=[DimensionFilter(key="model_class", operator=FilterOperator.IN, values=["closed"])],
        charts=[chart(title="Round success by noise")],
    )


@pytest.fixture(name="store")
def store_fixture(tmp_path: Path) -> FilesystemDashboardStore:
    """A store over an empty runs directory."""
    return FilesystemDashboardStore(runs_dir=tmp_path / "runs")


async def test_a_saved_dashboard_reloads_with_its_charts(
    store: FilesystemDashboardStore,
) -> None:
    group = uuid4()

    created = await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )
    reloaded = await store.get_dashboard(group_id=group, dashboard_id=created.dashboard_id)

    assert reloaded is not None
    assert reloaded.name == "Noise sweep"
    assert reloaded.charts[0].query.group_by == ["knob.channel_noise_level"]
    assert reloaded.charts[0].query.measures[0].key == "round_success"
    assert reloaded.filters[0].values == ["closed"]


async def test_listing_reports_the_chart_count_without_the_charts(
    store: FilesystemDashboardStore,
) -> None:
    group = uuid4()
    await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )

    listed = await store.list_dashboards(group_id=group)

    assert [summary.name for summary in listed] == ["Noise sweep"]
    assert listed[0].chart_count == 1


async def test_another_group_cannot_read_a_dashboard(store: FilesystemDashboardStore) -> None:
    owner = uuid4()
    created = await store.create_dashboard(
        group_id=owner, content=content(name="Noise sweep"), created_by="local-user"
    )

    stranger = await store.get_dashboard(group_id=uuid4(), dashboard_id=created.dashboard_id)

    assert stranger is None


async def test_two_groups_may_each_have_a_dashboard_by_the_same_name(
    store: FilesystemDashboardStore,
) -> None:
    first = await store.create_dashboard(
        group_id=uuid4(), content=content(name="Noise sweep"), created_by="local-user"
    )
    second = await store.create_dashboard(
        group_id=uuid4(), content=content(name="Noise sweep"), created_by="local-user"
    )

    assert first.dashboard_id != second.dashboard_id


async def test_one_group_may_not_reuse_a_name(store: FilesystemDashboardStore) -> None:
    group = uuid4()
    await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )

    with pytest.raises(DashboardNameTaken):
        await store.create_dashboard(
            group_id=group, content=content(name="Noise sweep"), created_by="local-user"
        )


async def test_updating_keeps_the_name_it_already_had(store: FilesystemDashboardStore) -> None:
    """Renaming to itself is not a collision with itself."""
    group = uuid4()
    created = await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )

    updated = await store.update_dashboard(
        group_id=group, dashboard_id=created.dashboard_id, content=content(name="Noise sweep")
    )

    assert updated is not None
    assert updated.created_at == created.created_at


async def test_updating_replaces_the_charts(store: FilesystemDashboardStore) -> None:
    group = uuid4()
    created = await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )

    replacement = content(name="Noise sweep")
    replacement.charts = [chart(title="First"), chart(title="Second")]
    updated = await store.update_dashboard(
        group_id=group, dashboard_id=created.dashboard_id, content=replacement
    )

    assert updated is not None
    assert [chart_spec.title for chart_spec in updated.charts] == ["First", "Second"]


async def test_updating_a_dashboard_another_group_owns_finds_nothing(
    store: FilesystemDashboardStore,
) -> None:
    created = await store.create_dashboard(
        group_id=uuid4(), content=content(name="Noise sweep"), created_by="local-user"
    )

    updated = await store.update_dashboard(
        group_id=uuid4(), dashboard_id=created.dashboard_id, content=content(name="Renamed")
    )

    assert updated is None


async def test_deleting_reports_whether_there_was_one(store: FilesystemDashboardStore) -> None:
    group = uuid4()
    created = await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )

    assert await store.delete_dashboard(group_id=group, dashboard_id=created.dashboard_id) is True
    assert await store.delete_dashboard(group_id=group, dashboard_id=created.dashboard_id) is False


async def test_an_unreadable_file_is_skipped_rather_than_failing_the_listing(
    store: FilesystemDashboardStore, tmp_path: Path
) -> None:
    """One corrupt dashboard must not take the whole list down with it."""
    group = uuid4()
    await store.create_dashboard(
        group_id=group, content=content(name="Noise sweep"), created_by="local-user"
    )
    (tmp_path / "runs" / "_dashboards" / str(group) / f"{uuid4()}.json").write_text("not json")

    listed = await store.list_dashboards(group_id=group)

    assert [summary.name for summary in listed] == ["Noise sweep"]


def test_a_chart_whose_encoding_points_past_its_measures_is_refused() -> None:
    """An out-of-range index is not a visible error: every cell it reads comes back
    missing, so the chart draws an empty frame under a header still reporting its
    groups and runs. That is what a saved chart does after a measure is removed."""
    one_measure = chart(title="One measure").query

    with pytest.raises(ValidationError):
        ChartSpec(
            chart_id="c1",
            title="One measure",
            kind=ChartKind.SCATTER,
            query=one_measure,
            encoding=ChartEncoding(measure_index=0, y_measure_index=1),
        )


def test_a_scatter_encoding_within_range_is_accepted() -> None:
    single = chart(title="Two measures").query
    two_measures = single.model_copy(update={"measures": [single.measures[0], single.measures[0]]})

    spec = ChartSpec(
        chart_id="c1",
        title="Two measures",
        kind=ChartKind.SCATTER,
        query=two_measures,
        encoding=ChartEncoding(measure_index=0, y_measure_index=1),
    )

    assert spec.encoding.y_measure_index == 1


def test_a_chart_drawing_its_only_measure_as_error_bars_is_refused() -> None:
    """Error bars are drawn on another measure rather than as a series, so naming the
    only one leaves axes with nothing between them under a populated header."""
    one_measure = chart(title="Only measure").query

    with pytest.raises(ValidationError):
        ChartSpec(
            chart_id="c1",
            title="Only measure",
            kind=ChartKind.BAR,
            query=one_measure,
            encoding=ChartEncoding(measure_index=0, y_measure_index=0, error_measure_index=0),
        )


def test_error_bars_drawn_from_the_measure_they_sit_on_are_refused() -> None:
    single = chart(title="Two measures").query
    two_measures = single.model_copy(update={"measures": [single.measures[0], single.measures[0]]})

    with pytest.raises(ValidationError):
        ChartSpec(
            chart_id="c1",
            title="Two measures",
            kind=ChartKind.BAR,
            query=two_measures,
            encoding=ChartEncoding(measure_index=1, y_measure_index=0, error_measure_index=1),
        )


def test_error_bars_from_a_second_measure_are_accepted() -> None:
    """The shape this is for: the metric once as a mean, once as its standard error."""
    single = chart(title="Mean and sem").query
    two_measures = single.model_copy(update={"measures": [single.measures[0], single.measures[0]]})

    spec = ChartSpec(
        chart_id="c1",
        title="Mean and sem",
        kind=ChartKind.BAR,
        query=two_measures,
        encoding=ChartEncoding(measure_index=0, y_measure_index=0, error_measure_index=1),
    )

    assert spec.encoding.error_measure_index == 1


def test_a_stored_chart_without_the_error_field_still_opens() -> None:
    """The field has a default because this model is stored: a dashboard saved before
    it existed has to keep loading."""
    stored = chart(title="Saved earlier").model_dump()
    stored["encoding"] = {"measure_index": 0, "y_measure_index": 0}

    assert ChartSpec.model_validate(stored).encoding.error_measure_index is None
