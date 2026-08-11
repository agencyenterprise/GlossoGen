"""`dialog_retransmission`: how much of the channel is talk about the channel.

Counts dialog turns and retransmission requests per round. A protocol that
needs constant "say again" is paying for its compression somewhere else, and
this is where that cost shows up.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metrics.dialog_retransmission_metric import (
    DialogRetransmissionOutput,
    RoundCommCounts,
)
from tests.metrics.conftest import FIRST_TEXT, METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "dialog_retransmission"
REPLICAS = 3
# The registry name is not what lands in the report: this metric splits its
# answer into two measurements. Analysis tooling looking up "dialog_retransmission"
# finds nothing, which is worth knowing before writing a query against it.
DIALOG = "dialog_count"
RETRANSMISSION = "retransmission_request_count"


def counts(*, dialog: int, retransmissions: int) -> DialogRetransmissionOutput:
    """A judge reply reporting one round's counts."""
    return DialogRetransmissionOutput(
        per_round_counts=[
            RoundCommCounts(
                round_number=1,
                dialog_count=dialog,
                retransmission_request_count=retransmissions,
                evidence="agents traded a clarification",
            )
        ],
        explanation="One round of back-and-forth.",
    )


async def test_it_averages_the_replicas_and_reads_this_run(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three replicas, averaged, over the run's own transcript."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[counts(dialog=2, retransmissions=1)] * REPLICAS,
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert sorted(scored.names()) == sorted([DIALOG, RETRANSMISSION])
    assert scored.measurement(metric_name=DIALOG).score == pytest.approx(2.0)
    assert scored.measurement(metric_name=RETRANSMISSION).score == pytest.approx(1.0)
    assert len(scored.judge.calls) == REPLICAS
    assert FIRST_TEXT in scored.judge.calls[0].messages[0].content


async def test_it_writes_nothing_when_every_replica_fails(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge that never answered produced no observation, so none is recorded.

    This is the behaviour `language_repetition` is missing: same three-replica
    shape, but a total judge failure here yields no measurement rather than a
    number that reads as a clean result.
    """
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert len(scored.judge.calls) == REPLICAS
    assert not scored.has(metric_name=DIALOG)
    assert not scored.has(metric_name=RETRANSMISSION)
