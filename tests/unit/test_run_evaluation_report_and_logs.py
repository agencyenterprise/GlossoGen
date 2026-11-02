"""Replacing a run's evaluation report over HTTP, and reading it and the run's logs back.

``glossogen sync-metadata-to-prod`` pushes reports with the PUT, and the run page
reads the report, the evaluation's stdout and the simulation's debug log with the
GETs. Driven through the app with no database, so the report file in the run
directory is the only place a report is kept.
"""

from pathlib import Path
from typing import Any

import orjson

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.reports.evaluation_cost import EvaluationCost, EvaluationTokenUsage
from glossogen.evaluation.reports.evaluation_report import EvaluationReport, load_report
from glossogen.run_file_paths import debug_log_path, evaluation_report_path
from tests.fakes.local_app import (
    GROUP_API,
    build_local_app,
    local_client,
    one_round_run_events,
    write_event_log,
)

SCENARIO = "veyru"
RUN = "1770000100"
RUN_API = f"{GROUP_API}/runs/{SCENARIO}/{RUN}"


def _write_run(runs_dir: Path) -> Path:
    return write_event_log(
        runs_dir=runs_dir,
        scenario_name=SCENARIO,
        run_dir_name=RUN,
        events=one_round_run_events(scenario_name=SCENARIO, run_dir_name=RUN, finished=True),
        extra_records=[],
    )


def _measurement(metric_name: str, score: float) -> Measurement:
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit="chars",
        summary=f"{metric_name}={score}",
        per_round=[],
        per_agent=[],
    )


def _report(measurements: list[Measurement]) -> EvaluationReport:
    return EvaluationReport(
        simulation_id=f"{SCENARIO}/{RUN}",
        scenario_name=SCENARIO,
        measurements=measurements,
        evaluation_cost=EvaluationCost(
            usage=EvaluationTokenUsage(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            estimated_cost_usd=0.01,
            model="claude-haiku-4-5-20251001",
            provider_name="anthropic",
        ),
    )


def _report_path(run_dir: Path) -> Path:
    return evaluation_report_path(run_dir=run_dir, scenario_name=SCENARIO)


def _write_report(run_dir: Path, report: EvaluationReport) -> None:
    _report_path(run_dir=run_dir).write_bytes(orjson.dumps(report.model_dump(mode="json")))


def _metric_scores(body: dict[str, Any]) -> dict[str, float]:
    return {m["metric_name"]: m["score"] for m in body["measurements"]}


async def test_putting_a_report_replaces_every_measurement_of_the_old_one(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir)
    _write_report(
        run_dir=run_dir,
        report=_report(
            measurements=[
                _measurement(metric_name="mean_chars_per_message", score=12.0),
                _measurement(metric_name="gzip_compression_ratio", score=0.4),
            ]
        ),
    )
    replacement = _report(
        measurements=[_measurement(metric_name="mean_chars_per_message", score=0.0)]
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.put(
            f"{RUN_API}/evaluation", json=replacement.model_dump(mode="json")
        )
        read_back = await client.get(f"{RUN_API}/evaluation")

    assert response.status_code == 200, response.text
    assert response.json() == {"run_id": f"{SCENARIO}/{RUN}", "measurement_count": 1}
    assert await load_report(report_path=_report_path(run_dir=run_dir)) == replacement
    assert _metric_scores(body=read_back.json()) == {"mean_chars_per_message": 0.0}


async def test_putting_a_report_on_a_run_never_evaluated_creates_it(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir)
    report = _report(measurements=[_measurement(metric_name="gzip_compression_ratio", score=0.4)])

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        before = await client.get(f"{RUN_API}/evaluation")
        response = await client.put(f"{RUN_API}/evaluation", json=report.model_dump(mode="json"))

    assert before.status_code == 200
    assert before.json() is None
    assert response.status_code == 200, response.text
    assert await load_report(report_path=_report_path(run_dir=run_dir)) == report


async def test_a_malformed_report_is_refused_and_the_old_one_kept(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir)
    kept = _report(measurements=[_measurement(metric_name="gzip_compression_ratio", score=0.4)])
    _write_report(run_dir=run_dir, report=kept)
    malformed = kept.model_dump(mode="json")
    del malformed["evaluation_cost"]

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.put(f"{RUN_API}/evaluation", json=malformed)

    assert response.status_code == 422
    assert await load_report(report_path=_report_path(run_dir=run_dir)) == kept


async def test_putting_a_report_on_an_unknown_run_answers_404_and_writes_nothing(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    report = _report(measurements=[])

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.put(f"{RUN_API}/evaluation", json=report.model_dump(mode="json"))

    assert response.status_code == 404
    assert not (runs_dir / SCENARIO).exists()


async def test_an_unreadable_report_reads_as_not_evaluated(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir)
    _report_path(run_dir=run_dir).write_bytes(b"{not json")

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{RUN_API}/evaluation")

    assert response.status_code == 200
    assert response.json() is None


async def test_the_evaluation_log_is_served_as_numbered_lines(tmp_path: Path) -> None:
    """Bytes that are not UTF-8 are replaced, so a garbled log still reads."""
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir)
    (run_dir / "eval_stdout.log").write_bytes(
        b"Evaluating veyru\n\xff judged\nEvaluation complete\n"
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{RUN_API}/eval-logs")

    assert response.status_code == 200
    assert response.json() == {
        "lines": [
            {"line_number": 1, "text": "Evaluating veyru"},
            {"line_number": 2, "text": "� judged"},
            {"line_number": 3, "text": "Evaluation complete"},
        ]
    }


async def test_a_run_with_no_logs_serves_none(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _write_run(runs_dir=runs_dir)

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        eval_logs = await client.get(f"{RUN_API}/eval-logs")
        debug_logs = await client.get(f"{RUN_API}/debug-logs")

    assert eval_logs.json() == {"lines": []}
    assert debug_logs.json() == {"entries": []}


async def test_the_debug_log_is_served_skipping_lines_it_cannot_read(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _write_run(runs_dir=runs_dir)
    entry = {
        "timestamp": "2026-01-01T00:00:01+00:00",
        "logger": "glossogen.runtime.game_clock",
        "level": "INFO",
        "message": "Round 1 started",
    }
    debug_log_path(run_dir=run_dir, scenario_name=SCENARIO).write_bytes(
        orjson.dumps(entry)
        + b"\n{truncated\n"
        + orjson.dumps({"timestamp": "2026-01-01T00:00:02+00:00", "level": "INFO"})
        + b"\n\n"
        + orjson.dumps({**entry, "level": "WARNING", "message": "slow reply"})
        + b"\n"
    )

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        response = await client.get(f"{RUN_API}/debug-logs")

    assert response.status_code == 200
    assert response.json() == {
        "entries": [
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "logger_name": "glossogen.runtime.game_clock",
                "level": "INFO",
                "message": "Round 1 started",
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "logger_name": "glossogen.runtime.game_clock",
                "level": "WARNING",
                "message": "slow reply",
            },
        ]
    }


async def test_the_log_reads_answer_404_for_an_unknown_run(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    async with local_client(app=build_local_app(runs_dir=runs_dir)) as client:
        eval_logs = await client.get(f"{RUN_API}/eval-logs")
        debug_logs = await client.get(f"{RUN_API}/debug-logs")

    assert eval_logs.status_code == 404
    assert debug_logs.status_code == 404
