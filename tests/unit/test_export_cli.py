"""`glossogen export`, from the arguments through to the files on disk.

The command reads the runs directory directly, with no server and no database, so
these drive it end to end against a run directory built in a temp dir.

Driven through `main` with a patched `sys.argv`, the way the other command tests
are, because the argument parsing and the exit code are part of what is being
checked. A zero exit is the absence of a raise rather than `SystemExit(0)`.

The `--status` assertions are behavioural on purpose: that field reached the
selection model and was then ignored, so what is worth pinning is that the flag
changes which runs come out.
"""

import csv
import zipfile
from pathlib import Path

import orjson
import pytest

from glossogen.cli import main
from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted

SCENARIO = "veyru"
FINISHED = "1777638061"
RUNNING = "1777638099"


def started_event(run_id: str) -> SimulationStarted:
    """The first line of a run's event log, carrying the knobs it ran with."""
    return SimulationStarted(
        round_number=0,
        run_id=run_id,
        scenario_name=SCENARIO,
        scenario_description="A scenario",
        channel_ids=["link"],
        provider="anthropic",
        scenario_config={"round_count": 15, "postmortem_enabled": False},
    )


ENDED_EVENT = SimulationEnded(
    round_number=15,
    reason=RunStatus.SCENARIO_COMPLETE,
    total_messages=81,
    total_cost_usd=1.25,
)

REPORT: dict[str, object] = {
    "simulation_id": "sim-1",
    "scenario_name": SCENARIO,
    "measurements": [
        {
            "metric_name": "round_success",
            "score": 0.6,
            "score_unit": "fraction of rounds",
            "summary": "9 of 15",
            "per_round": [{"round_number": 1, "value": 1.0, "note": "ok"}],
            "per_agent": [],
        }
    ],
    "evaluation_cost": {
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
        "estimated_cost_usd": 0.01,
        "model": "claude-haiku-4-5-20251001",
        "provider_name": "anthropic",
    },
}


def write_run(runs_dir: Path, run_dir_name: str, finished: bool) -> None:
    """Write one run directory, finished or still running."""
    run_dir = runs_dir / SCENARIO / run_dir_name
    run_dir.mkdir(parents=True)
    events = [started_event(run_id=run_dir_name).model_dump_json().encode()]
    if finished:
        events.append(ENDED_EVENT.model_dump_json().encode())
        (run_dir / f"{SCENARIO}_report.json").write_bytes(orjson.dumps(REPORT))
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(b"\n".join(events) + b"\n")
    (run_dir / "labels.json").write_bytes(orjson.dumps(["baseline_oss", "budget=800"]))
    (run_dir / f"{SCENARIO}_debug.jsonl").write_text("noise\n")


@pytest.fixture(name="runs_dir")
def runs_dir_fixture(tmp_path: Path) -> Path:
    """A runs directory holding one finished, evaluated run and one still running."""
    runs_dir = tmp_path / "runs"
    write_run(runs_dir=runs_dir, run_dir_name=FINISHED, finished=True)
    write_run(runs_dir=runs_dir, run_dir_name=RUNNING, finished=False)
    return runs_dir


def export(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `glossogen export` with the given flags."""
    monkeypatch.setattr("sys.argv", ["glossogen", "export", *argv])
    main()


def rows_of(path: Path) -> list[dict[str, str]]:
    """Read a written CSV back."""
    return list(csv.DictReader(path.open(newline="")))


# --- the selection contract -----------------------------------------------------


def test_naming_runs_and_filtering_at_once_is_refused(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two forms answer different questions, so combining them has no meaning."""
    with pytest.raises(SystemExit):
        export(
            [
                "--runs-dir",
                str(runs_dir),
                "--out",
                str(tmp_path / "out"),
                "--run-id",
                f"{SCENARIO}/{FINISHED}",
                "--label",
                "baseline_oss",
            ],
            monkeypatch,
        )


def test_status_counts_as_a_filter(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It narrows the same way the others do, so it cannot be mixed with ids either."""
    with pytest.raises(SystemExit):
        export(
            [
                "--runs-dir",
                str(runs_dir),
                "--out",
                str(tmp_path / "out"),
                "--run-id",
                f"{SCENARIO}/{FINISHED}",
                "--status",
                "scenario_complete",
            ],
            monkeypatch,
        )


def test_naming_one_run_exports_only_that_run(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form the checkbox list produces."""
    out = tmp_path / "out"
    export(
        [
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(out),
            "--frames",
            "run_level",
            "--run-id",
            f"{SCENARIO}/{FINISHED}",
        ],
        monkeypatch,
    )
    assert [row["run_id"] for row in rows_of(out / "run_level.csv")] == [f"{SCENARIO}/{FINISHED}"]


def test_a_run_id_that_does_not_exist_exits_naming_it(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command exits non-zero and names the id, so a script can react to it."""
    with pytest.raises(SystemExit) as raised:
        export(
            [
                "--runs-dir",
                str(runs_dir),
                "--out",
                str(tmp_path / "out"),
                "--run-id",
                f"{SCENARIO}/999",
            ],
            monkeypatch,
        )
    assert f"{SCENARIO}/999" in str(raised.value)


def test_no_filters_exports_every_run(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No filters means every run, including the one still going."""
    out = tmp_path / "out"
    export(["--runs-dir", str(runs_dir), "--out", str(out), "--frames", "run_level"], monkeypatch)
    assert len(rows_of(out / "run_level.csv")) == 2


def test_the_status_flag_narrows_to_finished_runs(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exporting only what finished is the reason the flag exists."""
    out = tmp_path / "out"
    export(
        [
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(out),
            "--frames",
            "run_level",
            "--status",
            "scenario_complete",
        ],
        monkeypatch,
    )
    assert [row["run_id"] for row in rows_of(out / "run_level.csv")] == [f"{SCENARIO}/{FINISHED}"]


def test_a_filter_matching_nothing_exits_rather_than_writing(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty export is a mistake worth stopping on, not a set of empty files."""
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        export(
            ["--runs-dir", str(runs_dir), "--out", str(out), "--label", "no_such_label"],
            monkeypatch,
        )
    assert not out.exists()


def test_an_unknown_table_name_is_named_in_the_error(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message has to say which value was wrong."""
    with pytest.raises(SystemExit) as raised:
        export(
            [
                "--runs-dir",
                str(runs_dir),
                "--out",
                str(tmp_path / "out"),
                "--frames",
                "run_level,nonsense",
            ],
            monkeypatch,
        )
    assert "nonsense" in str(raised.value)


def test_a_selection_over_max_runs_exits(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag exists to be raised locally, so it has to be enforced."""
    with pytest.raises(SystemExit) as raised:
        export(
            ["--runs-dir", str(runs_dir), "--out", str(tmp_path / "out"), "--max-runs", "1"],
            monkeypatch,
        )
    assert "1" in str(raised.value)


# --- what gets written ----------------------------------------------------------


def test_every_table_plus_the_legend_is_written(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The four files a caller gets when they ask for all three tables."""
    out = tmp_path / "out"
    export(["--runs-dir", str(runs_dir), "--out", str(out)], monkeypatch)

    assert sorted(path.name for path in out.iterdir()) == [
        "agent_level.csv",
        "columns.csv",
        "round_level.csv",
        "run_level.csv",
    ]


def test_the_run_table_carries_knob_label_and_metric_columns(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The three column families that make the export scenario-agnostic."""
    out = tmp_path / "out"
    export(
        [
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(out),
            "--frames",
            "run_level",
            "--status",
            "scenario_complete",
        ],
        monkeypatch,
    )
    [row] = rows_of(out / "run_level.csv")

    assert row["knob.round_count"] == "15"
    assert row["knob.postmortem_enabled"] == "False"
    assert row["label.budget"] == "800"
    assert row["metric.round_success"] == "0.6"


def test_an_unevaluated_run_gets_an_empty_metric_cell(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The running run has no report, and an empty cell is not a zero."""
    out = tmp_path / "out"
    export(["--runs-dir", str(runs_dir), "--out", str(out), "--frames", "run_level"], monkeypatch)
    by_id = {row["run_id"]: row for row in rows_of(out / "run_level.csv")}

    assert by_id[f"{SCENARIO}/{FINISHED}"]["metric.round_success"] == "0.6"
    assert by_id[f"{SCENARIO}/{RUNNING}"]["metric.round_success"] == ""


def test_the_long_table_carries_the_per_round_observation(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row per observation a metric reported, and the report carries one."""
    out = tmp_path / "out"
    export(["--runs-dir", str(runs_dir), "--out", str(out), "--frames", "round_level"], monkeypatch)
    [row] = rows_of(out / "round_level.csv")

    assert row["metric_name"] == "round_success"
    assert row["round_number"] == "1"
    assert row["score_unit"] == "fraction of rounds"


def test_the_legend_records_each_column_and_its_coverage(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is the recoverable half of a blank cell in a sparse export."""
    out = tmp_path / "out"
    export(["--runs-dir", str(runs_dir), "--out", str(out)], monkeypatch)
    legend = {row["column"]: row for row in rows_of(out / "columns.csv")}

    assert legend["knob.round_count"]["group"] == "knob"
    assert legend["label.budget"]["group"] == "label"
    assert legend["metric.round_success"]["unit"] == "fraction of rounds"
    assert legend["metric.round_success"]["runs_with_value"] == "1"
    assert legend["metric.round_success"]["run_count"] == "2"


def test_the_raw_flag_writes_a_zip_without_the_debug_log(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Logs are excluded by default, and the fixture carries one to prove it."""
    out = tmp_path / "out"
    export(
        ["--runs-dir", str(runs_dir), "--out", str(out), "--frames", "run_level", "--raw"],
        monkeypatch,
    )
    with zipfile.ZipFile(out / "runs.zip") as archive:
        names = set(archive.namelist())

    assert f"{SCENARIO}/{FINISHED}/{SCENARIO}.jsonl" in names
    assert f"{SCENARIO}/{FINISHED}/{SCENARIO}_debug.jsonl" not in names
    assert "manifest.csv" in names


def test_include_logs_puts_the_debug_log_back(
    runs_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The opt-in half of the same rule."""
    out = tmp_path / "out"
    export(
        [
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(out),
            "--frames",
            "run_level",
            "--raw",
            "--include-logs",
        ],
        monkeypatch,
    )
    with zipfile.ZipFile(out / "runs.zip") as archive:
        names = set(archive.namelist())

    assert f"{SCENARIO}/{FINISHED}/{SCENARIO}_debug.jsonl" in names
