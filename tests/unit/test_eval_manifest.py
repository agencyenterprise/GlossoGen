"""When a run counts as being evaluated, judged from its ``eval_in_progress.json``.

The web server writes the manifest with the PID of the ``glossogen evaluate``
process it launched, and that process deletes it when it ends. These tests use
real child processes, because whether a PID reads as alive is the thing under
test.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

from glossogen.cli.evaluate_command import handle_evaluate
from glossogen.run_storage.eval_manifest import (
    EVAL_MANIFEST_FILENAME,
    read_eval_manifest,
    write_eval_manifest,
)
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.scenario_loader import get_scenario_class

SCENARIO = "veyru"


@pytest.mark.skipif(not hasattr(os, "waitid"), reason="needs os.waitid to wait without reaping")
def test_an_evaluation_that_exited_reads_as_finished_before_anyone_reaps_it(
    tmp_path: Path,
) -> None:
    """The server never waits on what it launches, so an exited evaluation stays a zombie."""
    child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(1)"])
    # Blocks until the child exits, and leaves it unreaped.
    os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
    write_eval_manifest(run_dir=tmp_path, pid=child.pid)

    assert read_eval_manifest(run_dir=tmp_path) is None


def test_an_evaluation_still_running_reads_as_running(tmp_path: Path) -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    try:
        write_eval_manifest(run_dir=tmp_path, pid=child.pid)

        manifest = read_eval_manifest(run_dir=tmp_path)
    finally:
        assert child.stdin is not None
        child.stdin.close()
        child.wait()

    assert manifest is not None
    assert manifest.pid == child.pid


async def test_an_evaluation_that_fails_while_loading_the_run_removes_the_servers_manifest(
    tmp_path: Path,
) -> None:
    """Otherwise the run reads as being evaluated, and every retry is refused, for as long
    as its PID stays in use."""
    run_dir = tmp_path / SCENARIO / "1770000100"
    run_dir.mkdir(parents=True)
    event_log_path(run_dir=run_dir, scenario_name=SCENARIO).write_bytes(b"{not an event\n")
    write_eval_manifest(run_dir=run_dir, pid=os.getpid())
    args = argparse.Namespace(
        scenario_name=SCENARIO,
        run_dir=str(run_dir),
        metrics="mean_chars_per_message",
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        inference_provider=None,
        knobs=None,
        judge_settings=None,
        probe_round=None,
        probe_replicas=None,
        ontology_path=None,
    )

    with pytest.raises(ValueError):
        await handle_evaluate(args=args, scenario_cls=get_scenario_class(name=SCENARIO))

    assert not (run_dir / EVAL_MANIFEST_FILENAME).exists()
