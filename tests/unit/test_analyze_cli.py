"""`glossogen analyze`, from the arguments through to the printed table.

The command reads the runs directory directly, with no server and no database, so
these drive it end to end against run directories built in a temp dir. Driven
through `main` with a patched `sys.argv`, the way the other command tests are,
because the argument parsing and the exit code are part of what is checked.

What matters most here is that the printed numbers are the ones the engine
computed, since this command is what a chart's numbers get checked against.
"""

import json
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.cli import main
from glossogen.models.event import RunStatus, SimulationEnded, SimulationStarted

SCENARIO = "veyru"
QUIET_RUN = "1777638061"
NOISY_RUN = "1777638099"
UNEVALUATED_RUN = "1777638120"


def started_event(run_id: str, noise: float) -> SimulationStarted:
    """The first line of a run's event log, carrying the knobs it ran with."""
    return SimulationStarted(
        round_number=0,
        run_id=run_id,
        scenario_name=SCENARIO,
        scenario_description="A scenario",
        channel_ids=["link"],
        provider="anthropic",
        scenario_config={"round_count": 15, "channel_noise_level": noise},
    )


ENDED_EVENT = SimulationEnded(
    round_number=15,
    reason=RunStatus.SCENARIO_COMPLETE,
    total_messages=81,
    total_cost_usd=1.25,
)


def report(score: float) -> dict[str, Any]:
    """An evaluation report carrying one metric with one round observation."""
    return {
        "simulation_id": "sim-1",
        "scenario_name": SCENARIO,
        "measurements": [
            {
                "metric_name": "round_success",
                "score": score,
                "score_unit": "fraction of rounds",
                "summary": "some of 15",
                "per_round": [{"round_number": 1, "value": score, "note": "ok"}],
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


def write_run(runs_dir: Path, run_dir_name: str, noise: float, score: float | None) -> None:
    """Write one finished run directory, evaluated or not."""
    run_dir = runs_dir / SCENARIO / run_dir_name
    run_dir.mkdir(parents=True)
    events = [
        started_event(run_id=run_dir_name, noise=noise).model_dump_json().encode(),
        ENDED_EVENT.model_dump_json().encode(),
    ]
    (run_dir / f"{SCENARIO}.jsonl").write_bytes(b"\n".join(events) + b"\n")
    (run_dir / "labels.json").write_bytes(orjson.dumps(["channel_noise"]))
    if score is not None:
        (run_dir / f"{SCENARIO}_report.json").write_bytes(orjson.dumps(report(score=score)))


@pytest.fixture(name="runs_dir")
def runs_dir_fixture(tmp_path: Path) -> Path:
    """Two evaluated runs at different noise levels, and one never evaluated."""
    runs_dir = tmp_path / "runs"
    write_run(runs_dir=runs_dir, run_dir_name=QUIET_RUN, noise=0.2, score=0.8)
    write_run(runs_dir=runs_dir, run_dir_name=NOISY_RUN, noise=0.6, score=0.2)
    write_run(runs_dir=runs_dir, run_dir_name=UNEVALUATED_RUN, noise=0.6, score=None)
    return runs_dir


def analyze(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `glossogen analyze` with the given flags."""
    monkeypatch.setattr("sys.argv", ["glossogen", "analyze", *argv])
    main()


def analyze_json(
    argv: list[str],
    runs_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    """Run the command with --json and parse what it printed."""
    analyze(["--runs-dir", str(runs_dir), "--json", *argv], monkeypatch)
    return json.loads(capsys.readouterr().out)


def test_a_knob_condition_narrows_which_runs_are_analyzed(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`analyze` takes the same knob conditions the runs list and export do.

    It reaches `_export_selection_from_args`, which reads `args.knob`, so a
    parser missing the flag raises AttributeError on every invocation rather
    than on the ones that use it.
    """
    result = analyze_json(
        argv=[
            "--knob",
            "channel_noise_level<0.5",
            "--group-by",
            "knob.channel_noise_level",
            "--measure",
            "round_success:mean",
        ],
        runs_dir=runs_dir,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert [row["group_values"] for row in result["rows"]] == [["0.2"]]
    assert result["run_count"] == 1


def test_knob_conditions_are_and_matched_by_analyze(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two conditions that cannot both hold narrow to nothing.

    This command refuses an empty selection, so the exit is what says the second
    condition was applied rather than ignored.
    """
    with pytest.raises(SystemExit, match="matches no runs"):
        analyze(
            [
                "--runs-dir",
                str(runs_dir),
                "--knob",
                "channel_noise_level<0.5",
                "--knob",
                "channel_noise_level>0.5",
                "--group-by",
                "knob.channel_noise_level",
                "--measure",
                "round_success:mean",
            ],
            monkeypatch,
        )


def test_analyze_refuses_a_malformed_knob_condition(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused at the selection, with the message the export path gives."""
    with pytest.raises(SystemExit, match="carries no operator"):
        analyze(
            [
                "--runs-dir",
                str(runs_dir),
                "--knob",
                "noiselevel0.5",
                "--group-by",
                "knob.channel_noise_level",
                "--measure",
                "round_success:mean",
            ],
            monkeypatch,
        )


def test_grouping_on_a_knob_reports_one_row_per_value(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = analyze_json(
        argv=["--group-by", "knob.channel_noise_level", "--measure", "round_success:mean"],
        runs_dir=runs_dir,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert [row["group_values"] for row in result["rows"]] == [["0.2"], ["0.6"]]
    assert result["rows"][0]["cells"][0]["value"] == pytest.approx(0.8)


def test_the_unevaluated_run_is_counted_as_missing_rather_than_as_zero(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = analyze_json(
        argv=["--group-by", "knob.channel_noise_level", "--measure", "round_success:mean"],
        runs_dir=runs_dir,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    noisy = result["rows"][1]
    assert noisy["run_count"] == 2
    assert noisy["cells"][0]["observation_count"] == 1
    assert noisy["cells"][0]["missing_count"] == 1
    assert noisy["cells"][0]["value"] == pytest.approx(0.2)


def test_a_run_column_measure_covers_the_run_that_has_no_report(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = analyze_json(
        argv=["--measure", "run_column:total_cost_usd:mean"],
        runs_dir=runs_dir,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert result["rows"][0]["cells"][0]["observation_count"] == 3


def test_the_round_grain_reads_the_per_round_observations(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = analyze_json(
        argv=[
            "--grain",
            "round",
            "--group-by",
            "round_number",
            "--measure",
            "round_success:mean",
        ],
        runs_dir=runs_dir,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert [row["group_values"] for row in result["rows"]] == [["1"]]
    assert result["rows"][0]["cells"][0]["observation_count"] == 2


def test_a_filter_narrows_the_selection(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = analyze_json(
        argv=[
            "--filter",
            "knob.channel_noise_level:gte:0.5",
            "--group-by",
            "run_id",
            "--measure",
            "round_success:mean",
        ],
        runs_dir=runs_dir,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert [row["group_values"][0] for row in result["rows"]] == [
        f"{SCENARIO}/{NOISY_RUN}",
        f"{SCENARIO}/{UNEVALUATED_RUN}",
    ]


def test_listing_fields_names_the_knob_and_the_metric(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    analyze(["--runs-dir", str(runs_dir), "--list-fields"], monkeypatch)

    printed = capsys.readouterr().out
    assert "knob.channel_noise_level" in printed
    assert "metric:round_success" in printed


def test_the_printed_table_shows_a_dash_where_nothing_could_be_computed(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    analyze(
        [
            "--runs-dir",
            str(runs_dir),
            "--run-id",
            f"{SCENARIO}/{UNEVALUATED_RUN}",
            "--measure",
            "round_success:mean",
        ],
        monkeypatch,
    )

    printed = capsys.readouterr().out
    assert " - " in printed


def test_a_measure_with_an_unknown_aggregate_is_refused_by_name(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as refusal:
        analyze(["--runs-dir", str(runs_dir), "--measure", "round_success:average"], monkeypatch)

    assert "average" in str(refusal.value)


def test_asking_for_no_measure_says_how_to_find_one(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as refusal:
        analyze(["--runs-dir", str(runs_dir), "--group-by", "run_id"], monkeypatch)

    assert "--list-fields" in str(refusal.value)


def test_naming_runs_and_filtering_at_once_is_refused(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit):
        analyze(
            [
                "--runs-dir",
                str(runs_dir),
                "--run-id",
                f"{SCENARIO}/{QUIET_RUN}",
                "--label",
                "channel_noise",
                "--measure",
                "round_success:mean",
            ],
            monkeypatch,
        )


# --- specs the command refuses by name ------------------------------------------


def test_a_measure_that_is_not_two_or_three_parts_is_refused(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as refusal:
        analyze(["--runs-dir", str(runs_dir), "--measure", "round_success"], monkeypatch)

    assert "key:aggregate" in str(refusal.value)


def test_an_unknown_measure_source_is_refused_by_name(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as refusal:
        analyze(
            ["--runs-dir", str(runs_dir), "--measure", "sidecar:round_success:mean"], monkeypatch
        )

    assert "sidecar" in str(refusal.value)


def test_an_unknown_filter_operator_is_refused_by_name(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as refusal:
        analyze(
            [
                "--runs-dir",
                str(runs_dir),
                "--measure",
                "round_success:mean",
                "--filter",
                "model_class:resembles:closed",
            ],
            monkeypatch,
        )

    assert "resembles" in str(refusal.value)


def test_a_filter_with_no_value_to_compare_against_is_refused(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as refusal:
        analyze(
            [
                "--runs-dir",
                str(runs_dir),
                "--measure",
                "round_success:mean",
                "--filter",
                "model_class:in",
            ],
            monkeypatch,
        )

    assert "value" in str(refusal.value)


def test_an_emptiness_filter_needs_no_value(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    analyze(
        [
            "--runs-dir",
            str(runs_dir),
            "--measure",
            "round_success:mean",
            "--filter",
            "labels:is_not_empty",
            "--group-by",
            "run_id",
        ],
        monkeypatch,
    )

    assert "veyru/" in capsys.readouterr().out
