"""Derives labels from evaluation results and merges them into a run's label set.

After evaluation completes, each metric's verdict is translated into a
descriptive label (e.g., ``eval:language_strangeness:pass``). These are
merged with existing labels and written to ``labels.json``.
"""

import logging
from pathlib import Path

import orjson

from schmidt.evaluation.evaluation_report import EvaluationReport

logger = logging.getLogger(__name__)

EVAL_LABEL_PREFIX = "eval:"


def _read_existing_labels(labels_path: Path) -> list[str]:
    """Read the current labels from disk, returning an empty list if missing."""
    if not labels_path.exists():
        return []
    try:
        raw: list[str] = orjson.loads(labels_path.read_bytes())
        return raw
    except Exception:
        logger.exception("Failed to read existing labels from %s", labels_path)
        return []


_VERDICT_LABEL_SUFFIX = {
    "pass": "identified",
    "partial": "partial",
    "fail": "fail",
}


def _derive_eval_labels(report: EvaluationReport) -> list[str]:
    """Produce one label per metric: ``eval:{evaluator_name}:{verdict_label}``.

    The ``pass`` verdict maps to ``identified`` to reflect that the evaluator
    detected the phenomenon it was looking for.
    """
    labels: list[str] = []
    for metric in report.metrics:
        suffix = _VERDICT_LABEL_SUFFIX[metric.verdict.value]
        label = f"{EVAL_LABEL_PREFIX}{metric.evaluator_name}:{suffix}"
        labels.append(label)
    return labels


def write_eval_labels(run_dir: Path, report: EvaluationReport) -> None:
    """Merge evaluation-derived labels into the run's ``labels.json``.

    Removes any previous ``eval:`` labels (from prior evaluation runs),
    then adds fresh labels derived from the current report.
    """
    labels_path = run_dir / "labels.json"
    existing = _read_existing_labels(labels_path=labels_path)

    without_eval = [label for label in existing if not label.startswith(EVAL_LABEL_PREFIX)]
    new_eval_labels = _derive_eval_labels(report=report)
    merged = sorted(set(without_eval + new_eval_labels))

    labels_path.write_bytes(orjson.dumps(merged))
    logger.info("Wrote eval labels to %s: %s", labels_path, new_eval_labels)
