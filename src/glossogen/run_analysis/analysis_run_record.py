"""One run, reduced to what an analysis reads.

The export's record holds a run's summary and its whole evaluation report: every
measurement, every judge note, every one-line rollup. A query reads none of that. It
reads dimension cells, numbers, and a unit for the axis.

Keeping the full records around costs roughly eight times as much per run, mostly in
small Pydantic objects and judge prose. Projecting to this shape is what makes a
scenario-wide cohort something a server can hold while someone edits a chart over it.

The projection happens once per selection, immediately after the reports are read.
"""

import asyncio
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.keyed_observation import KeyedObservation
from glossogen.evaluation.metric_core.keyed_observation_reader import read_keyed_observations
from glossogen.run_analysis.measure_resolution import run_column_values
from glossogen.run_export.agent_identity_columns import agent_model_by_id
from glossogen.run_export.export_run_record import ExportRunRecord, load_export_run_record
from glossogen.run_export.metric_column_projection import measurements_by_name
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.server.runs.models import RunSummary

_RECORD_LOAD_CONCURRENCY = 16


class MetricValues(NamedTuple):
    """One metric's numbers for one run: the run-level score and the observations."""

    score: float | None
    per_round: dict[int, float]
    per_agent: dict[str, float]
    score_unit: str


class AnalysisAgent(NamedTuple):
    """One agent on a run's registered roster."""

    agent_id: str
    role_name: str
    model: str
    provider: str


class AnalysisRunRecord(NamedTuple):
    """One run as an analysis sees it.

    ``has_report`` separates a run that was never evaluated from one whose report
    carries no measurement for a metric. Both leave a blank cell; only the first is
    the run's fault.

    ``keyed`` holds what the metrics wrote beside the report, by metric name. It is
    empty unless the query asked for the keyed grain: filling it costs a filesystem
    read per metric per run, and no other grain reads it.
    """

    run_id: str
    has_report: bool
    dimensions: dict[str, str]
    agents: list[AnalysisAgent]
    run_columns: dict[str, float]
    metrics: dict[str, MetricValues]
    keyed: dict[str, list[KeyedObservation]]


def _metric_values(record: ExportRunRecord) -> dict[str, MetricValues]:
    """Reduce a run's report to numbers, keyed by metric name."""
    if record.report is None:
        return {}
    return {
        name: MetricValues(
            score=measurement.score,
            per_round={
                observation.round_number: observation.value for observation in measurement.per_round
            },
            per_agent={
                observation.agent_id: observation.value for observation in measurement.per_agent
            },
            score_unit=measurement.score_unit,
        )
        for name, measurement in measurements_by_name(
            measurements=record.report.measurements
        ).items()
    }


def project_run_record(
    record: ExportRunRecord,
    keyed: dict[str, list[KeyedObservation]],
) -> AnalysisRunRecord:
    """Reduce one export record to what a query reads."""
    return AnalysisRunRecord(
        run_id=record.summary.run_id,
        has_report=record.report is not None,
        dimensions=run_context_cells(record=record),
        agents=[
            AnalysisAgent(
                agent_id=agent.agent_id,
                role_name=agent.role_name,
                model=agent.model,
                provider=agent.provider,
            )
            for agent in agent_model_by_id(agent_models=record.summary.agent_models).values()
        ],
        run_columns=run_column_values(summary=record.summary),
        metrics=_metric_values(record=record),
        keyed=keyed,
    )


async def load_analysis_records(
    runs: list[RunSummary],
    read_sidecars: bool,
) -> list[AnalysisRunRecord]:
    """Load each run's report and reduce it as it arrives.

    Loading every full record first and projecting afterwards holds both at once. The
    projection is what the cache is sized for, at a fraction of the full record's
    cost, so a selection at the export's run ceiling would peak near a gigabyte before
    a single row was built. Projecting inside the fan-out means only the runs in
    flight are ever held whole.

    ``read_sidecars`` is what the keyed grain needs and what every other grain must
    not pay for: it opens one file per metric per run.
    """
    limiter = asyncio.Semaphore(_RECORD_LOAD_CONCURRENCY)

    async def load_one(summary: RunSummary) -> AnalysisRunRecord:
        """Read one run's report and sidecars, keeping only the projection."""
        async with limiter:
            record = await load_export_run_record(summary=summary)
            keyed: dict[str, list[KeyedObservation]] = {}
            if read_sidecars:
                keyed = await read_keyed_observations(run_dir=Path(summary.run_dir))
            return project_run_record(record=record, keyed=keyed)

    return list(await asyncio.gather(*(load_one(summary=summary) for summary in runs)))
