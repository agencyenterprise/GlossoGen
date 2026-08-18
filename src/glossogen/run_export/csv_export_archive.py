"""Assembling the requested frames, and delivering them as a zip or a directory.

A multi-frame export is a zip carrying a `columns.csv` legend alongside the
tables. The legend records each column's family and how many runs filled it,
which is the recoverable half of a blank cell: a knob a scenario never declared
and a knob it declared as null both render empty, and only the legend says which
columns were sparse.

A single-frame export is the bare CSV, so a double-click opens it. It has no
legend, which is the tradeoff a caller accepts by asking for one table.
"""

import logging
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import IO

from glossogen.run_export.agent_level_frame import build_agent_level_frame
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.csv_frame_writer import write_frame
from glossogen.run_export.export_column_catalog import build_export_preview
from glossogen.run_export.export_request_models import CsvExportRequest, ExportFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.round_level_frame import build_round_level_frame
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
            )
        )
    if ExportFrame.AGENT_LEVEL in wanted:
        frames.append(
            build_agent_level_frame(
                records=records,
                columns=columns,
                metrics=metrics,
                repeat_run_columns=request.repeat_run_columns,
            )
        )
    return frames


def build_legend_frame(records: list[ExportRunRecord], request: CsvExportRequest) -> CsvFrame:
    """Build the legend naming each requested column, its family, and its coverage."""
    preview = build_export_preview(records=records, missing_run_ids=[], raw_bytes_estimate=None)
    requested_columns = set(request.columns)
    requested_metrics = set(request.metrics)

    rows: list[list[str]] = []
    for column in preview.columns:
        if not column.always_included and column.key not in requested_columns:
            continue
        rows.append(
            [column.key, column.group, "", str(column.runs_with_value), str(preview.run_count)]
        )
    for metric in preview.metrics:
        if metric.metric_name not in requested_metrics:
            continue
        rows.append(
            [
                f"metric.{metric.metric_name}",
                "metric",
                metric.score_unit,
                str(metric.runs_with_value),
                str(preview.run_count),
            ]
        )

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
