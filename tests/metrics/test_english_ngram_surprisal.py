"""`english_ngram_surprisal`: how English-like the channel's text is.

Scores each primary-channel message by its mean per-character surprisal under a
character trigram model trained on English, in nats. A protocol drifting into
codes and abbreviations stops looking like English and the number climbs, which
is the emergence signal this metric contributes.

The model needs the optional `metrics-ml` extra only to *train* itself from
wikitext. Once a model is cached it loads from JSON with no ML dependency at
all, so a hand-built cache is what lets the scoring be tested here.
"""

import math
from pathlib import Path

import pytest

from glossogen.evaluation.metrics.english_ngram.english_ngram_model import EnglishTrigramModel
from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "english_ngram_surprisal"

# A model that has seen nothing. Add-1 smoothing then gives every character
# probability `(0 + 1) / (0 + 1 * V)`, so the surprisal of any text at all is
# exactly `ln(V)` nats. The value comes from the smoothing formula rather than
# from the metric's code, which is what makes it an oracle instead of a copy.
VOCAB = list("abcdefghij")
UNTRAINED_SURPRISAL_NATS = math.log(len(VOCAB))


def cache_model(
    *, model: EnglishTrigramModel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the loader at a hand-built model instead of a trained one.

    The loader reads its cache before it reaches for `datasets`, so redirecting
    the path is enough to run the metric with no ML dependency present.
    """
    cache_path = tmp_path / "trigram.json"
    cache_path.write_text(model.model_dump_json())
    monkeypatch.setattr(
        "glossogen.evaluation.metrics.english_ngram.english_ngram_model._CACHE_PATH",
        cache_path,
    )


async def test_an_untrained_model_scores_every_text_at_ln_vocab_size(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact value add-1 smoothing produces when no n-gram was ever seen.

    Every character falls back to the uniform smoothing floor, so the mean is
    `ln(10)` for a ten-symbol vocabulary regardless of what the agents said.
    A metric that mis-applied the smoothing, or reported bits instead of nats,
    would land somewhere else.
    """
    cache_model(
        model=EnglishTrigramModel(vocab=VOCAB, bigram={}, trigram={}),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    measurement = scored.measurement(metric_name=METRIC)
    assert measurement.score == pytest.approx(UNTRAINED_SURPRISAL_NATS)
    assert scored.judge.calls == []


async def test_text_the_model_has_seen_is_less_surprising(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Familiar n-grams have to lower the score, or the model is decorative.

    The run's messages are "alpha" and "beta". Training the model on exactly
    those character sequences drives their probabilities toward 1 and the
    surprisal toward 0. Without this a metric ignoring its own counts would
    still pass the test above, and every run would score the smoothing floor.
    """
    # Padded as the scorer does: "^^" + word + "$".
    trained = EnglishTrigramModel(
        vocab=VOCAB + list("lphbet^$"),
        bigram={ctx: 1000 for ctx in ("^^", "^a", "al", "lp", "ph", "ha", "^b", "be", "et", "ta")},
        trigram={
            gram: 1000
            for gram in (
                "^^a",
                "^al",
                "alp",
                "lph",
                "pha",
                "ha$",
                "^^b",
                "^be",
                "bet",
                "eta",
                "ta$",
            )
        },
    )
    cache_model(model=trained, tmp_path=tmp_path, monkeypatch=monkeypatch)
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / "report.json",
        monkeypatch=monkeypatch,
    )

    assert scored.measurement(metric_name=METRIC).score < UNTRAINED_SURPRISAL_NATS


async def test_it_raises_rather_than_skipping_when_the_model_cannot_be_built(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing dependency is an error, not a not-applicable result.

    On a cold cache the model needs `metrics-ml` to train. Asking for this
    metric and receiving no measurement would be indistinguishable from a run
    with nothing to measure, which is how a broken environment gets written up
    as a valid result. The runner wraps the failure and exits non-zero.

    Pinned from the environment CI actually has: no extra, and here no cache.
    """
    monkeypatch.setattr(
        "glossogen.evaluation.metrics.english_ngram.english_ngram_model._CACHE_PATH",
        tmp_path / "absent.json",
    )
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
