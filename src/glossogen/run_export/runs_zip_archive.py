"""Writing run directories into a zip, one run or many.

Every member is streamed through :func:`shutil.copyfileobj` into an entry opened
for writing, never handed to `ZipFile.write`. `write` stats the file and
records that size in the member header, so a JSONL an in-progress simulation is
still appending to produces an entry whose declared size no longer matches its
contents. Copying into an open entry lets the size be whatever was read.

A multi-run archive nests each run under `{scenario_name}/{run_dir_name}/`,
because run directory names are unix timestamps and two scenarios can hold the
same one. A single-run archive keeps the bare `{run_dir_name}/` it has always
used, so it still drops into one scenario's runs directory.
"""

import csv
import io
import logging
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import IO, NamedTuple

from glossogen.run_export.archive_member_filter import should_include_in_archive
from glossogen.run_export.export_limits import check_raw_bytes
from glossogen.server.runs.models import RunSummary

logger = logging.getLogger(__name__)

_MANIFEST_MEMBER_NAME = "manifest.csv"

_ZIP_MIN_DATE_TIME: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)


class RunZipTally(NamedTuple):
    """How much of one run went into an archive."""

    file_count: int
    byte_count: int


class RunsZipTally(NamedTuple):
    """How much of a whole selection went into an archive."""

    run_count: int
    file_count: int
    byte_count: int


def zip_date_time(mtime: float) -> tuple[int, int, int, int, int, int]:
    """Return a zip-compatible ``date_time`` tuple, clamped to the 1980 epoch.

    The zip format cannot represent timestamps before 1980; run directories
    copied or extracted from older archives can carry such mtimes.
    """
    parts = time.localtime(mtime)
    if parts.tm_year < 1980:
        return _ZIP_MIN_DATE_TIME
    return (parts.tm_year, parts.tm_mon, parts.tm_mday, parts.tm_hour, parts.tm_min, parts.tm_sec)


def add_run_to_zip(
    archive: zipfile.ZipFile,
    run_dir: Path,
    arc_root: PurePosixPath,
    include_logs: bool,
) -> RunZipTally:
    """Add every included file under ``run_dir`` to ``archive`` beneath ``arc_root``."""
    file_count = 0
    byte_count = 0
    for entry_path in sorted(run_dir.rglob("*")):
        if not entry_path.is_file():
            continue
        if not should_include_in_archive(
            path=entry_path,
            run_dir=run_dir,
            include_logs=include_logs,
        ):
            continue
        stat_result = entry_path.stat()
        arcname = str(arc_root / entry_path.relative_to(run_dir))
        info = zipfile.ZipInfo(
            filename=arcname,
            date_time=zip_date_time(mtime=stat_result.st_mtime),
        )
        info.compress_type = zipfile.ZIP_DEFLATED
        with entry_path.open("rb") as source, archive.open(info, mode="w") as target:
            shutil.copyfileobj(source, target)
        file_count += 1
        byte_count += stat_result.st_size
    return RunZipTally(file_count=file_count, byte_count=byte_count)


def write_single_run_zip(
    run_dir: Path,
    run_dir_name: str,
    include_logs: bool,
    destination: IO[bytes],
) -> RunZipTally:
    """Write one run's zip, nesting its files under a ``{run_dir_name}/`` folder.

    Extracting the archive into a scenario's runs directory reproduces the
    original run directory.
    """
    with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        return add_run_to_zip(
            archive=archive,
            run_dir=run_dir,
            arc_root=PurePosixPath(run_dir_name),
            include_logs=include_logs,
        )


def _manifest_bytes(rows: list[tuple[str, str, str, str, str, int]]) -> bytes:
    """Render the archive's manifest rows as CSV."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["run_id", "scenario_name", "run_dir_name", "status", "timestamp", "bytes"])
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def write_runs_zip(
    runs: list[RunSummary],
    include_logs: bool,
    destination: IO[bytes],
) -> RunsZipTally:
    """Write many runs into one zip, each under ``{scenario_name}/{run_dir_name}/``.

    Adds a ``manifest.csv`` at the archive root naming what went in. Raises
    :class:`~glossogen.run_export.export_limits.ExportTooLargeError` if the run
    folders total more than the raw export ceiling.
    """
    manifest_rows: list[tuple[str, str, str, str, str, int]] = []
    total_files = 0
    total_bytes = 0

    with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for summary in runs:
            run_dir = Path(summary.run_dir)
            run_dir_name = run_dir.name
            tally = add_run_to_zip(
                archive=archive,
                run_dir=run_dir,
                arc_root=PurePosixPath(summary.scenario_name) / run_dir_name,
                include_logs=include_logs,
            )
            total_files += tally.file_count
            total_bytes += tally.byte_count
            check_raw_bytes(total_bytes=total_bytes)
            manifest_rows.append(
                (
                    summary.run_id,
                    summary.scenario_name,
                    run_dir_name,
                    summary.status.value,
                    summary.timestamp.isoformat(),
                    tally.byte_count,
                )
            )

        archive.writestr(_MANIFEST_MEMBER_NAME, _manifest_bytes(rows=manifest_rows))

    logger.info(
        "Wrote raw export: %d runs, %d files, %d bytes",
        len(runs),
        total_files,
        total_bytes,
    )
    return RunsZipTally(run_count=len(runs), file_count=total_files, byte_count=total_bytes)
