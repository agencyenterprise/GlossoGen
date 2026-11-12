"""`new-scenario` refuses a name that is already an importable module.

The folder it writes is imported under the scenario's name. A name the standard
library, an installed package or glossogen already uses would hide that module,
or be hidden by it, and every later command in that directory would fail.
"""

from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.scenario_authoring.scenario_scaffold import ScaffoldError, write_scenario_folder
from glossogen.scenario_contract.scenario_sources import SCENARIOS_ENV_VAR


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """`main` loads a catalog of its own."""
    _ = isolated_scenario_imports


@pytest.mark.parametrize("name", ["signal", "secrets", "pydantic", "glossogen"])
def test_a_name_that_shadows_an_importable_module_is_refused(tmp_path: Path, name: str) -> None:
    """Standard library, an installed package, and glossogen itself."""
    with pytest.raises(ScaffoldError) as refused:
        write_scenario_folder(scenario_name=name, target_dir=tmp_path)

    assert f"{name!r} is already an importable module" in str(refused.value)
    assert not list(tmp_path.iterdir()), "a refused name still wrote something"


def test_the_command_exits_before_writing_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``glossogen new-scenario signal`` says why and leaves the directory as it was."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(SCENARIOS_ENV_VAR, "")
    monkeypatch.setattr("sys.argv", ["glossogen", "new-scenario", "signal"])

    with pytest.raises(SystemExit) as exited:
        main()

    assert "'signal' is already an importable module" in str(exited.value.code)
    assert not list(tmp_path.iterdir())
