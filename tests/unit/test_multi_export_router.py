"""The export endpoints' branches: what they refuse, and what shape they answer with.

The handlers are called directly with a stubbed selection resolver rather than
through the app, because everything under test here is downstream of resolution:
which status code a bad request gets, whether one table comes back as a bare CSV or
a zip, and whether the response declares its length. Resolution itself is group
scoping plus the shared filter helpers, covered in `test_listing_filters`.

The ceilings are patched down rather than fed real cohorts, so the tests state the
rule instead of depending on how much data happens to be on the machine.
"""

import io
import zipfile
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.reports.evaluation_cost import EvaluationCost, EvaluationTokenUsage
from glossogen.evaluation.reports.evaluation_report import EvaluationReport
from glossogen.models.event import RunStatus
from glossogen.run_export import export_limits
from glossogen.run_export.export_request_models import (
    CsvExportRequest,
    ExplicitRunSelection,
    ExportFrame,
    ExportPreviewRequest,
    FilterRunSelection,
    RawExportRequest,
)
from glossogen.run_export.run_selection_resolution import ResolvedSelection
from glossogen.server.runs import multi_export_router
from glossogen.server.runs.models import AgentModelSummary, RunSummary
from glossogen.server.runs.multi_export_router import (
    export_runs_csv,
    export_runs_raw,
    preview_multi_run_export,
)

SCENARIO = "veyru"

ZERO_COST = EvaluationCost(
    usage=EvaluationTokenUsage(
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    ),
    estimated_cost_usd=0.0,
    model="test",
    provider_name="test",
)


def summary_for(run_dir: Any, run_dir_name: str) -> RunSummary:
    """A run summary pointing at a real directory on disk."""
    return RunSummary(
        run_id=f"{SCENARIO}/{run_dir_name}",
        scenario_name=SCENARIO,
        scenario_description="",
        scenario_config={"round_count": 15},
        timestamp=datetime(2026, 5, 4, tzinfo=UTC),
        total_messages=1,
        total_cost_usd=0.0,
        duration_seconds=0.0,
        status=RunStatus.SCENARIO_COMPLETE,
        has_evaluation=True,
        evaluation_in_progress=False,
        run_dir=str(run_dir),
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        resume_at_round_source=None,
        models=["opus"],
        provider="anthropic",
        agent_models=[
            AgentModelSummary(
                agent_id="field_observer",
                role_name="Field Observer",
                model="opus",
                provider="anthropic",
            )
        ],
        labels=["baseline_oss", "budget=800"],
        has_note=False,
        current_round=15,
        evaluation_content_hash=None,
    )


REPORT = EvaluationReport(
    simulation_id="sim-1",
    scenario_name=SCENARIO,
    measurements=[
        Measurement(
            metric_name="round_success",
            score=0.6,
            score_unit="fraction of rounds",
            summary="9 of 15",
            per_round=[RoundObservation(round_number=1, value=1.0, note="ok")],
            per_agent=[],
        )
    ],
    evaluation_cost=ZERO_COST,
)


@pytest.fixture(name="runs")
def runs_fixture(tmp_path: Any) -> list[RunSummary]:
    """Two run directories on disk, each with a report the exporter can read."""
    summaries: list[RunSummary] = []
    for name in ("1777638061", "1777638062"):
        run_dir = tmp_path / SCENARIO / name
        run_dir.mkdir(parents=True)
        (run_dir / f"{SCENARIO}.jsonl").write_text("{}\n")
        (run_dir / f"{SCENARIO}_report.json").write_bytes(REPORT.model_dump_json().encode())
        (run_dir / f"{SCENARIO}_debug.jsonl").write_text("noise\n")
        summaries.append(summary_for(run_dir=run_dir, run_dir_name=name))
    return summaries


def stub_resolution(
    monkeypatch: pytest.MonkeyPatch,
    summaries: list[RunSummary],
    missing: list[str],
) -> None:
    """Make the endpoints resolve to a fixed selection."""

    async def resolve(request: Request, selection: object) -> ResolvedSelection:
        """Answer with the fixed selection, ignoring the request."""
        _ = request, selection
        return ResolvedSelection(summaries=summaries, missing_run_ids=missing)

    monkeypatch.setattr(multi_export_router, "resolve_export_selection", resolve)


# A real Request so the handlers typecheck. Nothing reads it: the one thing that
# would, resolving the selection against the active group, is stubbed above.
REQUEST = Request(scope={"type": "http", "method": "POST", "headers": []})


def csv_request(
    frames: list[ExportFrame], columns: list[str], metrics: list[str]
) -> CsvExportRequest:
    """A CSV export body over a filter selection."""
    return CsvExportRequest(
        selection=FilterRunSelection(
            kind="filters",
            scenario=[],
            labels=[],
            run_id_contains=None,
            knob=[],
            status=None,
            contains_agent_id=None,
        ),
        frames=frames,
        columns=columns,
        metrics=metrics,
        repeat_run_columns=False,
        include_metric_summaries=False,
    )


async def body_of(response: StreamingResponse) -> bytes:
    """Drain a streaming response.

    The iterator is typed as yielding str or bytes, and these responses only ever
    yield bytes, so a str would mean the archive path changed underneath this.
    """
    collected = bytearray()
    async for chunk in response.body_iterator:
        assert isinstance(chunk, bytes)
        collected.extend(chunk)
    return bytes(collected)


# --- what the endpoints refuse --------------------------------------------------


async def test_a_csv_export_naming_no_tables_is_refused(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to emit cannot be what a caller meant."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    with pytest.raises(HTTPException) as raised:
        await export_runs_csv(
            body=csv_request(frames=[], columns=["status"], metrics=[]), request=REQUEST
        )
    assert raised.value.status_code == 422


async def test_a_csv_export_naming_no_columns_is_refused(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The identity columns alone are not an export anyone asked for."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    with pytest.raises(HTTPException) as raised:
        await export_runs_csv(
            body=csv_request(frames=[ExportFrame.RUN_LEVEL], columns=[], metrics=[]),
            request=REQUEST,
        )
    assert raised.value.status_code == 422


async def test_a_selection_matching_nothing_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty export is a mistake worth a status code."""
    stub_resolution(monkeypatch=monkeypatch, summaries=[], missing=[])
    with pytest.raises(HTTPException) as raised:
        await export_runs_csv(
            body=csv_request(frames=[ExportFrame.RUN_LEVEL], columns=["status"], metrics=[]),
            request=REQUEST,
        )
    assert raised.value.status_code == 422


async def test_a_download_naming_a_run_that_does_not_resolve_is_refused(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A table quietly missing a row someone asked for is the worst outcome."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[f"{SCENARIO}/999"])
    with pytest.raises(HTTPException) as raised:
        await export_runs_csv(
            body=csv_request(frames=[ExportFrame.RUN_LEVEL], columns=["status"], metrics=[]),
            request=REQUEST,
        )
    assert raised.value.status_code == 404
    assert f"{SCENARIO}/999" in str(raised.value.detail)


async def test_a_download_over_the_run_ceiling_is_refused(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ceiling names both numbers, so the message is actionable."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    monkeypatch.setattr(export_limits, "MAX_EXPORT_RUN_COUNT", 1)
    with pytest.raises(HTTPException) as raised:
        await export_runs_csv(
            body=csv_request(frames=[ExportFrame.RUN_LEVEL], columns=["status"], metrics=[]),
            request=REQUEST,
        )
    assert raised.value.status_code == 413
    assert "2 runs" in str(raised.value.detail)


async def test_a_csv_export_over_the_byte_ceiling_is_refused(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counted while writing, and nothing has been sent when it trips."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    monkeypatch.setattr(export_limits, "MAX_CSV_EXPORT_BYTES", 1)
    with pytest.raises(HTTPException) as raised:
        await export_runs_csv(
            body=csv_request(frames=[ExportFrame.RUN_LEVEL], columns=["status"], metrics=[]),
            request=REQUEST,
        )
    assert raised.value.status_code == 413


async def test_a_raw_export_over_the_byte_ceiling_is_refused(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sized before building, so the refusal costs no compression."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    monkeypatch.setattr(export_limits, "MAX_RAW_EXPORT_BYTES", 1)
    body = RawExportRequest(
        selection=ExplicitRunSelection(kind="explicit", run_ids=[r.run_id for r in runs]),
        include_logs=False,
    )
    with pytest.raises(HTTPException) as raised:
        await export_runs_raw(body=body, request=REQUEST)
    assert raised.value.status_code == 413


# --- the shape of an answer -----------------------------------------------------


async def test_one_table_comes_back_as_a_bare_csv(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A double-click on it opens a spreadsheet, which a zip does not."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    response = await export_runs_csv(
        body=csv_request(
            frames=[ExportFrame.RUN_LEVEL], columns=["status"], metrics=["round_success"]
        ),
        request=REQUEST,
    )
    assert response.media_type == "text/csv"
    assert "run_level_" in response.headers["content-disposition"]

    lines = (await body_of(response)).decode().splitlines()
    assert lines[0] == (
        "run_id,scenario_name,status,metric.round_success,metric_rounds.round_success"
    )
    assert len(lines) == 3


async def test_several_tables_come_back_as_a_zip_with_the_legend(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The legend is what explains a blank cell, so it travels with the tables."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    response = await export_runs_csv(
        body=csv_request(
            frames=[ExportFrame.RUN_LEVEL, ExportFrame.ROUND_LEVEL],
            columns=["status"],
            metrics=["round_success"],
        ),
        request=REQUEST,
    )
    assert response.media_type == "application/zip"

    with zipfile.ZipFile(io.BytesIO(await body_of(response))) as archive:
        assert sorted(archive.namelist()) == ["columns.csv", "round_level.csv", "run_level.csv"]


async def test_a_download_declares_its_length(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without it a browser cannot tell a truncated transfer from a complete one."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    response = await export_runs_csv(
        body=csv_request(frames=[ExportFrame.RUN_LEVEL], columns=["status"], metrics=[]),
        request=REQUEST,
    )
    declared = int(response.headers["content-length"])
    assert declared == len(await body_of(response))


async def test_the_raw_zip_nests_each_run_under_its_scenario(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extracting at the runs directory reproduces the tree."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    body = RawExportRequest(
        selection=ExplicitRunSelection(kind="explicit", run_ids=[r.run_id for r in runs]),
        include_logs=False,
    )
    response = await export_runs_raw(body=body, request=REQUEST)

    with zipfile.ZipFile(io.BytesIO(await body_of(response))) as archive:
        names = set(archive.namelist())
    assert f"{SCENARIO}/1777638061/{SCENARIO}.jsonl" in names
    assert f"{SCENARIO}/1777638061/{SCENARIO}_debug.jsonl" not in names
    assert "manifest.csv" in names


# --- the preview ----------------------------------------------------------------


async def test_the_preview_describes_the_columns_on_offer(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """What it offers is what the export can fill, computed from the same records."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    preview = await preview_multi_run_export(
        body=ExportPreviewRequest(
            selection=FilterRunSelection(
                kind="filters",
                scenario=[],
                labels=[],
                run_id_contains=None,
                knob=[],
                status=None,
                contains_agent_id=None,
            ),
            include_raw_size_estimate=False,
            include_logs=False,
        ),
        request=REQUEST,
    )
    assert preview.run_count == 2
    assert preview.evaluated_run_count == 2
    assert "knob.round_count" in {column.key for column in preview.columns}
    assert "label.budget" in {column.key for column in preview.columns}
    assert [metric.metric_name for metric in preview.metrics] == ["round_success"]
    assert preview.raw_bytes_estimate is None


async def test_the_preview_sizes_the_raw_export_with_the_logs_setting(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The estimate sits under the checkbox that changes it, so it has to move."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])

    async def estimate(include_logs: bool) -> int:
        """Ask the preview for a size with the given logs setting."""
        preview = await preview_multi_run_export(
            body=ExportPreviewRequest(
                selection=FilterRunSelection(
                    kind="filters",
                    scenario=[],
                    labels=[],
                    run_id_contains=None,
                    knob=[],
                    status=None,
                    contains_agent_id=None,
                ),
                include_raw_size_estimate=True,
                include_logs=include_logs,
            ),
            request=REQUEST,
        )
        assert preview.raw_bytes_estimate is not None
        return preview.raw_bytes_estimate

    assert await estimate(include_logs=True) > await estimate(include_logs=False)


async def test_the_preview_answers_an_oversized_selection_rather_than_refusing(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller renders the count against the ceiling; an error string cannot.

    It also must not read a report per run to do it, which is why the offered
    columns come back empty.
    """
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    monkeypatch.setattr(export_limits, "MAX_EXPORT_RUN_COUNT", 1)

    preview = await preview_multi_run_export(
        body=ExportPreviewRequest(
            selection=FilterRunSelection(
                kind="filters",
                scenario=[],
                labels=[],
                run_id_contains=None,
                knob=[],
                status=None,
                contains_agent_id=None,
            ),
            include_raw_size_estimate=False,
            include_logs=False,
        ),
        request=REQUEST,
    )
    assert preview.run_count == 2
    assert preview.max_run_count == 1
    assert preview.columns == []
    assert preview.metrics == []


async def test_the_preview_reports_every_ceiling_it_is_held_to(
    runs: list[RunSummary], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller states the limit the endpoint enforces rather than a copy of it."""
    stub_resolution(monkeypatch=monkeypatch, summaries=runs, missing=[])
    preview = await preview_multi_run_export(
        body=ExportPreviewRequest(
            selection=FilterRunSelection(
                kind="filters",
                scenario=[],
                labels=[],
                run_id_contains=None,
                knob=[],
                status=None,
                contains_agent_id=None,
            ),
            include_raw_size_estimate=False,
            include_logs=False,
        ),
        request=REQUEST,
    )
    assert preview.max_run_count == export_limits.MAX_EXPORT_RUN_COUNT
    assert preview.max_raw_bytes == export_limits.MAX_RAW_EXPORT_BYTES
    assert preview.max_csv_bytes == export_limits.MAX_CSV_EXPORT_BYTES
