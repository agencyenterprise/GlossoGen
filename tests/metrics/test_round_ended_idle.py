"""`round_ended_idle`: how many rounds ended because everyone stopped talking.

Distinguishes a round that finished from one that ran out of wall clock. A run
whose rounds all time out is a run whose agents were still working when the
clock cut them off, and its throughput numbers mean something different.
"""

from pathlib import Path

import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from tests.metrics.conftest import METRIC_RUN_GROUP, ROUND_COUNT

pytestmark = METRIC_RUN_GROUP

METRIC = "round_ended_idle"


async def test_it_counts_the_rounds_that_ended_on_idle(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every round here ends with both agents parked on a poll."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(float(ROUND_COUNT))
    assert len(measurement.per_round) == ROUND_COUNT


async def test_the_timeout_counterpart_stays_at_zero(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two partition the run, so idle and timeout must not both fire.

    Asserting only the idle count would pass just as well if every round were
    counted twice.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=["round_ended_timeout"],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name="round_ended_timeout")
    assert measurement.score == pytest.approx(0.0)
    assert measurement.per_round == []
