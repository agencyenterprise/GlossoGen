"""`perplexity`: mean per-token surprisal of the channel under gpt2, in nats.

The most direct "is this still English" signal. A protocol drifting into codes
becomes unpredictable to a model trained on English and the number climbs.

Unlike the n-gram metrics, this one needs the `metrics-ml` extra on **every**
invocation: there is no cached model to hand-build, because the score comes
from a real forward pass. So the coverage here is in three layers.

  1. Without the extra, it raises. That is the path CI takes, and the contract
     that stops a broken environment reading as a run with nothing to measure.
  2. With a fake scorer injected, the metric's own arithmetic runs: per-message
     scores into per-round means into a run mean, and NaN dropped. That is the
     part this repo wrote and the part that can drift.
  3. With `--metrics-ml`, the real gpt2 path runs end to end. Off by default
     because it downloads a model and takes minutes; available so the code is
     not permanently untestable.
"""

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from glossogen.evaluation.metric_core.optional_ml_backend import is_perplexity_backend_available
from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "perplexity"
# What the fake scorer returns per message, in nats. Two messages per round in
# the shared run, so the round mean and the run mean are both their average.
FAKE_SURPRISALS = [2.0, 4.0]
EXPECTED_MEAN = sum(FAKE_SURPRISALS) / len(FAKE_SURPRISALS)


class FakeScorer:
    """Stands in for `minicons.IncrementalLMScorer` with scores we chose.

    `sequence_score` is the only method the metric calls. It hands in a
    reduction that minicons would apply to a tensor; a fake returns the numbers
    directly, so what is under test is the aggregation rather than the model.
    """

    def __init__(self, surprisals: list[float]) -> None:
        """Cycle through `surprisals`, one per text scored."""
        self._surprisals = surprisals
        self.scored_texts: list[str] = []

    def sequence_score(self, texts: list[str], reduction: Any) -> list[float]:
        """Return one score per text, recording what was asked for."""
        _ = reduction
        self.scored_texts.extend(texts)
        return [self._surprisals[i % len(self._surprisals)] for i in range(len(texts))]


def use_fake_scorer(*, scorer: FakeScorer, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the metric's own logic without torch, minicons or a download.

    Three seams: the backend guard, the device probe, and the scorer factory.
    All three are module-level names in the metric, so patching them leaves the
    scoring loop and every aggregation step running for real.
    """

    def allow_backend(metric_name: str) -> None:
        """Stand in for the guard that would reject a missing extra."""
        _ = metric_name

    def cpu_device() -> str:
        """Stand in for the torch device probe."""
        return "cpu"

    def scorer_factory() -> Callable[[str, str], FakeScorer]:
        """Stand in for the minicons scorer class the metric instantiates."""

        def build(model_name: str, device: str) -> FakeScorer:
            _ = model_name, device
            return scorer

        return build

    monkeypatch.setattr(
        "glossogen.evaluation.metrics.perplexity_metric.require_perplexity_backend",
        allow_backend,
    )
    monkeypatch.setattr(
        "glossogen.evaluation.metrics.perplexity_metric.resolve_torch_device",
        cpu_device,
    )
    monkeypatch.setattr(
        "glossogen.evaluation.metrics.perplexity_metric.load_incremental_lm_scorer",
        scorer_factory,
    )


@pytest.mark.skipif(
    is_perplexity_backend_available(),
    reason="the extra is installed, so the metric can run and will not raise",
)
async def test_it_raises_rather_than_skipping_when_the_extra_is_absent(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing dependency is an error, not a not-applicable result.

    Asking for perplexity and receiving no measurement would look exactly like
    a run with nothing to measure. The metric raises, the runner writes what
    did succeed and exits non-zero, so the gap is visible.
    """
    with pytest.raises(Exception) as raised:
        await score_metrics(
            run=metric_run,
            metric_names=[METRIC],
            judge_responses=[],
            options=NO_OPTIONS,
            report_path=tmp_path / "report.json",
            monkeypatch=monkeypatch,
        )
    assert METRIC in str(raised.value), "the error has to name the metric that failed"


async def test_it_averages_per_message_scores_into_rounds_and_the_run(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The aggregation, with the language model taken out of the picture.

    Scores of 2 and 4 nats per message mean a round mean of 3 and a run mean of
    3. Getting this wrong (summing instead of averaging, or weighting rounds by
    message count) is invisible against a real model, where no expected value
    is known.
    """
    scorer = FakeScorer(surprisals=FAKE_SURPRISALS)
    use_fake_scorer(scorer=scorer, monkeypatch=monkeypatch)

    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(EXPECTED_MEAN)
    assert measurement.per_round
    assert all(o.value == pytest.approx(EXPECTED_MEAN) for o in measurement.per_round)
    # The scorer was shown the run's own messages, not an empty list.
    assert scorer.scored_texts


async def test_a_message_the_scorer_cannot_score_is_dropped_not_propagated(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Minicons returns NaN for single-token inputs, and NaN spreads.

    One NaN reaching the mean makes the whole run's score NaN, which serializes
    to `null` and fails validation downstream, far from the message that caused
    it. The remaining scores still have to produce a real number.
    """
    scorer = FakeScorer(surprisals=[math.nan, 4.0])
    use_fake_scorer(scorer=scorer, monkeypatch=monkeypatch)

    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == measurement.score, "a NaN reached the run mean"
    assert measurement.score == pytest.approx(4.0)


@pytest.mark.metrics_ml
async def test_it_scores_real_text_under_gpt2(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real path: gpt2 loaded, a forward pass per message.

    Run with `--metrics-ml` after `uv sync --extra metrics-ml`. No expected
    value is asserted, because the point is that the whole path executes and
    returns a finite number in the right range; the exact surprisal belongs to
    gpt2 and would change with the model version.
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
    assert measurement.score == measurement.score, "gpt2 produced a NaN run mean"
    assert 0.0 < measurement.score < 50.0, "mean per-token surprisal in nats"
    assert measurement.per_round
