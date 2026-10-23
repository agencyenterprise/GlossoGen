"""Reading a run's per-metric scores out of its evaluation report.

Every completed run's summary carries these scores, and some listings build a
summary for every run in a group (MCP ``list_runs``, the exports, the status
filter). Over 4,738 local runs, reading every report took such a listing from
1.4s to 2.0s. The scores are therefore held per report, keyed on its modification
time and size, so a run whose report has not changed costs one ``stat`` and a
repeat listing takes 1.6s. ``write_report`` replaces a report through
``os.replace``, so a rewritten report presents a new key unless the new file has
the same size and the same modification time as the old one.
"""

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, ValidationError

from glossogen.server.runs.models import EvaluationScore

logger = logging.getLogger(__name__)

# A group with more evaluated runs than this re-reads every report on each
# listing that covers all of them, since the least recently read entries are
# evicted as the listing proceeds.
MAX_CACHED_REPORTS = 10_000


class _ReportScores(BaseModel):
    """The part of an evaluation report the scores come from; every other field is skipped."""

    measurements: list[EvaluationScore]


class EvaluationReportScores(NamedTuple):
    """What reading a run's report yielded.

    ``has_report`` is whether the report file exists. ``scores`` holds the
    report's measurements in report order; it is empty when there is no report
    and None when the report exists but could not be read or parsed.
    """

    has_report: bool
    scores: list[EvaluationScore] | None


class _CachedScores(NamedTuple):
    """One report's scores and the modification time and size of the file they came from."""

    modified_ns: int
    size: int
    scores: tuple[EvaluationScore, ...] | None


_CACHE: OrderedDict[Path, _CachedScores] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def read_evaluation_scores(report_path: Path) -> EvaluationReportScores:
    """Read the report's scores through the cache.

    A report that cannot be read or parsed yields ``scores=None`` and one logged
    exception per version of the file while that version stays cached, so one
    bad report costs that run its scores rather than failing the listing. A
    ``stat`` that fails for a reason other than the file being absent is logged
    and reported as no report. Called from worker threads.
    """
    try:
        stat = report_path.stat()
    except FileNotFoundError:
        return _no_report()
    except OSError:
        logger.exception("Failed to stat evaluation report %s", report_path)
        return _no_report()
    with _CACHE_LOCK:
        cached = _CACHE.get(report_path)
        if (
            cached is not None
            and cached.modified_ns == stat.st_mtime_ns
            and cached.size == stat.st_size
        ):
            _CACHE.move_to_end(report_path)
            return _as_result(scores=cached.scores)
    scores = _parse_scores(report_path=report_path)
    with _CACHE_LOCK:
        _CACHE[report_path] = _CachedScores(
            modified_ns=stat.st_mtime_ns, size=stat.st_size, scores=scores
        )
        _CACHE.move_to_end(report_path)
        while len(_CACHE) > MAX_CACHED_REPORTS:
            _CACHE.popitem(last=False)
    return _as_result(scores=scores)


def _no_report() -> EvaluationReportScores:
    """The result for a run without a report, with a fresh list the caller may keep."""
    return EvaluationReportScores(has_report=False, scores=[])


def _as_result(scores: tuple[EvaluationScore, ...] | None) -> EvaluationReportScores:
    """The result for a report that exists, with a fresh list the caller may keep."""
    if scores is None:
        return EvaluationReportScores(has_report=True, scores=None)
    return EvaluationReportScores(has_report=True, scores=list(scores))


def _parse_scores(report_path: Path) -> tuple[EvaluationScore, ...] | None:
    """Read the report's scores, or None when the file cannot be read or does not parse."""
    try:
        report = _ReportScores.model_validate_json(report_path.read_bytes())
    except OSError, ValidationError:
        logger.exception("Failed to read evaluation scores from %s", report_path)
        return None
    return tuple(report.measurements)
