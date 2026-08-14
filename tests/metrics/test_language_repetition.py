"""`language_repetition`: how many times each message re-encodes its own content.

The compression signal for noisy channels: `12 12`, `12 twelve`, `gnt gentle`
all say one thing more than once. Judged per message, three replicas per round,
averaged. 1.0 means each piece of information appears once.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metrics.language_repetition_metric import (
    MessageRepetition,
    RoundRepetitionOutput,
)
from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from tests.metrics.conftest import FIRST_TEXT, MESSAGES_TOTAL, METRIC_RUN_GROUP, SECOND_TEXT

pytestmark = METRIC_RUN_GROUP

METRIC = "language_repetition"
# One call per round with messages, three replicas each.
REPLICAS = 3


def every_message_at(*, factor: float) -> RoundRepetitionOutput:
    """A judge reply giving every message in the round the same factor."""
    return RoundRepetitionOutput(
        per_message=[
            MessageRepetition(message_number=number, repetition_factor=factor)
            for number in range(1, MESSAGES_TOTAL + 1)
        ]
    )


async def test_it_averages_the_replicas_into_one_factor(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three replicas per round, so a stable judge gives back its own number."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[every_message_at(factor=2.0)] * REPLICAS,
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(2.0)
    assert len(scored.judge.calls) == REPLICAS
    assert FIRST_TEXT in scored.judge.calls[0].messages[0].content
    assert SECOND_TEXT in scored.judge.calls[0].messages[0].content


async def test_a_factor_below_one_is_floored(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A message cannot encode its content less than once.

    The unit only makes sense at or above 1.0, and a judge that returns 0.5
    would otherwise drag a run's mean below the floor its own scale defines.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[every_message_at(factor=0.25)] * REPLICAS,
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.measurement(metric_name=METRIC).score == pytest.approx(1.0)


async def test_a_dead_judge_produces_no_measurement(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every replica fails, so there is nothing to report and nothing is reported.

    Reporting 1.0 would be the healthiest value the scale defines, and
    indistinguishable from a judge that read the run and found no redundancy.
    It also filled the score list unconditionally, which made the caller's
    "every judge replica failed" guard unreachable dead code.

    `dialog_retransmission` has the identical three-replica structure and
    behaves the same way, which is what keeps the two comparable when a judge
    goes down mid-evaluation.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.judge.calls) == REPLICAS, "the judge was asked and failed every time"
    assert not scored.has(metric_name=METRIC)
    assert scored.report.measurements == []


async def test_a_message_no_replica_scored_is_dropped_not_invented(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge that answers for only some messages must not have the rest filled in.

    The prompt asks for one entry per enumerated message and nothing enforces
    it. A message no replica scored has no observation, so inventing 1.0 for it
    drags the round mean toward "no redundancy" using data nobody produced.
    """
    partial = RoundRepetitionOutput(
        per_message=[MessageRepetition(message_number=1, repetition_factor=3.0)]
    )
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[partial] * REPLICAS,
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    # Only message 1 was scored, so the round mean is its factor alone rather
    # than that factor diluted by three invented 1.0s.
    assert scored.measurement(metric_name=METRIC).score == pytest.approx(3.0)
