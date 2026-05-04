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
MWL_METRIC = "mean_word_length"
MML_METRIC = "mean_message_length"
MCR_METRIC = "mean_chars_per_round"
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


def mwl_score(evaluated: EvaluatedRun) -> float | None:
    """Mean characters per primary-channel word; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=MWL_METRIC)


def mml_score(evaluated: EvaluatedRun) -> float | None:
    """Mean words per primary-channel message; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=MML_METRIC)


def mcr_score(evaluated: EvaluatedRun) -> float | None:
    """Mean total chars per primary-channel round; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=MCR_METRIC)


def round_success_score(evaluated: EvaluatedRun) -> float | None:
    """Fraction of rounds the team stabilized; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=ROUND_SUCCESS_METRIC)


def round_success_after_resume_score(evaluated: EvaluatedRun) -> float | None:
    """Fraction of post-resume rounds stabilized; ``None`` if unscored."""
    return measurement_score(evaluated=evaluated, metric_name=ROUND_SUCCESS_AFTER_RESUME_METRIC)
