"""What a run-folder zip contains, and what it leaves out.

The single-run export and the multi-run one are the same writer called with a
different arc root, so these cover both member layouts and the exclusion rules
they share.

Two of the rules are load-bearing beyond tidiness. Debug and stdout logs are
excluded by default because they are routinely larger than the event log itself,
and an export can ask for them back. `stream.json` and `eval_in_progress.json`
are excluded either way: they describe work in flight, so a re-imported run
carrying them reads as still running.
"""

import csv
import io
import os
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from glossogen.models.event import RunStatus
from glossogen.run_export import export_limits
from glossogen.run_export.export_limits import ExportTooLargeError
from glossogen.run_export.runs_zip_archive import write_runs_zip, write_single_run_zip
from glossogen.server.runs.models import RunSummary

RUN_DIR_NAME = "1777638061"

# One file per rule the filter applies, so a failure names the rule it broke.
INCLUDED_FILES: tuple[str, ...] = (
    "veyru.jsonl",
    "veyru_report.json",
    "labels.json",
    "note.md",
    "replace_config.json",
    "protocol_probe_responses.jsonl",
)

EXCLUDED_FILES: tuple[str, ...] = (
    "veyru_debug.jsonl",
    "veyru_stdout.log",
    "veyru_start.log",
    "eval_stdout.log",
    "stream.json",
    "eval_in_progress.json",
)


def _populate_run_dir(run_dir: Path) -> None:
    """Write one file per include and exclude rule, plus a nested dir and a .git dir."""
    run_dir.mkdir(parents=True)
    for name in INCLUDED_FILES + EXCLUDED_FILES:
        (run_dir / name).write_text(f"contents of {name}\n")

    nested = run_dir / "resume_contexts"
    nested.mkdir()
    (nested / "field_observer.json").write_text("{}\n")

    git_dir = run_dir / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")


def _build_zip(run_dir: Path, include_logs: bool) -> zipfile.ZipFile:
    """Build the run's zip in memory and return it open for reading."""
    buffer = io.BytesIO()
    write_single_run_zip(
        run_dir=run_dir,
        run_dir_name=RUN_DIR_NAME,
        include_logs=include_logs,
        destination=buffer,
    )
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def _member_names(run_dir: Path, include_logs: bool) -> set[str]:
    """Build the run's zip and return its member names."""
    with _build_zip(run_dir=run_dir, include_logs=include_logs) as archive:
        return set(archive.namelist())


def test_every_run_file_is_nested_under_the_run_dir_name(tmp_path: Path) -> None:
    """Extracting into a scenario's runs directory has to reproduce the run directory."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=False)

    assert names
    for name in names:
        assert name.startswith(f"{RUN_DIR_NAME}/")


def test_the_files_a_run_is_read_from_are_present(tmp_path: Path) -> None:
    """The event log, the report, the labels, and the sidecars a metric wrote."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=False)

    for included in INCLUDED_FILES:
        assert f"{RUN_DIR_NAME}/{included}" in names


def test_logs_and_live_state_files_are_left_out(tmp_path: Path) -> None:
    """Debug and stdout logs by size, stream.json and eval_in_progress.json by meaning."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=False)

    for excluded in EXCLUDED_FILES:
        assert f"{RUN_DIR_NAME}/{excluded}" not in names


def test_a_nested_directory_keeps_its_relative_path(tmp_path: Path) -> None:
    """Per-agent resume contexts live in a subdirectory on some runs."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=False)

    assert f"{RUN_DIR_NAME}/resume_contexts/field_observer.json" in names


def test_the_git_directory_is_left_out(tmp_path: Path) -> None:
    """Runs created before the JSONL rewrite carry one, and it is not run data."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=False)

    assert f"{RUN_DIR_NAME}/.git/HEAD" not in names


def test_file_contents_survive_the_round_trip(tmp_path: Path) -> None:
    """A zip whose members are truncated or reordered would still pass the name checks."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    with _build_zip(run_dir=run_dir, include_logs=False) as archive:
        extracted = archive.read(f"{RUN_DIR_NAME}/veyru.jsonl").decode()

    assert extracted == "contents of veyru.jsonl\n"


def test_an_mtime_older_than_the_zip_epoch_is_clamped(tmp_path: Path) -> None:
    """A run copied out of an older archive can carry one, and zip cannot store it."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    pre_1980 = time.mktime((1970, 1, 2, 0, 0, 0, 0, 0, -1))
    target = run_dir / "veyru.jsonl"
    os.utime(target, (pre_1980, pre_1980))

    with _build_zip(run_dir=run_dir, include_logs=False) as archive:
        info = archive.getinfo(f"{RUN_DIR_NAME}/veyru.jsonl")

    assert info.date_time == (1980, 1, 1, 0, 0, 0)


def test_asking_for_logs_puts_them_back(tmp_path: Path) -> None:
    """Whoever is debugging an eval wants the stdout log the default drops."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=True)

    assert f"{RUN_DIR_NAME}/veyru_debug.jsonl" in names
    assert f"{RUN_DIR_NAME}/veyru_stdout.log" in names
    assert f"{RUN_DIR_NAME}/veyru_start.log" in names
    assert f"{RUN_DIR_NAME}/eval_stdout.log" in names


def test_live_state_files_stay_out_even_when_logs_are_asked_for(tmp_path: Path) -> None:
    """They are not logs, and an imported run carrying them reads as busy."""
    run_dir = tmp_path / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    names = _member_names(run_dir=run_dir, include_logs=True)

    assert f"{RUN_DIR_NAME}/stream.json" not in names
    assert f"{RUN_DIR_NAME}/eval_in_progress.json" not in names
    assert f"{RUN_DIR_NAME}/.git/HEAD" not in names


# --- the multi-run layout -------------------------------------------------------


def _summary_for(run_dir: Path, scenario_name: str) -> RunSummary:
    """Build the summary fields the multi-run writer reads off a run."""
    return RunSummary(
        run_id=f"{scenario_name}/{run_dir.name}",
        scenario_name=scenario_name,
        scenario_description="",
        scenario_config={},
        timestamp=datetime(2026, 5, 4, 18, 53, 43, tzinfo=UTC),
        total_messages=0,
        total_cost_usd=0.0,
        duration_seconds=0.0,
        status=RunStatus.SCENARIO_COMPLETE,
        has_evaluation=False,
        evaluation_in_progress=False,
        run_dir=str(run_dir),
        fork_source=None,
        replace_agent_source=None,
        cross_run_replace_agent_source=None,
        fork_at_round_source=None,
        models=[],
        provider="anthropic",
        agent_models=[],
        labels=[],
        has_note=False,
        current_round=0,
        evaluation_content_hash=None,
    )


def _build_multi_zip(runs: list[RunSummary], include_logs: bool) -> zipfile.ZipFile:
    """Write a multi-run zip in memory and return it open for reading."""
    buffer = io.BytesIO()
    write_runs_zip(runs=runs, include_logs=include_logs, destination=buffer)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def test_two_scenarios_sharing_a_run_dir_name_do_not_collide(tmp_path: Path) -> None:
    """Run directories are unix timestamps, so two scenarios can hold the same one."""
    first = tmp_path / "veyru" / RUN_DIR_NAME
    second = tmp_path / "spot_the_difference" / RUN_DIR_NAME
    _populate_run_dir(run_dir=first)
    _populate_run_dir(run_dir=second)

    with _build_multi_zip(
        runs=[_summary_for(first, "veyru"), _summary_for(second, "spot_the_difference")],
        include_logs=False,
    ) as archive:
        names = set(archive.namelist())

    assert f"veyru/{RUN_DIR_NAME}/veyru.jsonl" in names
    assert f"spot_the_difference/{RUN_DIR_NAME}/veyru.jsonl" in names


def test_the_multi_run_layout_extracts_at_the_runs_directory(tmp_path: Path) -> None:
    """Every member sits under ``{scenario}/{run_dir_name}/`` so the tree reproduces."""
    run_dir = tmp_path / "veyru" / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    with _build_multi_zip(runs=[_summary_for(run_dir, "veyru")], include_logs=False) as archive:
        names = [n for n in archive.namelist() if n != "manifest.csv"]

    assert names
    for name in names:
        assert name.startswith(f"veyru/{RUN_DIR_NAME}/")


def test_the_manifest_names_every_run_that_went_in(tmp_path: Path) -> None:
    """Whoever opens the archive can see what it covers without walking it."""
    first = tmp_path / "veyru" / "1"
    second = tmp_path / "veyru" / "2"
    _populate_run_dir(run_dir=first)
    _populate_run_dir(run_dir=second)

    with _build_multi_zip(
        runs=[_summary_for(first, "veyru"), _summary_for(second, "veyru")],
        include_logs=False,
    ) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("manifest.csv").decode())))

    assert [row["run_id"] for row in rows] == ["veyru/1", "veyru/2"]
    assert [row["run_dir_name"] for row in rows] == ["1", "2"]
    for row in rows:
        assert int(row["bytes"]) > 0
        assert row["status"] == "scenario_complete"


def test_the_multi_run_zip_applies_the_same_exclusions(tmp_path: Path) -> None:
    """One predicate serves both layouts, so the rules cannot drift apart."""
    run_dir = tmp_path / "veyru" / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)

    with _build_multi_zip(runs=[_summary_for(run_dir, "veyru")], include_logs=False) as archive:
        without = set(archive.namelist())
    with _build_multi_zip(runs=[_summary_for(run_dir, "veyru")], include_logs=True) as archive:
        with_logs = set(archive.namelist())

    assert f"veyru/{RUN_DIR_NAME}/veyru_debug.jsonl" not in without
    assert f"veyru/{RUN_DIR_NAME}/veyru_debug.jsonl" in with_logs
    assert f"veyru/{RUN_DIR_NAME}/stream.json" not in with_logs


def test_a_selection_over_the_byte_ceiling_is_refused(tmp_path: Path) -> None:
    """A ceiling the writer ignores is not a ceiling."""
    run_dir = tmp_path / "veyru" / RUN_DIR_NAME
    _populate_run_dir(run_dir=run_dir)
    summary = _summary_for(run_dir, "veyru")

    with pytest.MonkeyPatch.context() as patch:
        # ``check_raw_bytes`` reads the ceiling from its own module at call time.
        patch.setattr(export_limits, "MAX_RAW_EXPORT_BYTES", 1)
        with pytest.raises(ExportTooLargeError):
            write_runs_zip(runs=[summary], include_logs=False, destination=io.BytesIO())
