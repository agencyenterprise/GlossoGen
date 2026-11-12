"""`--scenarios` after the subcommand is refused, by `evaluate` as by every other subcommand.

`--scenarios` is read before the subcommand only. Placed after it, `evaluate`
used to drop it silently and then answer that the scenario was not loaded,
telling the user to pass the flag they had just passed.
"""

from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.scenario_contract.scenario_sources import SCENARIOS_ENV_VAR


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """`main` loads a catalog of its own."""
    _ = isolated_scenario_imports


def run_main(argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SystemExit:
    """Run ``glossogen <argv>`` from an empty directory, built-ins only; return its exit."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SCENARIOS_ENV_VAR, "")
    monkeypatch.setattr("sys.argv", ["glossogen", *argv])
    with pytest.raises(SystemExit) as exited:
        main()
    return exited.value


def test_evaluate_rejects_scenarios_after_the_subcommand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """argparse names the misplaced flag instead of the scenario being missing."""
    exited = run_main(
        argv=[
            "evaluate",
            "alpha_s",
            "--scenarios",
            "./alpha_s",
            "--run-dir",
            "runs/alpha_s/1",
            "--metrics",
            "word_count",
            "--model",
            "claude-haiku-4-5-20251001",
            "--provider",
            "anthropic",
        ],
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )

    assert exited.code == 2
    assert "unrecognized arguments: --scenarios ./alpha_s" in capsys.readouterr().err


def test_the_not_loaded_message_says_where_scenarios_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix it suggests is one the user can type."""
    exited = run_main(
        argv=[
            "evaluate",
            "alpha_s",
            "--run-dir",
            "runs/alpha_s/1",
            "--metrics",
            "word_count",
            "--model",
            "claude-haiku-4-5-20251001",
            "--provider",
            "anthropic",
        ],
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )

    assert "'alpha_s' is not loaded" in str(exited.code)
    assert "--scenarios, before the subcommand" in str(exited.code)
