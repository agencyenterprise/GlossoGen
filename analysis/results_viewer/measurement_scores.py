"""Shared per-measurement score extractors used across streamlit tabs.

Each helper takes an ``EvaluatedRun`` and returns the headline ``score`` for
a single metric, or ``None`` if the run wasn't evaluated for that metric.
Lifted out of ``baseline_data`` so the verbosity tab can reuse them without
importing baseline-specific filtering.
"""

from pathlib import Path

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun

PERPLEXITY_METRIC = "perplexity"
ENGLISH_NGRAM_SURPRISAL_METRIC = "english_ngram_surprisal"
MESSAGE_ENTROPY_METRIC = "message_entropy"
GZIP_COMPRESSION_RATIO_METRIC = "gzip_compression_ratio"
MCR_METRIC = "mean_chars_per_round"
MCM_METRIC = "mean_chars_per_message"
LANGUAGE_REPETITION_METRIC = "language_repetition"
ROUND_SUCCESS_METRIC = "round_success"
ROUND_SUCCESS_AFTER_RESUME_METRIC = "round_success_after_resume"


def read_labels(run_dir: Path) -> list[str]:
    """Return the labels stored in the run directory's ``labels.json``, or an empty list."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    raw = orjson.loads(labels_path.read_bytes())
    if not isinstance(raw, list):
        return []
    return [label for label in raw if isinstance(label, str)]


def measurement_score(evaluated: EvaluatedRun, metric_name: str) -> float | None:
    """Return the ``score`` for the named metric on this run, or ``None`` if missing."""
    for measurement in evaluated.report.measurements:
        if measurement.metric_name == metric_name:
            return float(measurement.score)
    return None


def perplexity_score(evaluated: EvaluatedRun) -> float | None:
    """Mean per-token surprisal in nats under gpt2; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=PERPLEXITY_METRIC)


def english_ngram_surprisal_score(evaluated: EvaluatedRun) -> float | None:
    """Mean per-char surprisal in nats under the English char trigram; ``None`` if unscored.

    Higher means less English-like (the inverse intuition of ``perplexity``).
    """
    return measurement_score(evaluated=evaluated, metric_name=ENGLISH_NGRAM_SURPRISAL_METRIC)


def message_entropy_score(evaluated: EvaluatedRun) -> float | None:
    """Mean within-message character Shannon entropy in bits/char; ``None`` if unscored.

    Lower means more repetitive/compressible (a model-free intrinsic measure).
    """
    return measurement_score(evaluated=evaluated, metric_name=MESSAGE_ENTROPY_METRIC)


def gzip_compression_ratio_score(evaluated: EvaluatedRun) -> float | None:
    """Mean per-message gzip compression ratio (compressed/original); ``None`` if unscored.

    Lower means more compressible/repetitive (short messages are overhead-dominated).
    """
    return measurement_score(evaluated=evaluated, metric_name=GZIP_COMPRESSION_RATIO_METRIC)


def mcr_score(evaluated: EvaluatedRun) -> float | None:
    """Mean total chars per primary-channel round; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=MCR_METRIC)


def mcm_score(evaluated: EvaluatedRun) -> float | None:
    """Mean chars per primary-channel message; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=MCM_METRIC)


def language_repetition_score(evaluated: EvaluatedRun) -> float | None:
    """Mean redundancy factor (encodings per information unit) on the primary channel.

    ``None`` if unscored.
    """
    return measurement_score(evaluated=evaluated, metric_name=LANGUAGE_REPETITION_METRIC)


def round_success_score(evaluated: EvaluatedRun) -> float | None:
    """Fraction of rounds the team stabilized; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=ROUND_SUCCESS_METRIC)


def round_success_after_resume_score(evaluated: EvaluatedRun) -> float | None:
    """Fraction of post-resume rounds stabilized; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=ROUND_SUCCESS_AFTER_RESUME_METRIC)
