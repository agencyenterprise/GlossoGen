"""When a derived run's own simulation began, read from its manifest.

A replace-agent, fork-at-round or cross-run run starts from a clone of its
source's log. Every cloned event predates the manifest, which is written before
the derived simulation launches, so an event logged before the manifest's
``replaced_at`` belongs to the source and one logged at or after it belongs to
the derived run.
"""

from datetime import UTC, datetime
from pathlib import Path

from glossogen.run_storage.cross_run_replace_manifest import read_cross_run_replace_manifest
from glossogen.run_storage.replace_manifest import read_replace_manifest


def derived_run_started_at(run_dir: Path) -> datetime | None:
    """The time ``run_dir``'s manifest was written, or ``None`` for a run that is not derived."""
    replace_manifest = read_replace_manifest(run_dir=run_dir)
    if replace_manifest is not None:
        return datetime.fromtimestamp(replace_manifest.replaced_at, tz=UTC)
    cross_run_manifest = read_cross_run_replace_manifest(run_dir=run_dir)
    if cross_run_manifest is not None:
        return datetime.fromtimestamp(cross_run_manifest.replaced_at, tz=UTC)
    return None
