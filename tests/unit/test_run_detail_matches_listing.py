"""A run's detail page reports what the runs list reports for the same run.

Both read the not-ended status and a derived run's duration through
``discovery``. The detail page also reads an unreadable evaluation report as no
evaluation, the way the list, the exports and the MCP browser do.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from glossogen.models.event import (
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
)
from glossogen.run_derivation.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.server.runs.detail_reader import load_evaluation_report, load_run_detail
from glossogen.server.runs.discovery import build_summary

# The run directory is created after its source run started, as a derived run's is.
SOURCE_STARTED_AT = datetime.fromtimestamp(1_700_000_000, tz=UTC)
RUN_DIR_NAME = "1700000600"
ENDED_AT = datetime.fromtimestamp(1_700_000_700, tz=UTC)


def _write_log(run_dir: Path, ended: bool) -> Path:
    """Write a log that opens with the source run's start, as a derived run's does."""
    run_dir.mkdir(parents=True)
    events: list[SimulationEvent] = [
        SimulationStarted(
            round_number=0,
            run_id=f"smoke/{run_dir.name}",
            scenario_name="smoke",
            scenario_description="",
            channel_ids=["link"],
            provider="anthropic",
            scenario_config={},
        ).model_copy(update={"timestamp": SOURCE_STARTED_AT})
    ]
    if ended:
        events.append(
            SimulationEnded(
                round_number=3,
                reason=RunStatus.SCENARIO_COMPLETE,
                total_messages=0,
                total_cost_usd=0.0,
            ).model_copy(update={"timestamp": ENDED_AT})
        )
    log_path = run_dir / "smoke.jsonl"
    log_path.write_bytes(b"\n".join(event.model_dump_json().encode() for event in events) + b"\n")
    return log_path


def _write_fork_manifest(run_dir: Path) -> None:
    (run_dir / "fork_manifest.json").write_bytes(
        orjson.dumps(
            {
                "source_run_id": "smoke/1700000000",
                "target_message_id": "message-1",
                "forked_at": 1_700_000_600.0,
            }
        )
    )


def _write_cross_run_manifest(run_dir: Path) -> None:
    manifest = CrossRunReplaceManifest(
        source_a_run_id="smoke/1700000000",
        source_a_run_dir="runs/smoke/1700000000",
        source_b_run_id="smoke/1690000000",
        source_b_run_dir="runs/smoke/1690000000",
        imported_history_source="imported_history.jsonl",
        round_start=2,
        rounds_after_swap=1,
        target_event_id="evt-a",
        source_b_round_end=1,
        source_b_cutoff_event_id="evt-b",
        replaced_agent_id="first_agent",
        imported_model="claude-sonnet-4-6",
        imported_provider="anthropic",
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=1_700_000_600.0,
    )
    (run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())


async def test_a_starting_cross_run_replace_run_is_starting_in_both(tmp_path: Path) -> None:
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    log_path = _write_log(run_dir=run_dir, ended=False)
    _write_cross_run_manifest(run_dir=run_dir)

    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )
    detail = await load_run_detail(log_path=log_path, children=[])

    assert summary is not None
    assert summary.status == RunStatus.STARTING
    assert detail.status == RunStatus.STARTING


async def test_a_derived_run_has_the_same_duration_in_both(tmp_path: Path) -> None:
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    log_path = _write_log(run_dir=run_dir, ended=True)
    _write_fork_manifest(run_dir=run_dir)

    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )
    detail = await load_run_detail(log_path=log_path, children=[])

    assert summary is not None
    assert summary.duration_seconds == 100.0
    assert detail.duration_seconds == 100.0


async def test_an_original_run_measures_from_its_start_in_both(tmp_path: Path) -> None:
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    log_path = _write_log(run_dir=run_dir, ended=True)

    summary = await build_summary(
        scenario_name="smoke", timestamp_dir=run_dir, evaluation_content_hash=None
    )
    detail = await load_run_detail(log_path=log_path, children=[])

    assert summary is not None
    assert summary.duration_seconds == 700.0
    assert detail.duration_seconds == 700.0


async def test_an_unreadable_report_is_no_evaluation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    run_dir = tmp_path / "smoke" / RUN_DIR_NAME
    log_path = _write_log(run_dir=run_dir, ended=True)
    report_path = run_dir / "smoke_report.json"
    report_path.write_text("{not a report")

    with caplog.at_level(logging.ERROR):
        evaluation = await load_evaluation_report(report_path=report_path)
        detail = await load_run_detail(log_path=log_path, children=[])

    assert evaluation is None
    assert detail.evaluation is None
    report_logs = [record for record in caplog.records if str(report_path) in record.getMessage()]
    assert len(report_logs) == 2
