"""`mean_chars_per_message`: the same corpus, normalised by message count.

Separates per-message verbosity from message density. A round that needs more
back-and-forth inflates `mean_chars_per_round` without either agent becoming
wordier; this metric is what tells the two apart, so the pair is only useful if
both are right.
"""

from pathlib import Path

import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from glossogen.testing.smoke_scenario import LINK_CHANNEL_ID
from tests.metrics.conftest import (
    FIRST_TEXT,
    MESSAGES_TOTAL,
    METRIC_RUN_GROUP,
    SECOND_TEXT,
    TOTAL_CHARS,
)

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


async def test_it_reports_the_spread_of_message_lengths(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half the messages are one length and half the other, so the std is half the gap."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    mean_chars = TOTAL_CHARS / MESSAGES_TOTAL
    std_chars = abs(len(FIRST_TEXT) - len(SECOND_TEXT)) / 2
    assert [observation.value for observation in measurement.per_round] == [
        pytest.approx(mean_chars)
    ]
    assert measurement.per_round[0].note == f"{MESSAGES_TOTAL} messages, std={std_chars:.2f}"
    assert measurement.summary == (
        f"{MESSAGES_TOTAL} messages on {LINK_CHANNEL_ID} across 1 rounds; "
        f"mean {mean_chars:.2f} chars/message (std {std_chars:.2f})"
    )
