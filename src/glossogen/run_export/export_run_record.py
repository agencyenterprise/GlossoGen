"""A run paired with its evaluation report. Every frame reads from this.

Loading the reports once up front is what lets the export preview promise exactly
what the export will produce: the columns offered and the columns built come off
the same records.

`report` is `None` for a run that was never evaluated. That is common and not an
error, so the loader tolerates it and the preview counts it.

Reports are read with the tolerant loader, because a bulk read hits reports
written before evaluation cost was tracked and one of those must not fail the
whole export.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.reports.evaluation_report import EvaluationReport, load_report_tolerant
from glossogen.server.runs.models import RunSummary

logger = logging.getLogger(__name__)

_REPORT_LOAD_CONCURRENCY = 16


class ExportRunRecord(NamedTuple):
    """One run's summary and its evaluation report, if it has one."""

    summary: RunSummary
    report: EvaluationReport | None


def report_path_for(summary: RunSummary) -> Path:
    """Return where the run's evaluation report lives on disk."""
    return Path(summary.run_dir) / f"{summary.scenario_name}_report.json"


async def load_export_run_record(summary: RunSummary) -> ExportRunRecord:
    """Load one run's report, treating an unreadable one as absent.

    Public because a caller that reduces each run as it arrives needs them one at a
    time: holding every full record to project them afterwards peaks at several times
    what the projections cost.
    """
    try:
        report = await load_report_tolerant(report_path=report_path_for(summary=summary))
    except Exception:
        logger.exception(
            "Could not read the evaluation report for %s; exporting it without scores",
            summary.run_id,
        )
        return ExportRunRecord(summary=summary, report=None)
    return ExportRunRecord(summary=summary, report=report)


async def _load_one(summary: RunSummary, limiter: asyncio.Semaphore) -> ExportRunRecord:
    """Load one run's report under the shared concurrency limit."""
    async with limiter:
        return await load_export_run_record(summary=summary)


async def load_export_run_records(runs: list[RunSummary]) -> list[ExportRunRecord]:
    """Pair each run with its evaluation report, preserving the given order."""
    limiter = asyncio.Semaphore(_REPORT_LOAD_CONCURRENCY)
    return list(
        await asyncio.gather(*(_load_one(summary=summary, limiter=limiter) for summary in runs))
    )
