"""`mean_chars_per_message`: the same corpus, normalised by message count.

Separates per-message verbosity from message density. A round that needs more
back-and-forth inflates `mean_chars_per_round` without either agent becoming
wordier; this metric is what tells the two apart, so the pair is only useful if
both are right.
"""

from pathlib import Path

import pytest

from tests.metrics.conftest import MESSAGES_TOTAL, METRIC_RUN_GROUP, TOTAL_CHARS
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "mean_chars_per_message"


async def test_it_divides_the_corpus_by_message_count(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scored against the same run as `mean_chars_per_round`, so the two compare."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(TOTAL_CHARS / MESSAGES_TOTAL)
    assert scored.judge.calls == []
