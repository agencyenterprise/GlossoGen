"""`postmortem_ended_timeout`: postmortems cut off by the clock, not by silence.

A postmortem that runs out of wall clock was still in progress when it ended,
so whatever the agents were working out did not finish. Distinguishing that
from one that ended because everyone was done changes what the round's
discussion means.
"""

from pathlib import Path

import pytest

from tests.metrics.conftest import METRIC_RUN_GROUP, ROUND_COUNT
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "postmortem_ended_timeout"


async def test_it_counts_the_phases_the_clock_cut_off(
    timed_out_postmortem_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every round's postmortem times out here, so every round is flagged.

    The final round is the one worth having: its postmortem end is not followed
    by a `round_advanced`, so a metric reading only advance events would miss
    it and under-report by one on every run.
    """
    scored = await score_metrics(
        run=timed_out_postmortem_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(float(ROUND_COUNT))
    assert sorted(o.round_number for o in measurement.per_round) == list(range(1, ROUND_COUNT + 1))
    assert scored.judge.calls == []


async def test_a_run_with_no_postmortem_writes_no_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hybrid contract, and the reason this metric has two absent cases.

    Zero would mean "postmortems ran and none was cut off", which is a claim
    about a phase that never happened. A run with no postmortem at all reports
    nothing instead.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.report.measurements == []
