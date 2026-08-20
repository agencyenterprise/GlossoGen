"""FastAPI router for cross-run analysis: what a selection carries, and one query.

Two POSTs, for the same reason the export endpoints are POSTs: a selection can name
hundreds of runs and a query can name a dozen dimensions and measures, which as a
query string exceeds what proxies accept and comes back as an opaque 414.

A selection that matches nothing is answered rather than refused. A saved dashboard
points at a cohort by filters, and a cohort that is empty today is a thing to render
as "no runs match" rather than an error to explain. Ids that no longer resolve are
reported on the answer for the same reason: a dashboard outlives its runs.

The run ceiling is the export's, since the work is the same work: one evaluation
report read per selected run.
"""

import logging
import time
from typing import NamedTuple

from fastapi import APIRouter, HTTPException, Request

from glossogen.run_analysis.analysis_field_catalog import build_field_catalog
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_query_engine import run_analysis_query
from glossogen.run_analysis.analysis_query_models import (
    AnalysisFieldsRequest,
    AnalysisQueryRequest,
)
from glossogen.run_analysis.analysis_result_models import AnalysisFieldCatalog, AnalysisResult
from glossogen.run_analysis.analysis_run_record import (
    AnalysisRunRecord,
    load_analysis_records,
)
from glossogen.run_export.export_limits import ExportTooLargeError, check_run_count
from glossogen.run_export.export_request_models import RunSelection
from glossogen.server.runs.export_selection import resolve_export_selection
from glossogen.server.runs.lookup import get_identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


class SelectedRecords(NamedTuple):
    """The loaded runs a selection names, and the ids it named that are gone."""

    records: list[AnalysisRunRecord]
    missing_run_ids: list[str]


async def _selected_records(
    request: Request,
    selection: RunSelection,
    grain: AnalysisGrain,
) -> SelectedRecords:
    """Resolve and load the runs a selection names within the active group.

    The grain decides whether the metrics' sidecars are read, which is a filesystem
    read per metric per run and is why it is not done for the grains that cannot use
    them. It is part of the cache key for the same reason: records loaded without
    sidecars would answer a keyed query with nothing.
    """
    resolved = await resolve_export_selection(request=request, selection=selection)
    try:
        check_run_count(run_count=len(resolved.summaries))
    except ExportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    identity = get_identity(request=request)
    cache = request.app.state.analysis_record_cache
    read_sidecars = grain is AnalysisGrain.KEYED
    key = f"{identity.active_group_id}|{read_sidecars}|{selection.model_dump_json()}"

    async def load() -> list[AnalysisRunRecord]:
        """Read every selected run's report, keeping only what a query reads."""
        return await load_analysis_records(
            runs=resolved.summaries, read_sidecars=read_sidecars
        )

    records = await cache.records(
        key=key,
        now=time.monotonic(),
        run_count=len(resolved.summaries),
        load=load,
    )
    return SelectedRecords(records=records, missing_run_ids=sorted(resolved.missing_run_ids))


@router.post("/runs/analysis/fields", response_model=AnalysisFieldCatalog)
async def analysis_fields(
    body: AnalysisFieldsRequest,
    request: Request,
) -> AnalysisFieldCatalog:
    """Describe what this selection can be grouped, filtered, and measured by."""
    selected = await _selected_records(
        request=request, selection=body.selection, grain=body.grain
    )
    catalog = build_field_catalog(records=selected.records, grain=body.grain)
    return catalog.model_copy(update={"missing_run_ids": selected.missing_run_ids})


@router.post("/runs/analysis/query", response_model=AnalysisResult)
async def analysis_query(
    body: AnalysisQueryRequest,
    request: Request,
) -> AnalysisResult:
    """Group and aggregate this selection, one row per group."""
    selected = await _selected_records(
        request=request, selection=body.selection, grain=body.query.grain
    )
    logger.info(
        "Analysis query over %d runs at the %s grain, grouped by %s",
        len(selected.records),
        body.query.grain.value,
        ", ".join(body.query.group_by),
    )
    result = run_analysis_query(records=selected.records, spec=body.query)
    return result.model_copy(update={"missing_run_ids": selected.missing_run_ids})
