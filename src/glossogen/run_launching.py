"""Launching a prepared fork's simulation subprocess, detached.

The fork flows (replace-agent, cross-run replace-agent, fork-at-round) prepare a
new run directory on disk and then spawn ``glossogen run --resume`` over it.
Preparation and launching are separate so tests can exercise everything up to
the manifest write without spawning a subprocess that would call real models.
"""

import subprocess
from pathlib import Path
from typing import NamedTuple


class PreparedForkRun(NamedTuple):
    """A fork prepared on disk, ready to launch.

    ``launch_cmd`` is the full argv of the resumed subprocess and
    ``stdout_log_path`` is where its combined stdout and stderr land.
    """

    new_run_id: str
    new_run_dir: Path
    launch_cmd: tuple[str, ...]
    stdout_log_path: Path


def launch_prepared_run(prepared: PreparedForkRun) -> None:
    """Spawn the prepared run in the background, detached from this process."""
    with open(prepared.stdout_log_path, "w", encoding="utf-8") as log_file:
        subprocess.Popen(
            list(prepared.launch_cmd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
