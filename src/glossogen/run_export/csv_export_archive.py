"""Assembling the requested frames, and delivering them as a zip or a directory.

A multi-frame export is a zip carrying a `columns.csv` legend alongside the
tables. The legend records each column's family and how many runs filled it,
which is the recoverable half of a blank cell: a knob a scenario never declared
and a knob it declared as null both render empty, and only the legend says which
columns were sparse.

It covers every metric column the tables carry: the score, the `metric_rounds`
denominator, and with summaries on, the unit, summary and note text. The text
columns carry no coverage count, since they describe a measurement rather than
make one.

It also covers the structural columns of each table it wrote, not only the ones
a caller could pick. Those carry no coverage count, since they are emitted on
every row of their table by construction, but they do carry the units: nothing
else in the export says that `character_entropy_bits` is bits per character or
that `repetition_factor` counts encodings per information unit.

A single-frame export is the bare CSV, so a double-click opens it. It has no
legend, which is the tradeoff a caller accepts by asking for one table.
"""

import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import IO

from glossogen.run_export.agent_level_frame import AGENT_COLUMNS, build_agent_level_frame
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.csv_frame_writer import write_frame
from glossogen.run_export.export_column_catalog import build_export_preview
from glossogen.run_export.export_preview_models import ExportMetricColumn
from glossogen.run_export.export_request_models import CsvExportRequest, ExportFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.message_level_frame import (
    MESSAGE_COLUMN_UNITS,
    MESSAGE_COLUMNS,
    build_message_level_frame,
)
from glossogen.run_export.metric_column_projection import (
    METRIC_COLUMN_PREFIX,
    METRIC_NOTE_COLUMN_PREFIX,
    METRIC_ROUNDS_COLUMN_PREFIX,
    METRIC_SUMMARY_COLUMN_PREFIX,
    METRIC_UNIT_COLUMN_PREFIX,
)
from glossogen.run_export.round_context_frame import build_round_context_frame
from glossogen.run_export.round_level_frame import ROUND_NUMBER_COLUMN, build_round_level_frame
from glossogen.run_export.run_level_frame import build_run_level_frame

logger = logging.getLogger(__name__)


def build_export_frames(
    records: list[ExportRunRecord],
    request: CsvExportRequest,
) -> list[CsvFrame]:
    """Build the frames ``request`` asked for, in a stable order.

    A repeated column key would otherwise emit the column twice, which no reader
    expects and which the modal cannot produce but a scripted caller can.
    """
    columns = list(dict.fromkeys(request.columns))
    metrics = list(dict.fromkeys(request.metrics))
    frames: list[CsvFrame] = []
    wanted = set(request.frames)

    if ExportFrame.RUN_LEVEL in wanted:
        frames.append(
            build_run_level_frame(
                records=records,
                columns=columns,
                metrics=metrics,
                include_metric_summaries=request.include_metric_summaries,
            )
        )
    if ExportFrame.ROUND_LEVEL in wanted:
        frames.append(
            build_round_level_frame(
                records=records,
                columns=columns,
                metrics=metrics,
                repeat_run_columns=request.repeat_run_columns,
                include_metric_summaries=request.include_metric_summaries,
            )
        )
    if ExportFrame.AGENT_LEVEL in wanted:
        frames.append(
            build_agent_level_frame(
                records=records,
                columns=columns,
                metrics=metrics,
                repeat_run_columns=request.repeat_run_columns,
                include_metric_summaries=request.include_metric_summaries,
            )
        )
    if ExportFrame.MESSAGE_LEVEL in wanted:
        frames.append(
            build_message_level_frame(
                records=records,
                columns=columns,
                repeat_run_columns=request.repeat_run_columns,
            )
        )
    if ExportFrame.ROUND_CONTEXT in wanted:
        frames.append(
            build_round_context_frame(
                records=records,
                columns=columns,
                repeat_run_columns=request.repeat_run_columns,
            )
        )
    return frames


# Which structural columns each table adds, in the order that table emits them.
_STRUCTURAL_COLUMNS: dict[ExportFrame, tuple[str, ...]] = {
    ExportFrame.ROUND_LEVEL: (ROUND_NUMBER_COLUMN,),
    ExportFrame.AGENT_LEVEL: AGENT_COLUMNS,
    ExportFrame.MESSAGE_LEVEL: MESSAGE_COLUMNS,
    ExportFrame.ROUND_CONTEXT: (ROUND_NUMBER_COLUMN,),
}


def _structural_rows(request: CsvExportRequest) -> list[list[str]]:
    """Describe the columns each requested table emits on every one of its rows.

    ``runs_with_value`` is left empty rather than set to the run count: these are
    not filled per run, so a coverage number would be answering a question nobody
    asked of them.
    """
    rows: list[list[str]] = []
    seen: set[str] = set()
    for frame in request.frames:
        for column in _STRUCTURAL_COLUMNS.get(frame, ()):
            if column in seen:
                continue
            seen.add(column)
            rows.append([column, frame.value, MESSAGE_COLUMN_UNITS.get(column, ""), "", ""])
    return rows


_METRIC_FRAMES = {ExportFrame.RUN_LEVEL, ExportFrame.ROUND_LEVEL, ExportFrame.AGENT_LEVEL}
_NOTE_FRAMES = {ExportFrame.ROUND_LEVEL, ExportFrame.AGENT_LEVEL}


def _metric_rows(
    name: str,
    metric: ExportMetricColumn | None,
    request: CsvExportRequest,
    run_count: int,
) -> list[list[str]]:
    """Describe the columns one requested metric adds to the tables ``request`` wrote.

    ``metric`` is ``None`` when no selected run reported the metric. The tables still
    carry its columns, all blank, so the legend names them with a coverage of ``0``.
    ``metric_rounds`` is filled exactly where the score is, so it shares the score's
    coverage. The unit, summary and note columns leave coverage empty.
    """
    score_unit = ""
    coverage = "0"
    if metric is not None:
        score_unit = metric.score_unit
        coverage = str(metric.runs_with_value)
    frames = set(request.frames)
    total = str(run_count)
    rows: list[list[str]] = []
    if frames & _METRIC_FRAMES:
        rows.append([f"{METRIC_COLUMN_PREFIX}{name}", "metric", score_unit, coverage, total])
    if ExportFrame.RUN_LEVEL in frames:
        rows.append([f"{METRIC_ROUNDS_COLUMN_PREFIX}{name}", "metric", "rounds", coverage, total])
    if not request.include_metric_summaries:
        return rows
    if ExportFrame.RUN_LEVEL in frames:
        rows.append([f"{METRIC_UNIT_COLUMN_PREFIX}{name}", "metric", "", "", ""])
        rows.append([f"{METRIC_SUMMARY_COLUMN_PREFIX}{name}", "metric", "", "", ""])
    if frames & _NOTE_FRAMES:
        rows.append([f"{METRIC_NOTE_COLUMN_PREFIX}{name}", "metric", "", "", ""])
    return rows


def build_legend_frame(records: list[ExportRunRecord], request: CsvExportRequest) -> CsvFrame:
    """Build the legend naming each column the export wrote, its family, and its coverage."""
    preview = build_export_preview(records=records, missing_run_ids=[], raw_bytes_estimate=None)
    requested_columns = set(request.columns)
    reported_metrics = {metric.metric_name: metric for metric in preview.metrics}

    rows: list[list[str]] = []
    for column in preview.columns:
        if not column.always_included and column.key not in requested_columns:
            continue
        rows.append(
            [column.key, column.group, "", str(column.runs_with_value), str(preview.run_count)]
        )
    for name in dict.fromkeys(request.metrics):
        rows.extend(
            _metric_rows(
                name=name,
                metric=reported_metrics.get(name),
                request=request,
                run_count=preview.run_count,
            )
        )

    rows.extend(_structural_rows(request=request))

    return CsvFrame(
        name="columns",
        header=["column", "group", "unit", "runs_with_value", "run_count"],
        rows=iter(rows),
    )


def write_frames_to_zip(
    frames: list[CsvFrame],
    legend: CsvFrame,
    destination: IO[bytes],
    check: Callable[[], None] | None,
) -> None:
    """Write every frame plus the legend into one zip.

    ``check`` is called periodically during the write and is expected to raise if the
    export has grown too large. ``None`` writes without a ceiling.
    """
    with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for frame in list(frames) + [legend]:
            with archive.open(f"{frame.name}.csv", mode="w") as entry:
                row_count, frame_bytes = write_frame(frame=frame, destination=entry, check=check)
            logger.info("Wrote %s.csv (%d rows, %d bytes)", frame.name, row_count, frame_bytes)


def write_single_frame(
    frame: CsvFrame,
    destination: IO[bytes],
    check: Callable[[], None] | None,
) -> None:
    """Write one frame as a bare CSV, with the same periodic check."""
    row_count, frame_bytes = write_frame(frame=frame, destination=destination, check=check)
    logger.info("Wrote %s.csv (%d rows, %d bytes)", frame.name, row_count, frame_bytes)


def write_frames_to_directory(
    frames: list[CsvFrame],
    legend: CsvFrame,
    out_dir: Path,
) -> list[Path]:
    """Write every frame plus the legend into ``out_dir``; return the written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for frame in list(frames) + [legend]:
        path = out_dir / f"{frame.name}.csv"
        with path.open("wb") as handle:
            row_count, _ = write_frame(frame=frame, destination=handle, check=None)
        logger.info("Wrote %s (%d rows)", path, row_count)
        written.append(path)
    return written
