"""`mean_chars_per_round`: total characters on the primary channel, per round.

The headline throughput number. In veyru it maps directly onto the round's
time budget, one character costing one simulated second, so a drift here moves
every budget comparison in the corpus.
"""

from pathlib import Path

import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from tests.metrics.conftest import (
    MESSAGES_TOTAL,
    METRIC_RUN_GROUP,
    ROUNDS_WITH_MESSAGES,
    TOTAL_CHARS,
)

pytestmark = METRIC_RUN_GROUP

METRIC = "mean_chars_per_round"


async def test_it_totals_the_primary_channel_over_rounds_that_carried_it(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rounds with no messages are not averaged in.

    That is why the score is round 1's total rather than half of it: the metric
    averages over rounds that had traffic, not over the run's rounds. A silent
    round would otherwise halve the throughput of a run that sent exactly as
    much as another.
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
    assert measurement.score == pytest.approx(float(TOTAL_CHARS))
    assert measurement.score_unit == "chars/round"
    assert len(measurement.per_round) == ROUNDS_WITH_MESSAGES
    assert measurement.per_round[0].value == pytest.approx(float(TOTAL_CHARS))
    assert measurement.per_round[0].note == f"{MESSAGES_TOTAL} messages"


async def test_it_never_calls_the_judge(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic means reproducible and free.

    The judge is queued with no responses, so any call fails rather than
    costing money on every evaluation in production.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )
    assert scored.judge.calls == []
