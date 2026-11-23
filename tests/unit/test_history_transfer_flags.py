"""`glossogen run` refuses `--history-*` flags that do not describe one history transfer.

Each refusal happens while the flags are read, before the run's config is built
or a run directory is claimed, and argparse reports it with exit status 2.
"""

from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.scenario_contract.scenario_sources import SCENARIOS_ENV_VAR

RUN_ARGS = ["run", "veyru", "--model", "claude-haiku-5-5", "--provider", "anthropic"]
RUNS_DIR_ARGS = ["--runs-dir", "runs", "--config", "knobs_default"]
SOURCE_ARGS = ["--history-from-run", "runs/veyru/1"]


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """`main` loads a catalog of its own."""
    _ = isolated_scenario_imports


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (
            ["--history-seat", "a=b"],
            "--history-seat and --history-through-round need --history-from-run",
        ),
        (
            ["--history-through-round", "3"],
            "--history-seat and --history-through-round need --history-from-run",
        ),
        (SOURCE_ARGS, "--history-from-run needs at least one --history-seat"),
        ([*SOURCE_ARGS, "--history-seat", "a"], "--history-seat expects SEAT=SOURCE_AGENT"),
        ([*SOURCE_ARGS, "--history-seat", "=b"], "--history-seat expects SEAT=SOURCE_AGENT"),
        (
            [*SOURCE_ARGS, "--history-seat", "a=b", "--history-seat", "a=c"],
            "--history-seat names seat 'a' twice",
        ),
    ],
)
def test_history_flags_that_describe_no_single_transfer_are_refused(
    flags: list[str],
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """argparse names the flag that is wrong."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SCENARIOS_ENV_VAR, "")
    monkeypatch.setattr("sys.argv", ["glossogen", *RUN_ARGS, *RUNS_DIR_ARGS, *flags])

    with pytest.raises(SystemExit) as exited:
        main()

    assert exited.value.code == 2
    assert message in capsys.readouterr().err


def test_a_resume_with_a_history_source_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A history transfer starts a new run; a resumed one reads its histories from its directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SCENARIOS_ENV_VAR, "")
    monkeypatch.setattr(
        "sys.argv",
        [
            "glossogen",
            *RUN_ARGS,
            "--resume",
            "runs/veyru/2",
            "--config",
            "knobs_default",
            *SOURCE_ARGS,
            "--history-seat",
            "a=b",
        ],
    )

    with pytest.raises(SystemExit) as exited:
        main()

    assert exited.value.code == 2
    assert "--history-from-run starts a new run" in capsys.readouterr().err
