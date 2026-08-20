"""The analysis endpoints' branches, and the cache that sits under both.

The handlers are called directly with a stubbed selection resolver, the way the
export router's tests are: everything under test here is downstream of resolution.
What the endpoints add over the engine is a ceiling, a cache, and reporting the ids
a selection named that no longer exist, and those are what these pin.

The cache is driven with an explicit clock. It expires entries by time, and a test
that waited for that would be racing the machine it runs on.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_models import (
    AnalysisFieldsRequest,
    AnalysisQueryRequest,
    AnalysisQuerySpec,
    MeasureSpec,
    ResultSort,
)
from glossogen.run_analysis.analysis_run_record import (
    AnalysisRunRecord,
    project_run_record,
)
from glossogen.run_analysis.measure_resolution import MeasureSource
from glossogen.run_export import export_limits
from glossogen.run_export.export_request_models import FilterRunSelection
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.run_selection_resolution import ResolvedSelection
from glossogen.server.identity.identity_model import Identity
from glossogen.server.runs import analysis_router
from glossogen.server.runs.analysis_record_cache import (
    RECORD_CACHE_MAX_RUNS,
    RECORD_CACHE_TTL_SECONDS,
    AnalysisRecordCache,
)
from glossogen.server.runs.analysis_router import analysis_fields, analysis_query
from tests.fakes.export_run_records import make_agent, make_measurement, make_record

SONNET = make_agent(agent_id="field_observer", model="claude-sonnet-4-6", provider="anthropic")

SELECTION = FilterRunSelection(
    kind="filters",
    scenario=["veyru"],
    labels=[],
    run_id_contains=None,
    status=None,
    contains_agent_id=None,
)


def records_for(scores: list[float | None]) -> list[ExportRunRecord]:
    """Build one record per score, with ``None`` meaning the run was never evaluated."""
    built: list[ExportRunRecord] = []
    for index, score in enumerate(scores):
        measurements = None
        if score is not None:
            measurements = [
                make_measurement(
                    metric_name="round_success", score=score, per_round=[], per_agent=[]
                )
            ]
        built.append(
            make_record(
                run_id=f"veyru/{index}",
                scenario_name="veyru",
                scenario_config={"channel_noise_level": 0.2},
                labels=["channel_noise"],
                agents=[SONNET],
                measurements=measurements,
                total_cost_usd=1.0,
                current_round=15,
            )
        )
    return built


def make_request() -> Request:
    """A request carrying the app state and identity the handlers read."""
    cache = AnalysisRecordCache(
        ttl_seconds=RECORD_CACHE_TTL_SECONDS, max_runs=RECORD_CACHE_MAX_RUNS
    )
    app = SimpleNamespace(state=SimpleNamespace(analysis_record_cache=cache))
    request = Request(scope={"type": "http", "method": "POST", "headers": [], "app": app})
    request.state.identity = Identity(
        user_id="local-user", active_group_id=uuid4(), is_local_mode=True
    )
    return request


def stub_selection(
    monkeypatch: pytest.MonkeyPatch,
    records: list[ExportRunRecord],
    missing: list[str],
) -> None:
    """Answer resolution with these runs, and load them without touching disk."""

    async def resolve(request: Request, selection: object) -> ResolvedSelection:
        del request, selection
        return ResolvedSelection(
            summaries=[record.summary for record in records], missing_run_ids=missing
        )

    async def load(runs: object, read_sidecars: bool) -> list[AnalysisRunRecord]:
        del runs
        del read_sidecars
        return [project_run_record(record=record, keyed={}) for record in records]

    monkeypatch.setattr(analysis_router, "resolve_export_selection", resolve)
    monkeypatch.setattr(analysis_router, "load_analysis_records", load)


def query_body(group_by: list[str]) -> AnalysisQueryRequest:
    """A query over the mean of round success."""
    return AnalysisQueryRequest(
        selection=SELECTION,
        query=AnalysisQuerySpec(
            grain=AnalysisGrain.RUN,
            filters=[],
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
    )


# --- the endpoints --------------------------------------------------------------


async def test_the_field_catalog_offers_what_the_selection_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_selection(monkeypatch=monkeypatch, records=records_for(scores=[0.5]), missing=[])

    catalog = await analysis_fields(
        body=AnalysisFieldsRequest(selection=SELECTION, grain=AnalysisGrain.RUN),
        request=make_request(),
    )

    assert "knob.channel_noise_level" in {dimension.key for dimension in catalog.dimensions}
    assert "round_success" in {measure.key for measure in catalog.measures}


async def test_a_query_answers_with_one_row_per_group(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_selection(monkeypatch=monkeypatch, records=records_for(scores=[0.4, 0.6]), missing=[])

    result = await analysis_query(
        body=query_body(group_by=["scenario_name"]), request=make_request()
    )

    assert len(result.rows) == 1
    assert result.rows[0].cells[0].value == pytest.approx(0.5)
    assert result.run_count == 2


async def test_runs_that_no_longer_exist_are_named_on_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A saved dashboard outlives its runs, so a deleted one is reported, not hidden."""
    stub_selection(
        monkeypatch=monkeypatch, records=records_for(scores=[0.5]), missing=["veyru/gone"]
    )

    result = await analysis_query(body=query_body(group_by=[]), request=make_request())
    catalog = await analysis_fields(
        body=AnalysisFieldsRequest(selection=SELECTION, grain=AnalysisGrain.RUN),
        request=make_request(),
    )

    assert result.missing_run_ids == ["veyru/gone"]
    assert catalog.missing_run_ids == ["veyru/gone"]


async def test_a_selection_matching_nothing_is_answered_rather_than_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cohort that is empty today renders as "no runs match", not as an error."""
    stub_selection(monkeypatch=monkeypatch, records=[], missing=[])

    result = await analysis_query(
        body=query_body(group_by=["scenario_name"]), request=make_request()
    )

    assert result.rows == []
    assert result.run_count == 0


async def test_a_selection_over_the_run_ceiling_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(export_limits, "MAX_EXPORT_RUN_COUNT", 1)
    stub_selection(monkeypatch=monkeypatch, records=records_for(scores=[0.4, 0.6]), missing=[])

    with pytest.raises(HTTPException) as refusal:
        await analysis_query(body=query_body(group_by=[]), request=make_request())

    assert refusal.value.status_code == 413


# --- the record cache -----------------------------------------------------------


async def test_a_second_query_within_the_window_reuses_the_loaded_runs() -> None:
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=100)
    loads = 0

    async def load() -> list[AnalysisRunRecord]:
        nonlocal loads
        loads += 1
        return [project_run_record(record=record, keyed={}) for record in records_for(scores=[0.5])]

    await cache.records(key="a", now=100.0, run_count=1, load=load)
    await cache.records(key="a", now=110.0, run_count=1, load=load)

    assert loads == 1


async def test_a_query_after_the_window_loads_again() -> None:
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=100)
    loads = 0

    async def load() -> list[AnalysisRunRecord]:
        nonlocal loads
        loads += 1
        return [project_run_record(record=record, keyed={}) for record in records_for(scores=[0.5])]

    await cache.records(key="a", now=100.0, run_count=1, load=load)
    await cache.records(key="a", now=130.0, run_count=1, load=load)

    assert loads == 2


async def test_two_selections_do_not_share_an_entry() -> None:
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=100)
    loads = 0

    async def load() -> list[AnalysisRunRecord]:
        nonlocal loads
        loads += 1
        return [project_run_record(record=record, keyed={}) for record in records_for(scores=[0.5])]

    await cache.records(key="a", now=100.0, run_count=1, load=load)
    await cache.records(key="b", now=100.0, run_count=1, load=load)

    assert loads == 2


async def test_the_cache_holds_only_what_fits_its_run_budget() -> None:
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=2)
    loads = 0

    async def load() -> list[AnalysisRunRecord]:
        nonlocal loads
        loads += 1
        return [project_run_record(record=record, keyed={}) for record in records_for(scores=[0.5])]

    await cache.records(key="a", now=100.0, run_count=1, load=load)
    await cache.records(key="b", now=100.0, run_count=1, load=load)
    await cache.records(key="c", now=100.0, run_count=1, load=load)
    await cache.records(key="a", now=100.0, run_count=1, load=load)

    assert loads == 4


async def test_concurrent_requests_for_one_selection_load_once() -> None:
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=100)
    started = asyncio.Event()
    release = asyncio.Event()
    loads = 0

    async def load() -> list[AnalysisRunRecord]:
        nonlocal loads
        loads += 1
        started.set()
        await release.wait()
        return [project_run_record(record=record, keyed={}) for record in records_for(scores=[0.5])]

    first = asyncio.ensure_future(cache.records(key="a", now=100.0, run_count=1, load=load))
    await started.wait()
    second = asyncio.ensure_future(cache.records(key="a", now=100.0, run_count=1, load=load))
    release.set()
    await asyncio.gather(first, second)

    assert loads == 1


async def test_a_failed_load_is_not_held_for_the_next_request() -> None:
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=100)
    attempts = 0

    async def failing() -> list[AnalysisRunRecord]:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("the reports could not be read")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cache.records(key="a", now=100.0, run_count=1, load=failing)

    assert attempts == 2


async def test_a_selection_wider_than_the_whole_budget_is_not_held() -> None:
    """Holding it would evict everything else and still not fit."""
    cache = AnalysisRecordCache(ttl_seconds=20.0, max_runs=10)
    loads = 0

    async def load() -> list[AnalysisRunRecord]:
        nonlocal loads
        loads += 1
        return [project_run_record(record=record, keyed={}) for record in records_for(scores=[0.5])]

    await cache.records(key="wide", now=100.0, run_count=5000, load=load)
    await cache.records(key="wide", now=100.0, run_count=5000, load=load)

    assert loads == 2
    assert cache.cached_run_count() == 0
