"""Describing a selection: which columns it can fill, and how full each would be.

Built from the same records the export reads, so what a client is offered and what
it can receive are the same set by construction.

Metric row counts are attached per metric, not totalled, because the
preview does not know which metrics a client will pick. Attaching them per metric
lets a client total the ones it checked without asking again.
"""

from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.models.event import RunStatus
from glossogen.run_export import export_limits
from glossogen.run_export.agent_identity_columns import (
    AGENT_MODEL_COLUMN_PREFIX,
    AGENT_PROVIDER_COLUMN_PREFIX,
    AGENT_ROLE_COLUMN_PREFIX,
)
from glossogen.run_export.archive_member_filter import should_include_in_archive
from glossogen.run_export.export_preview_models import (
    ExportMetricColumn,
    ExportValueColumn,
    MultiRunExportPreview,
)
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.knob_flattening import KNOB_COLUMN_PREFIX
from glossogen.run_export.label_value_columns import LABEL_COLUMN_PREFIX
from glossogen.run_export.lineage_columns import DERIVATION_TYPE_COLUMN, LINEAGE_COLUMN_PREFIX
from glossogen.run_export.metric_column_projection import measurements_by_name
from glossogen.run_export.run_context_columns import collect_context_keys
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

COLUMN_GROUP_IDENTITY = "identity"
COLUMN_GROUP_RUN_METADATA = "run_metadata"
COLUMN_GROUP_KNOB = "knob"
COLUMN_GROUP_LABEL = "label"
COLUMN_GROUP_AGENT = "agent_identity"
COLUMN_GROUP_LINEAGE = "lineage"

_AGENT_PREFIXES = (
    AGENT_MODEL_COLUMN_PREFIX,
    AGENT_PROVIDER_COLUMN_PREFIX,
    AGENT_ROLE_COLUMN_PREFIX,
)


def _group_of(key: str) -> str:
    """Return which column family ``key`` belongs to."""
    if key in IDENTITY_COLUMNS:
        return COLUMN_GROUP_IDENTITY
    if key.startswith(KNOB_COLUMN_PREFIX):
        return COLUMN_GROUP_KNOB
    if key.startswith(LABEL_COLUMN_PREFIX):
        return COLUMN_GROUP_LABEL
    if key.startswith(LINEAGE_COLUMN_PREFIX) or key == DERIVATION_TYPE_COLUMN:
        return COLUMN_GROUP_LINEAGE
    for prefix in _AGENT_PREFIXES:
        if key.startswith(prefix):
            return COLUMN_GROUP_AGENT
    return COLUMN_GROUP_RUN_METADATA


def humanize_column_key(key: str) -> str:
    """Render a column key as a short label, keeping the part that identifies it."""
    _, _, tail = key.rpartition(".")
    if tail == "":
        tail = key
    return tail.replace("_", " ").strip().capitalize()


def _measurement_index(record: ExportRunRecord) -> dict[str, Measurement]:
    """Return the record's measurements by name, empty when it has no report.

    Delegates to the same indexer the frames use, so a report carrying a metric
    name twice is described here by the measurement that actually gets exported.
    """
    if record.report is None:
        return {}
    return measurements_by_name(measurements=record.report.measurements)


def _metric_columns(records: list[ExportRunRecord]) -> list[ExportMetricColumn]:
    """Return one entry per metric name any selected run's report carries."""
    runs_with_value: dict[str, int] = {}
    round_rows: dict[str, int] = {}
    agent_rows: dict[str, int] = {}
    units: dict[str, str] = {}

    for record in records:
        for name, measurement in _measurement_index(record=record).items():
            runs_with_value[name] = runs_with_value.get(name, 0) + 1
            round_rows[name] = round_rows.get(name, 0) + len(measurement.per_round)
            agent_rows[name] = agent_rows.get(name, 0) + len(measurement.per_agent)
            if name not in units:
                units[name] = measurement.score_unit

    return [
        ExportMetricColumn(
            metric_name=name,
            label=humanize_column_key(key=name),
            score_unit=units[name],
            runs_with_value=runs_with_value[name],
            round_row_count=round_rows[name],
            agent_row_count=agent_rows[name],
        )
        for name in sorted(runs_with_value)
    ]


def _value_columns(records: list[ExportRunRecord]) -> list[ExportValueColumn]:
    """Return one entry per run-context column any selected run fills."""
    coverage = collect_context_keys(records=records)
    return [
        ExportValueColumn(
            key=key,
            label=humanize_column_key(key=key),
            group=_group_of(key=key),
            runs_with_value=coverage[key],
            always_included=key in IDENTITY_COLUMNS,
        )
        for key in sorted(coverage)
    ]


def estimate_raw_bytes(records: list[ExportRunRecord], include_logs: bool) -> int:
    """Return the on-disk size of the files a raw export of these runs would carry."""
    total = 0
    for record in records:
        run_dir = Path(record.summary.run_dir)
        for path in run_dir.rglob("*"):
            if not path.is_file():
                continue
            if not should_include_in_archive(
                path=path,
                run_dir=run_dir,
                include_logs=include_logs,
            ):
                continue
            total += path.stat().st_size
    return total


def build_export_preview(
    records: list[ExportRunRecord],
    missing_run_ids: list[str],
    raw_bytes_estimate: int | None,
) -> MultiRunExportPreview:
    """Describe what an export of ``records`` would produce."""
    return MultiRunExportPreview(
        run_count=len(records),
        run_ids=[record.summary.run_id for record in records],
        scenario_names=sorted({record.summary.scenario_name for record in records}),
        evaluated_run_count=sum(1 for record in records if record.report is not None),
        in_progress_run_count=sum(
            1 for record in records if record.summary.status == RunStatus.IN_PROGRESS
        ),
        runs_without_report=[record.summary.run_id for record in records if record.report is None],
        missing_run_ids=missing_run_ids,
        raw_bytes_estimate=raw_bytes_estimate,
        columns=_value_columns(records=records),
        metrics=_metric_columns(records=records),
        max_run_count=export_limits.MAX_EXPORT_RUN_COUNT,
        max_raw_bytes=export_limits.MAX_RAW_EXPORT_BYTES,
        max_csv_bytes=export_limits.MAX_CSV_EXPORT_BYTES,
    )


def oversized_export_preview(
    run_ids: list[str],
    scenario_names: list[str],
    missing_run_ids: list[str],
) -> MultiRunExportPreview:
    """Describe a selection that is over the run ceiling, without reading its reports.

    The offered columns come from the runs' reports, and a selection that cannot be
    exported has none to offer, so they are empty. The count and the ceiling are what
    a caller needs here: with both, it can explain the refusal in its own words
    instead of passing along an error string.
    """
    return MultiRunExportPreview(
        run_count=len(run_ids),
        run_ids=run_ids,
        scenario_names=scenario_names,
        evaluated_run_count=0,
        in_progress_run_count=0,
        runs_without_report=[],
        missing_run_ids=missing_run_ids,
        raw_bytes_estimate=None,
        columns=[],
        metrics=[],
        max_run_count=export_limits.MAX_EXPORT_RUN_COUNT,
        max_raw_bytes=export_limits.MAX_RAW_EXPORT_BYTES,
        max_csv_bytes=export_limits.MAX_CSV_EXPORT_BYTES,
    )
