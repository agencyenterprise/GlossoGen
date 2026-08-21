"""The dashboard endpoints: what they refuse, and who can see what.

The stores are tested directly elsewhere. What the router adds is group scoping and
the two refusals a client has to be able to tell apart: a name the group already uses
is a 409, and an id belonging to another group reads as absent rather than forbidden,
which is the same shape run lookup uses and for the same reason — a 403 would confirm
the id exists.

Driven against the filesystem store, which is what a no-database deployment runs and
what this suite has.
"""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Request

from glossogen.dashboards.dashboard_models import (
    ChartEncoding,
    ChartKind,
    ChartSpec,
    DashboardContent,
)
from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_models import (
    AnalysisQuerySpec,
    MeasureSpec,
    ResultSort,
)
from glossogen.run_analysis.measure_resolution import MeasureSource
from glossogen.run_export.export_request_models import FilterRunSelection
from glossogen.server.identity.identity_model import Identity
from glossogen.server.runs.dashboard_router import (
    create_dashboard,
    delete_dashboard,
    get_dashboard,
    list_dashboards,
    update_dashboard,
)

SELECTION = FilterRunSelection(
    kind="filters",
    scenario=["veyru"],
    labels=[],
    run_id_contains=None,
    status=None,
    contains_agent_id=None,
)


def request_for(runs_dir: Path, group_id: UUID) -> Request:
    """A request carrying the runs directory and one group's identity."""
    app = SimpleNamespace(state=SimpleNamespace(db_pool=None, runs_dir=runs_dir))
    request = Request(scope={"type": "http", "method": "POST", "headers": [], "app": app})
    request.state.identity = Identity(
        user_id="local-user", active_group_id=group_id, is_local_mode=True
    )
    return request


def content(name: str) -> DashboardContent:
    """A dashboard with one chart on it."""
    return DashboardContent(
        name=name,
        description="",
        selection=SELECTION,
        filters=[],
        charts=[
            ChartSpec(
                chart_id="c1",
                title="Round success by budget",
                kind=ChartKind.BAR,
                query=AnalysisQuerySpec(
                    grain=AnalysisGrain.RUN,
                    filters=[],
                    group_by=["knob.round_time_budget_seconds"],
                    measures=[
                        MeasureSpec(
                            source=MeasureSource.METRIC,
                            key="round_success",
                            aggregate=Aggregate.MEAN,
                        )
                    ],
                    sort=ResultSort.GROUP,
                    sort_measure_index=0,
                    limit=100,
                ),
                encoding=ChartEncoding(measure_index=0, y_measure_index=0),
            )
        ],
    )


async def test_a_saved_dashboard_comes_back_on_the_group_listing(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())

    created = await create_dashboard(body=content(name="Noise sweep"), request=request)
    listed = await list_dashboards(request=request)

    assert [summary.name for summary in listed] == ["Noise sweep"]
    assert listed[0].chart_count == 1
    assert created.created_by == "local-user"


async def test_a_name_the_group_already_uses_is_refused_as_a_conflict(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())
    await create_dashboard(body=content(name="Noise sweep"), request=request)

    with pytest.raises(HTTPException) as refusal:
        await create_dashboard(body=content(name="Noise sweep"), request=request)

    assert refusal.value.status_code == 409
    assert "Noise sweep" in str(refusal.value.detail)


async def test_renaming_onto_another_dashboards_name_is_refused(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())
    await create_dashboard(body=content(name="Noise sweep"), request=request)
    second = await create_dashboard(body=content(name="Budget sweep"), request=request)

    with pytest.raises(HTTPException) as refusal:
        await update_dashboard(
            dashboard_id=second.dashboard_id, body=content(name="Noise sweep"), request=request
        )

    assert refusal.value.status_code == 409


async def test_another_groups_dashboard_reads_as_absent(tmp_path: Path) -> None:
    owner = request_for(runs_dir=tmp_path, group_id=uuid4())
    stranger = request_for(runs_dir=tmp_path, group_id=uuid4())
    created = await create_dashboard(body=content(name="Noise sweep"), request=owner)

    with pytest.raises(HTTPException) as refusal:
        await get_dashboard(dashboard_id=created.dashboard_id, request=stranger)

    assert refusal.value.status_code == 404


async def test_another_group_cannot_delete_it_either(tmp_path: Path) -> None:
    owner = request_for(runs_dir=tmp_path, group_id=uuid4())
    stranger = request_for(runs_dir=tmp_path, group_id=uuid4())
    created = await create_dashboard(body=content(name="Noise sweep"), request=owner)

    with pytest.raises(HTTPException) as refusal:
        await delete_dashboard(dashboard_id=created.dashboard_id, request=stranger)

    assert refusal.value.status_code == 404
    assert await get_dashboard(dashboard_id=created.dashboard_id, request=owner) is not None


async def test_deleting_twice_is_a_404_the_second_time(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())
    created = await create_dashboard(body=content(name="Noise sweep"), request=request)

    response = await delete_dashboard(dashboard_id=created.dashboard_id, request=request)
    assert response.status_code == 204

    with pytest.raises(HTTPException) as refusal:
        await delete_dashboard(dashboard_id=created.dashboard_id, request=request)
    assert refusal.value.status_code == 404


async def test_updating_a_dashboard_that_is_not_there_is_a_404(tmp_path: Path) -> None:
    request = request_for(runs_dir=tmp_path, group_id=uuid4())

    with pytest.raises(HTTPException) as refusal:
        await update_dashboard(
            dashboard_id=uuid4(), body=content(name="Noise sweep"), request=request
        )

    assert refusal.value.status_code == 404
