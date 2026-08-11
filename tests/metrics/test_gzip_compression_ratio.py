"""`gzip_compression_ratio`: per-message DEFLATE compressibility.

`len(deflate(text)) / len(text)`, so **lower means more repetitive**. DEFLATE
exploits repeated substrings, which is what a protocol that re-uses tokens
produces. Complements `message_entropy`: entropy is blind to order, DEFLATE is
not.
"""

from pathlib import Path

import pytest

from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "gzip_compression_ratio"


async def ratio_for(
    *, run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str
) -> float:
    """Score one run and return its mean compression ratio."""
    scored = await score_metrics(
        run=run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / f"{label}.json",
        monkeypatch=monkeypatch,
    )
    assert scored.judge.calls == []
    return scored.measurement(metric_name=METRIC).score


async def test_repetitive_text_compresses_better_than_varied_text(
    known_entropy_run: MetricRun,
    high_entropy_run: MetricRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The comparison is the assertion, because the absolute value is not stable.

    DEFLATE's header still counts at this size, so both ratios can sit above
    1.0 and pinning either would pin the zlib version rather than the metric.
    What has to hold is the direction. Both corpora use messages of exactly the
    same length, so the only thing separating them is repetition: one is a
    single character repeated, the other has no character twice. A metric
    reporting a constant fails this while passing any bound.
    """
    repetitive = await ratio_for(
        run=known_entropy_run, tmp_path=tmp_path, monkeypatch=monkeypatch, label="repetitive"
    )
    varied = await ratio_for(
        run=high_entropy_run, tmp_path=tmp_path, monkeypatch=monkeypatch, label="varied"
    )

    assert repetitive < varied, (
        f"repetitive corpus scored {repetitive:.3f} and varied scored {varied:.3f}; "
        f"lower means more compressible, so the repetitive one has to be lower"
    )


async def test_it_reports_a_ratio_per_round_without_a_judge(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic, and every round with messages contributes one observation."""
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.per_round
    assert all(observation.value > 0.0 for observation in measurement.per_round)
    assert scored.judge.calls == []
