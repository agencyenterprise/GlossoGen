"""Where the project scan and the configured directory sources start, stop and give up.

Covers what the default scan does with a file it cannot load, where it stops,
which directories it never reads from any working directory, how a configured
folder named like a skipped one is read, and what a child process is told to
import. Each test builds a project under ``tmp_path``.
"""

import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.scenario_contract import scenario_source_kinds
from glossogen.scenario_contract.catalog import (
    ScenarioCatalog,
    ScenarioCatalogError,
    load_scenario_catalog,
)
from glossogen.scenario_contract.scenario_sources import (
    SCENARIOS_ENV_VAR,
    child_process_environment,
    resolve_scenario_sources,
)


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """Every test here imports modules from ``tmp_path``."""
    _ = isolated_scenario_imports


def decorated_module(name: str) -> str:
    """Return a module registering a scenario called ``name``."""
    return textwrap.dedent(f"""
        from glossogen.scenario_contract.registration import scenario
        from glossogen.scenarios.veyru.scenario import VeyruScenario


        @scenario(name={name!r})
        class Scenario(VeyruScenario):
            pass
        """)


def write(root: Path, files: dict[str, str]) -> None:
    """Write ``files``, keyed by path relative to ``root``."""
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def load(
    working_dir: Path,
    cli_sources: tuple[str, ...],
    environ: dict[str, str],
) -> ScenarioCatalog:
    """Resolve the sources for ``working_dir`` and load them."""
    return load_scenario_catalog(
        sources=resolve_scenario_sources(
            cli_sources=cli_sources, environ=environ, working_dir=working_dir, runs_dirs=()
        )
    )


def test_an_empty_scenarios_flag_loads_the_built_ins_only(tmp_path: Path) -> None:
    """``--scenarios ""`` means no scan, as an empty ``GLOSSOGEN_SCENARIOS`` does."""
    write(root=tmp_path, files={"pyproject.toml": "", "scen.py": decorated_module(name="scanned")})

    loaded = load(working_dir=tmp_path, cli_sources=("",), environ={})

    assert loaded.find(name="scanned") is None
    assert len(loaded.loaded_sources) == 1


@pytest.mark.parametrize("project_name", ["tests", "build", "env", "_lab"])
def test_a_project_named_like_a_skipped_folder_is_scanned(
    tmp_path: Path, project_name: str
) -> None:
    """The skip rules apply below the walk's root, not to the root itself."""
    project = tmp_path / project_name
    write(root=project, files={"pyproject.toml": "", "beta/beta.py": decorated_module(name="beta")})

    loaded = load(working_dir=project, cli_sources=(), environ={})

    assert loaded.find(name="beta") is not None


def test_a_configured_folder_named_like_a_skipped_one_is_read(tmp_path: Path) -> None:
    """``--scenarios build`` names that folder on purpose.

    Not ``tests``, which is this repository's own test package in the test process.
    """
    write(
        root=tmp_path,
        files={"pyproject.toml": "", "build/beta/beta.py": decorated_module(name="beta")},
    )

    loaded = load(working_dir=tmp_path, cli_sources=("build",), environ={})

    assert loaded.find(name="beta") is not None


def test_the_project_runs_folder_is_skipped_from_a_subdirectory(tmp_path: Path) -> None:
    """Run from ``<project>/notebooks``, the scan still never reads ``<project>/runs``."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "notebooks/.keep": "",
            "runs/zeta/zeta.py": decorated_module(name="zeta"),
        },
    )

    loaded = load(working_dir=tmp_path / "notebooks", cli_sources=(), environ={})

    assert loaded.find(name="zeta") is None


def test_the_scan_skips_a_file_that_fails_to_import_and_carries_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One broken draft under the project does not stop the command; the log names it.

    The draft registers the name before it raises, and a later file registers the
    same name: the failed import keeps no registration, so the later file loads.
    """
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "a_draft/draft.py": decorated_module(name="shared") + "\nraise RuntimeError('boom')\n",
            "z_good/good.py": decorated_module(name="shared"),
        },
    )

    with caplog.at_level(logging.WARNING):
        loaded = load(working_dir=tmp_path, cli_sources=(), environ={})

    assert loaded.get(name="shared").__module__ == "z_good.good"
    assert str(tmp_path.resolve() / "a_draft" / "draft.py") in caplog.text
    assert "RuntimeError: boom" in caplog.text


def test_the_scan_skips_a_copy_registering_a_built_in_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A vendored copy of a built-in registers its name a second time; the scan leaves it out."""
    write(
        root=tmp_path,
        files={"pyproject.toml": "", "vendor/copy/copy.py": decorated_module(name="veyru")},
    )

    with caplog.at_level(logging.WARNING):
        loaded = load(working_dir=tmp_path, cli_sources=(), environ={})

    assert loaded.get(name="veyru").__module__ == "glossogen.scenarios.veyru.scenario"
    assert "registered twice" in caplog.text


def test_the_scan_leaves_out_a_scenario_the_catalog_refuses_and_tells_no_child(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A scanned class whose events cannot be parsed is logged and left out, children too."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "bad/bad.py": decorated_module(name="bad")
            + "\n    @classmethod\n    def event_types(cls):\n        return (int,)\n",
            "good/good.py": decorated_module(name="good"),
        },
    )

    with caplog.at_level(logging.ERROR):
        loaded = load(working_dir=tmp_path, cli_sources=(), environ={})

    assert loaded.find(name="bad") is None
    assert loaded.find(name="good") is not None
    assert "'bad'" in caplog.text
    assert child_process_environment()[SCENARIOS_ENV_VAR] == "good.good"


def test_a_configured_source_stays_strict(tmp_path: Path) -> None:
    """The same broken file named in ``[tool.glossogen]`` stops the load."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": '[tool.glossogen]\nscenarios = ["draft"]\n',
            "draft/draft.py": decorated_module(name="draft") + "\nraise RuntimeError('boom')\n",
        },
    )

    with pytest.raises(ScenarioCatalogError, match="boom"):
        load(working_dir=tmp_path, cli_sources=(), environ={})


def test_help_works_whatever_the_scan_finds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``glossogen --help`` prints and exits 0 with broken files under the project.

    One raises on import; the other is the project root's own ``__init__.py``,
    which has no module name under the root.
    """
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "__init__.py": decorated_module(name="root_init"),
            "draft/draft.py": decorated_module(name="draft") + "\nraise RuntimeError('boom')\n",
        },
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(SCENARIOS_ENV_VAR, raising=False)
    monkeypatch.setattr("sys.argv", ["glossogen", "--help"])

    with pytest.raises(SystemExit) as exited:
        main()

    assert exited.value.code == 0
    assert "usage: glossogen" in capsys.readouterr().out


def test_the_scan_stops_at_the_file_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Files past the limit are not read at all, and the warning names the root."""
    monkeypatch.setattr(scenario_source_kinds, "LARGE_SCAN_FILE_COUNT", 2)
    write(
        root=tmp_path,
        files={"pyproject.toml": "", "a.py": "", "b.py": "", "c.py": decorated_module(name="late")},
    )

    with caplog.at_level(logging.WARNING):
        loaded = load(working_dir=tmp_path, cli_sources=(), environ={})

    assert loaded.find(name="late") is None
    assert f"Stopped scanning {tmp_path.resolve()}" in caplog.text
    assert "[tool.glossogen] scenarios" in caplog.text


def test_a_scan_with_no_pyproject_warns_before_walking(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """With no project file the root is the working directory, which may be a home directory."""
    with caplog.at_level(logging.WARNING):
        load(working_dir=tmp_path, cli_sources=(), environ={})

    assert f"No pyproject.toml at or above {tmp_path.resolve()}" in caplog.text
    assert "[tool.glossogen] scenarios" in caplog.text


def test_a_non_identifier_folder_inside_the_project_gets_advice_that_works(
    tmp_path: Path,
) -> None:
    """Pointing the source closer cannot help inside the project; the message says rename."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "my-experiments/gamma/gamma.py": decorated_module(name="gamma"),
        },
    )

    with pytest.raises(ScenarioCatalogError) as refused:
        load(working_dir=tmp_path, cli_sources=("my-experiments/gamma",), environ={})

    assert "closer to the file" not in str(refused.value)
    assert "rename the folder" in str(refused.value)


def test_the_scan_says_why_it_skipped_a_non_identifier_folder_with_a_scenario(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A decorated file under ``my-experiments`` cannot load; the scan logs why at INFO."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "my-experiments/gamma/gamma.py": decorated_module(name="gamma"),
        },
    )

    with caplog.at_level(logging.INFO):
        loaded = load(working_dir=tmp_path, cli_sources=(), environ={})

    assert loaded.find(name="gamma") is None
    assert "'my-experiments' is not a Python identifier" in caplog.text
    assert str(tmp_path.resolve() / "my-experiments" / "gamma" / "gamma.py") in caplog.text


def test_a_child_loads_exactly_the_files_the_parent_walk_imported(tmp_path: Path) -> None:
    """A decorated package ``__init__`` does not make the child scan what the walk skipped."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "pkg/__init__.py": decorated_module(name="pkg_scenario"),
            "pkg/tests/__init__.py": "",
            "pkg/tests/extra/__init__.py": "",
            "pkg/tests/extra/extra.py": decorated_module(name="extra"),
        },
    )
    parent = load(working_dir=tmp_path, cli_sources=(), environ={})
    environment = child_process_environment()

    child = load(
        working_dir=tmp_path,
        cli_sources=(),
        environ={SCENARIOS_ENV_VAR: environment[SCENARIOS_ENV_VAR]},
    )

    assert parent.find(name="extra") is None
    assert child.names() == parent.names()


def test_event_types_holding_a_non_event_class_is_refused_naming_the_scenario(
    tmp_path: Path,
) -> None:
    """A configured scenario listing ``int`` as an event fails as a catalog error.

    Not as an ``AttributeError`` from deep inside the parser's construction.
    """
    write(
        root=tmp_path,
        files={
            "pyproject.toml": '[tool.glossogen]\nscenarios = ["bad"]\n',
            "bad/bad.py": decorated_module(name="bad")
            + "\n    @classmethod\n    def event_types(cls):\n        return (int,)\n",
        },
    )

    with pytest.raises(ScenarioCatalogError) as refused:
        load(working_dir=tmp_path, cli_sources=(), environ={})

    assert "Scenario 'bad'" in str(refused.value)
    assert "not an EventBase subclass" in str(refused.value)


def test_the_lookahead_into_a_non_identifier_folder_counts_against_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Looking for a decorated file to explain a skipped folder reads within the walk's budget."""
    monkeypatch.setattr(scenario_source_kinds, "LARGE_SCAN_FILE_COUNT", 2)
    reads: list[str] = []
    real_check = scenario_source_kinds.uses_scenario_decorator

    def counting_check(source: bytes, origin: str) -> bool:
        reads.append(origin)
        return real_check(source=source, origin=origin)

    monkeypatch.setattr(scenario_source_kinds, "uses_scenario_decorator", counting_check)
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            **{f"not-identifier/f{index}.py": "" for index in range(12)},
        },
    )

    with caplog.at_level(logging.WARNING):
        load(working_dir=tmp_path, cli_sources=(), environ={})

    assert len(reads) == 2
    assert "Stopped scanning" in caplog.text


def test_a_child_process_loads_what_the_parent_did_when_one_class_of_a_module_is_refused(
    tmp_path: Path,
) -> None:
    """The scan refuses a whole module, so a real child neither gains nor loses a scenario."""
    write(
        root=tmp_path,
        files={
            "project/pyproject.toml": "",
            "project/mixed/mixed.py": decorated_module(name="review_good") + textwrap.dedent("""

                @scenario(name="review_bad")
                class BadScenario(VeyruScenario):
                    @classmethod
                    def event_types(cls):
                        return (int,)
                """),
            "elsewhere/.keep": "",
        },
    )
    parent = load(working_dir=tmp_path / "project", cli_sources=(), environ={})
    environment = child_process_environment()

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from glossogen.scenario_contract.scenario_sources import "
            "load_configured_scenario_catalog\n"
            "loaded = load_configured_scenario_catalog(cli_sources=(), runs_dirs=())\n"
            "print(','.join(loaded.names()))\n",
        ],
        cwd=tmp_path / "elsewhere",
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
    )

    assert child.returncode == 0, child.stderr
    assert parent.find(name="review_good") is None
    assert child.stdout.strip().split(",") == parent.names()
