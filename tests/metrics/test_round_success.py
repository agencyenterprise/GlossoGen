"""`round_success`: the verdicts a scenario recorded, counted.

The headline experimental result. It reads `RoundResultRecorded` events that
the game clock writes from `judge_round_result`, so this test covers the path
from a scenario's own judgement to the number a comparison is built on.
"""

from pathlib import Path

import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from tests.metrics.conftest import METRIC_RUN_GROUP, ROUND_COUNT

pytestmark = METRIC_RUN_GROUP

METRIC = "round_success"


async def test_it_reports_the_verdicts_the_scenario_recorded(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The smoke scenario passes a round when a finding was recorded in it.

    This run records none, so every round fails and the score is zero. A metric
    that ignored the events and reported a default would land somewhere else.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(0.0)
    assert all(observation.value == 0.0 for observation in measurement.per_round)


async def test_it_counts_every_round_not_just_the_ones_with_traffic(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both rounds are scored, though only one carried messages.

    A round-level metric that silently skipped silent rounds would report a
    denominator smaller than the run, and every rate computed from it would be
    wrong in the flattering direction.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.measurement(metric_name=METRIC).per_round) == ROUND_COUNT


async def test_a_single_team_scenario_emits_one_unsuffixed_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-team scenarios suffix by team; a single-team run must not.

    Analysis tooling looks the plain name up, so a stray suffix here reads as a
    run with no round_success at all.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )
    assert scored.names() == [METRIC]
