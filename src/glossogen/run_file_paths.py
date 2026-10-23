"""Paths of the files inside a run directory whose names carry the scenario name.

A run directory holds ``{scenario_name}.jsonl`` and its siblings (see "Run Storage"
in Architecture.md). Each function here takes the run directory and
the scenario name and returns one of those paths, so the names are spelled in one
place. Files with fixed names, such as the manifests and the metric sidecars, are
named by their own modules.
"""

from pathlib import Path


def event_log_path(run_dir: Path, scenario_name: str) -> Path:
    """Return the run's JSONL event log, ``{scenario_name}.jsonl``."""
    return run_dir / f"{scenario_name}.jsonl"


def debug_log_path(run_dir: Path, scenario_name: str) -> Path:
    """Return the run's JSON-lines debug log, ``{scenario_name}_debug.jsonl``."""
    return run_dir / f"{scenario_name}_debug.jsonl"


def evaluation_report_path(run_dir: Path, scenario_name: str) -> Path:
    """Return the run's evaluation report, ``{scenario_name}_report.json``."""
    return run_dir / f"{scenario_name}_report.json"


def stdout_log_path(run_dir: Path, scenario_name: str) -> Path:
    """Return the simulation process's stdout log, ``{scenario_name}_stdout.log``."""
    return run_dir / f"{scenario_name}_stdout.log"
