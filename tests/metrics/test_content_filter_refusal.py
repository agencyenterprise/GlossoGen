"""`content_filter_refusal`: how often a provider refused an agent's cycle.

A refusal wastes a cycle and signals the safety classifier reacting to
something in the prompt. Runs with many of them are not comparable to runs
without, so a zero here has to mean zero rather than "not measured".
"""

from pathlib import Path

import pytest

from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "content_filter_refusal"


async def test_a_clean_run_scores_zero_and_still_reports(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero refusals is a measurement, not a reason to skip.

    This metric is on the other side of the line from
    `round_success_after_resume`: the count is legitimately zero, so the report
    records it. Dropping the entry would make "no refusals" and "never
    evaluated" the same thing in the corpus.
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
    assert measurement.per_round == []
    assert measurement.per_agent == []
    assert scored.judge.calls == []
