"""`english_ngram_backoff_surprisal`: the same signal, smoothed by backoff.

Where the plain trigram falls back to a flat add-1 floor for anything it has
not seen, this one backs off through trigram to bigram to unigram, so an unseen
sequence made of familiar characters is treated as less surprising than one
made of unfamiliar ones. That difference is the reason both metrics exist, and
it only shows up on text the model was not trained on.

Like its sibling, the optional `metrics-ml` extra is needed only to *train* the
model. A cached model loads from JSON with no ML dependency, which is what lets
the scoring be tested here.
"""

from pathlib import Path

import pytest

from glossogen.evaluation.metrics.english_ngram.backoff_ngram_metric import (
    CASE_SENSITIVE as METRIC_CASE_SENSITIVE,
)
from glossogen.evaluation.metrics.english_ngram.backoff_ngram_metric import (
    KEEP_PUNCTUATION as METRIC_KEEP_PUNCTUATION,
)
from glossogen.evaluation.metrics.english_ngram.backoff_ngram_model import (
    BackoffTrigramModel,
    cache_path,
)
from tests.metrics.conftest import METRIC_RUN_GROUP
from tests.testbed.metric_harness import NO_OPTIONS, MetricRun, score_metrics

pytestmark = METRIC_RUN_GROUP

METRIC = "english_ngram_backoff_surprisal"

# The configuration the metric asks the loader for, which decides the cache
# filename. Imported rather than restated: guessing it wrong puts the fake cache
# at a name the loader never looks at, the load falls through to training, and
# the test fails claiming the extra is missing rather than saying the filename
# drifted.
CASE_SENSITIVE = METRIC_CASE_SENSITIVE
KEEP_PUNCTUATION = METRIC_KEEP_PUNCTUATION

VOCAB = list("abcdefghijlpht^$")


def unseen_sequences() -> BackoffTrigramModel:
    """Knows the characters but has never seen them in these orders.

    Unigram counts only, so every trigram and bigram lookup misses and the
    scorer backs all the way off. A model with `total=0` would instead be
    degenerate, and the metric would fail rather than score high.
    """
    return BackoffTrigramModel(
        vocab=VOCAB,
        trigram={},
        bigram={},
        unigram={char: 1 for char in VOCAB},
        total=len(VOCAB),
        case_sensitive=CASE_SENSITIVE,
        keep_punctuation=KEEP_PUNCTUATION,
    )


def trained_on_the_runs_words() -> BackoffTrigramModel:
    """A model that has seen the exact character sequences the run sent."""
    grams = ("^^a", "^al", "alp", "lph", "pha", "ha$", "^^b", "^be", "bet", "eta", "ta$")
    contexts = ("^^", "^a", "al", "lp", "ph", "ha", "^b", "be", "et", "ta")
    return BackoffTrigramModel(
        vocab=VOCAB,
        trigram={gram: 1000 for gram in grams},
        bigram={ctx: 1000 for ctx in contexts},
        unigram={char: 1000 for char in VOCAB},
        total=1000 * len(VOCAB),
        case_sensitive=CASE_SENSITIVE,
        keep_punctuation=KEEP_PUNCTUATION,
    )


def cache_model(
    *, model: BackoffTrigramModel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the loader at a hand-built model instead of a trained one.

    The path is configuration-keyed, so it is derived through the loader's own
    helper: a hardcoded filename would drift the moment the metric changed its
    case or punctuation setting, and the test would silently fall through to
    training instead of failing.
    """
    monkeypatch.setattr(
        "glossogen.evaluation.metrics.english_ngram.backoff_ngram_model._CACHE_DIR",
        tmp_path,
    )
    path = cache_path(case_sensitive=CASE_SENSITIVE, keep_punctuation=KEEP_PUNCTUATION)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json())


async def surprisal_under(
    *,
    model: BackoffTrigramModel,
    metric_run: MetricRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> float:
    """Score the shared run under one model and return the mean surprisal."""
    cache_model(model=model, tmp_path=tmp_path / label, monkeypatch=monkeypatch)
    scored = await score_metrics(
        run=metric_run,
        metric_names=[METRIC],
        judge_responses=[],
        options=NO_OPTIONS,
        report_path=tmp_path / f"{label}.json",
        monkeypatch=monkeypatch,
    )
    assert scored.judge.calls == []
    return scored.measurement(metric_name=METRIC).score


async def test_familiar_text_is_less_surprising_than_unseen_text(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The counts have to drive the score, or the model is decorative.

    The run's messages are "alpha" and "beta". Scored under a model trained on
    exactly those sequences they are cheap; under one that knows the same
    characters but never in that order, the scorer backs off and they cost
    more. Both models share a vocabulary, so the only thing separating them is
    the sequence counts, and a metric ignoring its own model returns the same
    number twice.
    """
    seen = await surprisal_under(
        model=trained_on_the_runs_words(),
        metric_run=metric_run,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        label="trained",
    )
    unseen = await surprisal_under(
        model=unseen_sequences(),
        metric_run=metric_run,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        label="unseen",
    )

    assert seen < unseen, (
        f"text the model was trained on scored {seen:.3f} nats and unseen text "
        f"scored {unseen:.3f}; familiar text has to be the cheaper of the two"
    )


async def test_it_reports_a_surprisal_per_round(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every round with messages contributes one observation, and none is nan.

    `mean_char_surprisal` returns nan for text with nothing scorable, and a nan
    propagates silently through the run mean into the report, where it is much
    harder to attribute.
    """
    cache_model(model=trained_on_the_runs_words(), tmp_path=tmp_path, monkeypatch=monkeypatch)
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
    assert measurement.score == measurement.score, "run mean is nan"
    for observation in measurement.per_round:
        assert observation.value == observation.value, f"round {observation.round_number} is nan"


async def test_it_raises_rather_than_skipping_when_the_model_cannot_be_built(
    metric_run: MetricRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing dependency is an error, not a not-applicable result.

    On a cold cache the model needs `metrics-ml` to train. Returning no
    measurement would be indistinguishable from a run with nothing to measure,
    so the metric raises and the runner exits non-zero.

    Pinned from the environment CI actually has: no extra, and here no cache.
    """
    monkeypatch.setattr(
        "glossogen.evaluation.metrics.english_ngram.backoff_ngram_model._CACHE_DIR",
        tmp_path / "empty",
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
