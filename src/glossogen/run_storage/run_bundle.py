"""Packing a run directory into a tar.gz bundle that another glossogen server can import.

The bundle holds the run's directory, event log included, minus its debug and stdout
logs, its live-state files and its summary cache (see
:mod:`glossogen.run_storage.archive_member_filter`). A ``bundle_manifest.json`` names
the run and the timestamp its directory had where it was exported. The
server's bundle export endpoint and ``glossogen push-to-prod`` both build it here;
the server's import endpoint reads it back.
"""

import io
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import orjson
from pydantic import BaseModel

from glossogen.run_storage.archive_member_filter import should_include_in_archive

BUNDLE_MANIFEST_FILENAME = "bundle_manifest.json"


class BundleManifest(BaseModel):
    """Metadata embedded in an exported run bundle tar.gz."""

    run_id: str
    scenario_name: str
    exported_at: datetime
    original_timestamp: int


def build_bundle_bytes(
    run_dir: Path,
    run_id: str,
    scenario_name: str,
    original_timestamp: int,
) -> bytes:
    """Build a tar.gz archive of the run directory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for entry_path in sorted(run_dir.rglob("*")):
            if not should_include_in_archive(
                path=entry_path,
                run_dir=run_dir,
                include_logs=False,
            ):
                continue
            arcname = str(entry_path.relative_to(run_dir))
            tar.add(name=str(entry_path), arcname=arcname, recursive=False)

        manifest = BundleManifest(
            run_id=run_id,
            scenario_name=scenario_name,
            exported_at=datetime.now(tz=UTC),
            original_timestamp=original_timestamp,
        )
        manifest_bytes = orjson.dumps(manifest.model_dump(mode="json"), option=orjson.OPT_INDENT_2)
        info = tarfile.TarInfo(name=BUNDLE_MANIFEST_FILENAME)
        info.size = len(manifest_bytes)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(manifest_bytes))

    return buffer.getvalue()
