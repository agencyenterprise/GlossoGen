"""What `glossogen new-scenario` writes.

The generated package is checked here for the things that fail late: the
`package-data` entry without which a wheel renders no prompt, and the
entry-point key that has to equal what `name()` returns. That the package also
*runs* is a separate test, in tests/integration.
"""

import tomllib
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenario_entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_scaffold import (
    ScaffoldError,
    default_glossogen_ref,
    distribution_name,
    scenario_class_prefix,
    write_scenario_package,
)

REF = "v9.9.9"


def generate(target: Path, scenario_name: str) -> Path:
    """Write a package and return its directory."""
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
        "reactor_purge/__init__.py",
        "reactor_purge/events.py",
        "reactor_purge/ids.py",
        "reactor_purge/knobs.py",
        "reactor_purge/knobs_default.json",
        "reactor_purge/prompts/briefer_system.jinja",
        "reactor_purge/prompts/relay_system.jinja",
        "reactor_purge/scenario.py",
        "reactor_purge/team_declaration.py",
        "reactor_purge/world.py",
        "tests/test_reactor_purge.py",
    }


def test_the_package_init_is_empty(tmp_path: Path) -> None:
    """Discovery imports submodules of this package while the event union builds.

    Anything in here is imported at that moment, which is what the "why empty
    inits" rule in the guide is about.
    """
    package = generate(tmp_path, "reactor_purge")

    assert (package / "reactor_purge" / "__init__.py").read_text() == ""


def test_the_entry_point_key_is_what_name_returns(tmp_path: Path) -> None:
    """The mistake that puts runs in a directory nothing will look in.

    Generated from one value, so the two cannot disagree, and this is what says
    so if the templates ever drift apart.
    """
    package = generate(tmp_path, "reactor_purge")
    declared = read_pyproject(package)["project"]["entry-points"][SCENARIO_ENTRY_POINT_GROUP]

    assert list(declared) == ["reactor_purge"]
    assert declared["reactor_purge"] == "reactor_purge.scenario:ReactorPurgeScenario"


def test_prompts_and_presets_are_declared_as_package_data(tmp_path: Path) -> None:
    """Without this the wheel carries only `.py` files.

    An editable install still works, which is what makes the omission survive
    until the package is handed to somebody else.
    """
    package = generate(tmp_path, "reactor_purge")
    package_data = read_pyproject(package)["tool"]["setuptools"]["package-data"]

    assert set(package_data["reactor_purge"]) == {"**/*.jinja", "**/*.json"}


def test_async_tests_are_configured_to_run(tmp_path: Path) -> None:
    """Without `asyncio_mode`, every generated async test errors rather than runs."""
    package = generate(tmp_path, "reactor_purge")
    pytest_config = read_pyproject(package)["tool"]["pytest"]["ini_options"]

    assert pytest_config["asyncio_mode"] == "auto"


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
    prompt = (package / "reactor_purge" / "prompts" / "briefer_system.jinja").read_text()

    assert "{{ channels[0].display_name }}" in prompt


def test_a_name_that_is_not_an_identifier_is_refused(tmp_path: Path) -> None:
    """It becomes a module, an entry-point key and a directory."""
    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "Reactor Purge")

    assert "lowercase" in str(refused.value)
    assert not list(tmp_path.iterdir()), "a refused name still wrote something"


def test_a_name_a_built_in_holds_is_refused(tmp_path: Path) -> None:
    """A name already taken stays with the scenario that holds it.

    Generating one anyway produces a package that installs and never resolves,
    and the collision is only logged.
    """
    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "veyru")

    assert "already a scenario" in str(refused.value)


def test_an_existing_directory_is_not_written_over(tmp_path: Path) -> None:
    """Regenerating over a package someone has edited would discard their work."""
    generate(tmp_path, "reactor_purge")

    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "reactor_purge")

    assert "already exists" in str(refused.value)


def test_the_names_derived_from_the_scenario_name() -> None:
    """One value spells the class, the module and the distribution."""
    assert scenario_class_prefix("reactor_purge") == "ReactorPurge"
    assert distribution_name("reactor_purge") == "reactor-purge"


def test_the_default_ref_is_a_release_tag() -> None:
    """Generated packages pin a tag, which is what the install docs tell people to do."""
    assert default_glossogen_ref().startswith("v")
