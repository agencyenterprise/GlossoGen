"""A run summary carries the scores in the run's evaluation report.

The runs list shows them when the Evaluated badge is hovered, so they travel with
the summary rather than being fetched per run. The reader holds them per version
of the report file, which these tests change by rewriting it with a different
size, so no test depends on how finely the filesystem records modification time.
"""

import logging
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.reports.evaluation_report import EvaluationReport, write_report
from glossogen.server.runs.derived_run_references import headline_measurements_of
from glossogen.server.runs.discovery import build_summary
from glossogen.server.runs.evaluation_score_reader import (
    EvaluationReportScores,
    read_evaluation_scores,
)
from glossogen.server.runs.models import EvaluationScore
from tests.fakes.export_run_records import ZERO_COST


def _measurement(metric_name: str, score: float, score_unit: str) -> Measurement:
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit=score_unit,
        summary=f"{metric_name} summary",
        per_round=[RoundObservation(round_number=1, value=score, note="round note")],
        per_agent=[],
    )


async def _write(report_path: Path, measurements: list[Measurement]) -> None:
    await write_report(
        report=EvaluationReport(
            simulation_id="smoke/1700000000",
            scenario_name="smoke",
            measurements=measurements,
            evaluation_cost=ZERO_COST,
        ),
        report_path=report_path,
    )


def _score(metric_name: str, score: float, score_unit: str) -> EvaluationScore:
    return EvaluationScore(
        metric_name=metric_name,
        score=score,
        score_unit=score_unit,
        summary=f"{metric_name} summary",
    )


def test_a_run_without_a_report_has_no_scores(tmp_path: Path) -> None:
    assert read_evaluation_scores(
        report_path=tmp_path / "smoke_report.json"
    ) == EvaluationReportScores(has_report=False, scores=[])


def test_a_report_path_whose_parent_is_a_file_is_no_report(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "1700000000").write_text("a file where the run directory would be")

    with caplog.at_level(logging.ERROR):
        result = read_evaluation_scores(report_path=tmp_path / "1700000000" / "smoke_report.json")

    assert result == EvaluationReportScores(has_report=False, scores=[])
    assert len(caplog.records) == 1


async def test_scores_keep_the_report_order(tmp_path: Path) -> None:
    report_path = tmp_path / "smoke_report.json"
    await _write(
        report_path=report_path,
        measurements=[
            _measurement(metric_name="round_success", score=0.75, score_unit="fraction"),
            _measurement(metric_name="perplexity", score=3.25, score_unit="nats"),
        ],
    )

    assert read_evaluation_scores(report_path=report_path) == EvaluationReportScores(
        has_report=True,
        scores=[
            _score(metric_name="round_success", score=0.75, score_unit="fraction"),
            _score(metric_name="perplexity", score=3.25, score_unit="nats"),
        ],
    )


async def test_a_rewritten_report_is_read_again(tmp_path: Path) -> None:
    report_path = tmp_path / "smoke_report.json"
    await _write(
        report_path=report_path,
        measurements=[_measurement(metric_name="round_success", score=0.5, score_unit="fraction")],
    )
    read_evaluation_scores(report_path=report_path)

    await _write(
        report_path=report_path,
        measurements=[
            _measurement(metric_name="round_success", score=0.9, score_unit="fraction"),
            _measurement(metric_name="neologism", score=2.0, score_unit="rounds"),
        ],
    )

    assert read_evaluation_scores(report_path=report_path) == EvaluationReportScores(
        has_report=True,
        scores=[
            _score(metric_name="round_success", score=0.9, score_unit="fraction"),
            _score(metric_name="neologism", score=2.0, score_unit="rounds"),
        ],
    )


def test_an_unparseable_report_is_distinguished_from_an_empty_one_and_logs_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    report_path = tmp_path / "smoke_report.json"
    report_path.write_text('{"measurements": [')

    with caplog.at_level(logging.ERROR):
        first = read_evaluation_scores(report_path=report_path)
        second = read_evaluation_scores(report_path=report_path)

    assert first == EvaluationReportScores(has_report=True, scores=None)
    assert second == EvaluationReportScores(has_report=True, scores=None)
    assert len(caplog.records) == 1


def test_headline_scores_are_the_round_success_family_after_resume_first() -> None:
    scores = [
        _score(metric_name="perplexity", score=3.0, score_unit="nats"),
        _score(metric_name="round_success_team_b", score=0.5, score_unit="fraction"),
        _score(metric_name="round_success_after_resume", score=0.7, score_unit="fraction"),
        _score(metric_name="round_success_team_a", score=0.6, score_unit="fraction"),
        _score(metric_name="round_success", score=0.4, score_unit="fraction"),
    ]

    assert [m.metric_name for m in headline_measurements_of(scores=scores)] == [
        "round_success_after_resume",
        "round_success",
        "round_success_team_a",
    ]


def _current_cache() -> dict[str, Any]:
    """A summary cache in the current shape, with every required field."""
    return {
        "scenario_name": "smoke",
        "scenario_description": "cached run",
        "scenario_config": {"round_count": 3},
        "provider": "anthropic",
        "total_messages": 12,
        "total_cost_usd": 0.5,
        "duration_seconds": 60.0,
        "status": "scenario_complete",
        "models": ["claude-sonnet-4-6"],
        "agent_models": [
            {
                "agent_id": "first_agent",
                "role_name": "First Agent",
                "model": "claude-sonnet-4-6",
                "provider": "anthropic",
                "played": [
                    {"model": "claude-sonnet-4-6", "provider": "anthropic", "from_round": 1}
                ],
            }
        ],
        "current_round": 3,
        "round_results": [],
        "fork_source": None,
        "replace_agent_source": None,
        "cross_run_replace_agent_source": None,
        "fork_at_round_source": None,
    }


async def test_a_run_summary_carries_its_report_scores(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    (run_dir / "smoke.jsonl").write_text("this is not json\n")
    (run_dir / "run_summary_cache.json").write_bytes(orjson.dumps(_current_cache()))
    await _write(
        report_path=run_dir / "smoke_report.json",
        measurements=[_measurement(metric_name="round_success", score=1.0, score_unit="fraction")],
    )

    summary = await build_summary(
        scenario_name="smoke",
        timestamp_dir=run_dir,
        evaluation_content_hash=None,
    )

    assert summary is not None
    assert summary.has_evaluation
    assert summary.evaluation_scores == [
        _score(metric_name="round_success", score=1.0, score_unit="fraction")
    ]


async def test_an_unevaluated_run_summary_has_no_scores(tmp_path: Path) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    (run_dir / "smoke.jsonl").write_text("this is not json\n")
    (run_dir / "run_summary_cache.json").write_bytes(orjson.dumps(_current_cache()))

    summary = await build_summary(
        scenario_name="smoke",
        timestamp_dir=run_dir,
        evaluation_content_hash=None,
    )

    assert summary is not None
    assert not summary.has_evaluation
    assert summary.evaluation_scores == []


async def test_a_run_summary_reports_an_unreadable_report_as_null_scores(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    run_dir = tmp_path / "1700000000"
    run_dir.mkdir()
    (run_dir / "smoke.jsonl").write_text("this is not json\n")
    (run_dir / "run_summary_cache.json").write_bytes(orjson.dumps(_current_cache()))
    (run_dir / "smoke_report.json").write_text("{not a report")

    with caplog.at_level(logging.ERROR):
        summary = await build_summary(
            scenario_name="smoke",
            timestamp_dir=run_dir,
            evaluation_content_hash=None,
        )

    assert summary is not None
    assert summary.has_evaluation
    assert summary.evaluation_scores is None
