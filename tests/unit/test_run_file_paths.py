"""The run-file names ``run_file_paths`` spells, held to the names runs on disk carry.

The expected names are the ones listed under "Run Output Directory Structure" in
CLAUDE.md, written out literally so a change to the helpers shows up here.
"""

from pathlib import Path

from glossogen.run_storage.run_file_paths import (
    debug_log_path,
    evaluation_report_path,
    event_log_path,
    stdout_log_path,
)

_RUN_DIR = Path("runs") / "veyru" / "1760000000"


def test_the_event_log_is_named_after_the_scenario() -> None:
    assert event_log_path(run_dir=_RUN_DIR, scenario_name="veyru") == _RUN_DIR / "veyru.jsonl"


def test_the_debug_log_carries_the_debug_suffix() -> None:
    assert debug_log_path(run_dir=_RUN_DIR, scenario_name="veyru") == _RUN_DIR / "veyru_debug.jsonl"


def test_the_evaluation_report_carries_the_report_suffix() -> None:
    assert (
        evaluation_report_path(run_dir=_RUN_DIR, scenario_name="veyru")
        == _RUN_DIR / "veyru_report.json"
    )


def test_the_stdout_log_carries_the_stdout_suffix() -> None:
    assert stdout_log_path(run_dir=_RUN_DIR, scenario_name="veyru") == _RUN_DIR / "veyru_stdout.log"


def test_a_scenario_name_with_underscores_is_used_whole() -> None:
    scenario_name = "container_yard_stacking"

    assert event_log_path(run_dir=_RUN_DIR, scenario_name=scenario_name).name == (
        "container_yard_stacking.jsonl"
    )
    assert evaluation_report_path(run_dir=_RUN_DIR, scenario_name=scenario_name).name == (
        "container_yard_stacking_report.json"
    )
