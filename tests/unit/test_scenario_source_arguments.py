"""What `main` reads from the command line before it can build the full parser.

The catalog loads first, so ``--scenarios`` and ``--runs-dir`` are read from the raw
arguments. The second decides which directory the scan of the project skips.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import pytest

from glossogen.cli import cli_entry
from glossogen.scenario_contract.catalog import current_scenario_catalog

SCAN_ROOT_PYPROJECT = ""
SCENARIO_MODULE = """\
from glossogen.scenario_contract.registration import scenario
from glossogen.scenarios.veyru.scenario import VeyruScenario


@scenario(name="zeta_drill")
class Scenario(VeyruScenario):
    pass
"""


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """`main` loads a catalog of its own and imports modules from ``tmp_path``."""
    _ = isolated_scenario_imports


class LoadRequest(NamedTuple):
    """What ``main`` asked the catalog to load."""

    cli_sources: list[str]
    runs_dirs: list[Path]


def requested_load(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> LoadRequest:
    """Run ``main`` on ``argv`` with the loading and the command stubbed, and return the request."""
    requests: list[LoadRequest] = []

    def record(cli_sources: Sequence[str], runs_dirs: Sequence[Path]) -> None:
        requests.append(LoadRequest(cli_sources=list(cli_sources), runs_dirs=list(runs_dirs)))

    monkeypatch.setattr("sys.argv", ["glossogen", *argv])
    monkeypatch.setattr(cli_entry, "load_configured_scenario_catalog", record)
    monkeypatch.setattr(cli_entry, "_dispatch", lambda: None)
    cli_entry.main()
    (request,) = requests
    return request


def test_every_scenarios_flag_before_the_subcommand_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag repeats, and order is kept."""
    request = requested_load(
        argv=["--scenarios", "one", "--scenarios", "two.py", "run", "veyru"],
        monkeypatch=monkeypatch,
    )

    assert request.cli_sources == ["one", "two.py"]
    assert request.runs_dirs == []


def test_a_scenarios_flag_after_the_subcommand_is_left_to_that_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only what precedes the subcommand configures the catalog."""
    request = requested_load(argv=["run", "veyru", "--scenarios", "one"], monkeypatch=monkeypatch)

    assert request.cli_sources == []


def test_every_runs_dir_flag_is_read_wherever_it_appears(monkeypatch: pytest.MonkeyPatch) -> None:
    """A subcommand's own ``--runs-dir`` counts, since that is the directory it works in."""
    request = requested_load(
        argv=["--scenarios", "one", "export", "--runs-dir", "first", "--runs-dir", "second"],
        monkeypatch=monkeypatch,
    )

    assert request.cli_sources == ["one"]
    assert request.runs_dirs == [Path("first"), Path("second")]


def test_no_arguments_read_as_no_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """The empty command line asks for nothing beyond the defaults."""
    request = requested_load(argv=[], monkeypatch=monkeypatch)

    assert request.cli_sources == []
    assert request.runs_dirs == []


def run_main_in(project: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    """Run ``main`` from ``project`` up to loading the catalog, without dispatching a command."""
    monkeypatch.chdir(project)
    monkeypatch.setattr("sys.argv", ["glossogen", *argv])
    monkeypatch.setattr(cli_entry, "_dispatch", lambda: None)
    cli_entry.main()


def write_project_with_a_scenario_in_runs(project: Path) -> None:
    """Write a project whose only scenario sits in a folder called ``myruns``."""
    project.mkdir()
    (project / "pyproject.toml").write_text(SCAN_ROOT_PYPROJECT)
    (project / "myruns" / "zeta_drill").mkdir(parents=True)
    (project / "myruns" / "zeta_drill" / "zeta_drill.py").write_text(SCENARIO_MODULE)


def test_the_scan_loads_a_scenario_in_a_folder_no_command_names_as_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the test below: without the flag the folder is just a folder."""
    write_project_with_a_scenario_in_runs(project=tmp_path / "project")

    run_main_in(project=tmp_path / "project", monkeypatch=monkeypatch, argv=["export"])

    assert current_scenario_catalog().find(name="zeta_drill") is not None


def test_a_runs_dir_flag_reaches_the_scans_skip_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The folder named as the runs directory is not read for scenarios."""
    write_project_with_a_scenario_in_runs(project=tmp_path / "project")

    run_main_in(
        project=tmp_path / "project",
        monkeypatch=monkeypatch,
        argv=["--runs-dir", "myruns", "export"],
    )

    assert current_scenario_catalog().find(name="zeta_drill") is None
