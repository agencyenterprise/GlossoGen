"""`message_entropy`: within-message character Shannon entropy, in bits/char.

A judge-free redundancy signal. A protocol that settles into a small symbol
vocabulary drops in entropy, which is the emergence these runs exist to detect,
so the number has to track the character distribution and not just message size.
"""

from pathlib import Path

import pytest

from glossogen.testing.metric_harness import NO_OPTIONS, MetricRun, score_metrics
from tests.metrics.conftest import (
    ALTERNATING_ENTROPY_BITS,
    FLAT_ENTROPY_BITS,
    METRIC_RUN_GROUP,
)

pytestmark = METRIC_RUN_GROUP

METRIC = "message_entropy"
# Half the messages are "aaaa" (0 bits) and half "abab" (1 bit), so the mean
# per-message entropy is exactly halfway between.
EXPECTED_BITS = (FLAT_ENTROPY_BITS + ALTERNATING_ENTROPY_BITS) / 2


async def test_it_computes_the_character_entropy_of_each_message(
    known_entropy_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checked against the definition, not against the implementation.

    `-Σ p(c)·log2 p(c)` for "aaaa" is 0: one symbol, nothing to be uncertain
    about. For "abab" it is exactly 1: two symbols at equal frequency. Those
    two values come from the formula rather than from this metric's code, so
    they would catch a change in how it counts characters or averages messages.
    """
    scored = await score_metrics(
        run=known_entropy_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(EXPECTED_BITS)
    assert scored.judge.calls == []


async def test_a_single_symbol_message_carries_no_information(
    known_entropy_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The zero end of the scale has to be reachable.

    Maximum compression is what an emergent protocol trends toward, so a metric
    that could not report 0 would flatten exactly the signal it exists for.
    The run's minimum per-round value is the round containing "aaaa".
    """
    scored = await score_metrics(
        run=known_entropy_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.per_round
    assert min(o.value for o in measurement.per_round) >= FLAT_ENTROPY_BITS
    assert max(o.value for o in measurement.per_round) <= ALTERNATING_ENTROPY_BITS
