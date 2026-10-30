"""Generate the static demo-run snapshot consumed by the public landing page.

The public ``/demo`` walkthrough renders a real, frozen simulation run without
authentication. This script serializes one run directory into two static assets
under the frontend's ``public/`` tree:

- ``run.json`` — the exact ``RunDetailResponse`` the run viewer consumes, produced
  by the same ``load_run_detail`` the authenticated REST endpoint uses.
- ``run.zip`` — the downloadable archive produced by ``write_single_run_zip``,
  identical to the run-list "Export bundle" button.

Both underlying functions are pure (no auth, DB, or request), so the snapshot is
generated fully offline. Re-run this script to refresh the demo run.

Usage:
    VIRTUAL_ENV= uv run --no-sync python -m scripts.generate_demo_snapshot \\
        --run-dir runs/veyru/1780600361 \\
        --out-dir frontend/public/demo
"""

import argparse
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from glossogen.run_export.runs_zip_archive import write_single_run_zip
from glossogen.run_file_paths import event_log_path
from glossogen.server.runs.detail_reader import load_run_detail
from glossogen.server.runs.models import RunDetailResponse

logger = logging.getLogger(__name__)


def write_run_json(detail: RunDetailResponse, path: Path) -> None:
    """Serialize the run detail the viewer consumes, formatted as it is committed."""
    path.write_text(json.dumps(obj=jsonable_encoder(detail), indent=2, ensure_ascii=False))


async def write_run_zip(run_dir: Path, run_dir_name: str, scenario_name: str, path: Path) -> None:
    """Write the archive the run list's Export bundle button produces for one run.

    ``include_atif`` is on because a single run's zip download always carries
    each agent's ATIF trajectory, and this asset is that download.

    The write goes to a worker thread, which is how the export endpoint calls
    it. The ATIF part loads its context with ``asyncio.run``, so calling it from
    a thread that already has a loop running raises instead of writing.
    """
    with path.open("wb") as handle:
        await asyncio.to_thread(
            write_single_run_zip,
            run_dir=run_dir,
            run_dir_name=run_dir_name,
            scenario_name=scenario_name,
            include_logs=False,
            include_atif=True,
            destination=handle,
        )


async def write_demo_snapshot(run_dir: Path, out_dir: Path) -> None:
    """Serialize ``run_dir`` into ``run.json`` + ``run.zip`` under ``out_dir``.

    Both are built in a staging directory and moved into place only once both
    exist. The two files are one snapshot and have to describe the same run, so
    a failure partway through leaves what was already there rather than a fresh
    ``run.json`` beside a truncated ``run.zip``.
    """
    scenario_name = run_dir.parent.name
    log_path = event_log_path(run_dir=run_dir, scenario_name=scenario_name)
    if not log_path.is_file():
        raise FileNotFoundError(f"No event log at {log_path}")

    detail = await load_run_detail(log_path=log_path, children=[])
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=out_dir) as staging:
        staged_json = Path(staging) / "run.json"
        staged_zip = Path(staging) / "run.zip"
        write_run_json(detail=detail, path=staged_json)
        await write_run_zip(
            run_dir=run_dir,
            run_dir_name=run_dir.name,
            scenario_name=scenario_name,
            path=staged_zip,
        )
        run_json_path = out_dir / "run.json"
        run_zip_path = out_dir / "run.zip"
        staged_json.replace(run_json_path)
        staged_zip.replace(run_zip_path)

    logger.info(
        "Wrote %s (%d messages, %d tool calls, %d rounds)",
        run_json_path,
        len(detail.messages),
        len(detail.tool_use),
        len(detail.round_results),
    )
    logger.info("Wrote %s (%d bytes)", run_zip_path, run_zip_path.stat().st_size)


def main() -> None:
    """Parse CLI arguments and generate the demo snapshot."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory, e.g. runs/veyru/1780600361",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for run.json + run.zip, e.g. frontend/public/demo",
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            write_demo_snapshot(
                run_dir=Path(args.run_dir).resolve(),
                out_dir=Path(args.out_dir).resolve(),
            )
        )
    except Exception:
        logger.exception("Failed to generate demo snapshot")
        raise


if __name__ == "__main__":
    main()
