"""The shipped scenario scripts that read runs load a scenario catalog first.

A run is parsed with the events its scenario declares, which the current catalog
answers, and a process outside the CLI has none until it loads one. Each script
runs in a fresh interpreter here, as a user runs it, so nothing the test suite
loaded hides a missing load.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import orjson

from glossogen.scenario_contract.scenario_sources import SCENARIOS_ENV_VAR

FIXED_TIME = "2026-01-01T00:00:00+00:00"


def write_run(runs_dir: Path, scenario_name: str) -> Path:
    """Write a run holding only its ``simulation_started`` line, and return its directory."""
    run_dir = runs_dir / scenario_name / "1780000000"
    run_dir.mkdir(parents=True)
    start: dict[str, Any] = {
        "event_id": "start",
        "event_type": "simulation_started",
        "timestamp": FIXED_TIME,
        "run_id": f"{scenario_name}/1780000000",
        "scenario_name": scenario_name,
        "scenario_description": "d",
        "scenario_config": {},
        "channel_ids": ["link"],
        "provider": "anthropic",
    }
    (run_dir / f"{scenario_name}.jsonl").write_bytes(orjson.dumps(start) + b"\n")
    return run_dir


def run_python(arguments: list[str], working_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run the interpreter with ``arguments`` in ``working_dir``, built-in scenarios only."""
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=working_dir,
        env={**os.environ, SCENARIOS_ENV_VAR: ""},
        capture_output=True,
        text=True,
        check=False,
    )


def test_audit_recorded_boards_reads_a_run(tmp_path: Path) -> None:
    """The documented command reads the run's events and gets as far as its config.

    The run carries an empty scenario config, so the audit then refuses it, which
    shows the events were read.
    """
    run_dir = write_run(runs_dir=tmp_path / "runs", scenario_name="spot_the_intersection")

    finished = run_python(
        arguments=[
            "-m",
            "glossogen.scenarios.spot_the_intersection.scripts.audit_recorded_boards",
            str(run_dir),
        ],
        working_dir=tmp_path,
    )

    assert "ScenarioCatalogNotLoaded" not in finished.stderr, finished.stderr
    assert "team_characters" in finished.stderr, "the audit did not get as far as the config"


def test_inspect_replaced_agent_input_reads_a_run(tmp_path: Path) -> None:
    """The script reaches the events; with no registration in them it says so and exits."""
    run_dir = write_run(runs_dir=tmp_path / "runs", scenario_name="veyru")
    script = (
        "import asyncio, sys\n"
        "from types import SimpleNamespace\n"
        "from glossogen.scenarios.veyru.scripts import inspect_replaced_agent_input as script\n"
        "script.read_replace_manifest_info = "
        "lambda run_dir: SimpleNamespace(replaced_agent_id='agent_a')\n"
        f"sys.argv = ['inspect', {str(run_dir)!r}]\n"
        "asyncio.run(script.main())\n"
    )

    finished = run_python(arguments=["-c", script], working_dir=tmp_path)

    assert "ScenarioCatalogNotLoaded" not in finished.stderr, finished.stderr
    assert "No AgentRegistered event for agent_a" in finished.stderr
