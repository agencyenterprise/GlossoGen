"""What `glossogen new-scenario` writes.

The generated project is checked here for the things that fail late: the
`[tool.glossogen]` source that makes glossogen load the scenario, and the
`package-data` entry without which a wheel renders no prompt. That the project
also *runs* is a separate test, in tests/integration.
"""

import tomllib
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenario_authoring.scenario_scaffold import (
    ScaffoldError,
    default_glossogen_ref,
    distribution_name,
    scenario_class_prefix,
    write_scenario_package,
)

REF = "v9.9.9"


def generate(target: Path, scenario_name: str) -> Path:
    """Write a project and return its directory."""
    return write_scenario_package(
        scenario_name=scenario_name, target_dir=target, glossogen_ref=REF
    ).package_dir


def read_pyproject(package_dir: Path) -> dict[str, Any]:
    """Parse the generated pyproject the way a build backend would."""
    return tomllib.loads((package_dir / "pyproject.toml").read_text())


def test_the_layout_is_the_one_the_guide_describes(tmp_path: Path) -> None:
    """Every file a scenario needs, and nothing that has to be filled in first."""
    package = generate(tmp_path, "reactor_purge")

    written = {
        path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()
    }
    assert written == {
        ".env.example",
        ".gitignore",
        "README.md",
        "pyproject.toml",
        "scenarios/knobs_default.json",
        "scenarios/prompts/briefer_system.jinja",
        "scenarios/prompts/relay_system.jinja",
        "scenarios/reactor_purge.py",
        "tests/test_reactor_purge.py",
    }


def test_the_scenario_folder_is_the_configured_source(tmp_path: Path) -> None:
    """`[tool.glossogen] scenarios` names the folder, so no scan is needed to find it."""
    package = generate(tmp_path, "reactor_purge")

    assert read_pyproject(package)["tool"]["glossogen"]["scenarios"] == ["scenarios"]
    assert "entry-points" not in read_pyproject(package)["project"]


def test_the_module_registers_the_scenario_under_its_name(tmp_path: Path) -> None:
    """The decorator carries the name, which is also the event prefix."""
    package = generate(tmp_path, "reactor_purge")
    module = (package / "scenarios" / "reactor_purge.py").read_text()

    assert '@scenario(name="reactor_purge")' in module
    assert '"reactor_purge_round_opened"' in module
    assert "def event_types(cls)" in module


def test_prompts_and_presets_are_declared_as_package_data(tmp_path: Path) -> None:
    """Without this the wheel carries only `.py` files.

    An editable install still works, which is what makes the omission survive
    until the package is handed to somebody else.
    """
    package = generate(tmp_path, "reactor_purge")
    package_data = read_pyproject(package)["tool"]["setuptools"]["package-data"]

    assert set(package_data["scenarios"]) == {"**/*.jinja", "**/*.json"}


def test_only_the_scenario_folder_is_packaged(tmp_path: Path) -> None:
    """`where = ["."]` alone would ship every top-level package added later.

    An author whose repository grows a second package would find it inside this
    distribution, without having said so anywhere.
    """
    package = generate(tmp_path, "reactor_purge")
    found = read_pyproject(package)["tool"]["setuptools"]["packages"]["find"]

    assert found["include"] == ["scenarios*"]


def test_async_tests_are_configured_to_run(tmp_path: Path) -> None:
    """Without `asyncio_mode`, every generated async test errors rather than runs."""
    package = generate(tmp_path, "reactor_purge")
    pytest_config = read_pyproject(package)["tool"]["pytest"]["ini_options"]

    assert pytest_config["asyncio_mode"] == "auto"
    assert pytest_config["pythonpath"] == ["."], "the tests import scenarios.<name>"


def test_glossogen_is_pinned_to_the_ref_it_was_given(tmp_path: Path) -> None:
    """A generated package installs the platform it was generated against."""
    package = generate(tmp_path, "reactor_purge")
    project = read_pyproject(package)["project"]

    assert any(REF in str(entry) for entry in project["dependencies"])
    assert any(REF in str(entry) for entry in project["optional-dependencies"]["testing"])


def test_the_prompt_templates_keep_their_own_placeholders(tmp_path: Path) -> None:
    """The scaffold renders with `<<>>`, so `{{ }}` survives into the output.

    A prompt whose placeholders were consumed at generation time renders a
    channel name of nothing, at the first turn of the first paid run.
    """
    package = generate(tmp_path, "reactor_purge")
    prompt = (package / "scenarios" / "prompts" / "briefer_system.jinja").read_text()

    assert "{{ channels[0].display_name }}" in prompt


def test_a_name_that_is_not_an_identifier_is_refused(tmp_path: Path) -> None:
    """It becomes a module and a run directory."""
    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "Reactor Purge")

    assert "lowercase" in str(refused.value)
    assert not list(tmp_path.iterdir()), "a refused name still wrote something"


def test_a_name_a_built_in_holds_is_refused(tmp_path: Path) -> None:
    """Two classes registering one name stop every command that loads both."""
    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "veyru")

    assert "already a scenario" in str(refused.value)


def test_an_existing_directory_is_not_written_over(tmp_path: Path) -> None:
    """Regenerating over a project someone has edited would discard their work."""
    generate(tmp_path, "reactor_purge")

    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "reactor_purge")

    assert "already exists" in str(refused.value)


def test_the_names_derived_from_the_scenario_name() -> None:
    """One value spells the class, the module and the project directory."""
    assert scenario_class_prefix("reactor_purge") == "ReactorPurge"
    assert distribution_name("reactor_purge") == "reactor-purge"


def test_the_default_ref_is_a_release_tag() -> None:
    """Generated packages pin a tag, which is what the install docs tell people to do."""
    assert default_glossogen_ref().startswith("v")
