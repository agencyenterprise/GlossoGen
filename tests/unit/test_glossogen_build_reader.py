"""`read_glossogen_build`: the version and commit for each way glossogen can be installed.

Each test replaces the installed distribution with a fake whose ``direct_url.json``
describes one kind of install. The editable cases point it at a git repository made
in ``tmp_path``.
"""

import json
import subprocess
from importlib import metadata
from pathlib import Path

import pytest
from pydantic import ValidationError

from glossogen.models.glossogen_build import GlossogenBuild
from glossogen.runtime import glossogen_build_reader
from glossogen.runtime.glossogen_build_reader import read_glossogen_build


class _FakeDistribution:
    """The two things the reader asks of an installed distribution."""

    def __init__(self, direct_url: str | None) -> None:
        self.version = "9.8.7"
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return self._direct_url


def _install(monkeypatch: pytest.MonkeyPatch, direct_url: str | None) -> None:
    def fake_distribution(name: str) -> _FakeDistribution:
        assert name == "glossogen"
        return _FakeDistribution(direct_url=direct_url)

    monkeypatch.setattr(glossogen_build_reader.metadata, "distribution", fake_distribution)


def _git(checkout: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(checkout), *arguments], check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _committed_checkout(root: Path) -> Path:
    """A git repository with one committed file under ``src/``."""
    checkout = root / "checkout"
    (checkout / "src").mkdir(parents=True)
    (checkout / "src" / "module.py").write_text("VALUE = 1\n")
    _git(checkout=checkout, arguments=["init", "--quiet"])
    _git(checkout=checkout, arguments=["add", "src"])
    _git(
        checkout=checkout,
        arguments=[
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "first",
        ],
    )
    return checkout


def _editable_url(checkout: Path) -> str:
    return json.dumps({"url": checkout.as_uri(), "dir_info": {"editable": True}})


async def test_an_install_without_a_direct_url_records_only_the_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch=monkeypatch, direct_url=None)

    assert await read_glossogen_build() == GlossogenBuild(
        version="9.8.7", git_commit=None, has_uncommitted_changes=None
    )


async def test_a_git_install_records_its_commit_as_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    direct_url = json.dumps(
        {
            "url": "https://github.com/example/glossogen.git",
            "vcs_info": {"vcs": "git", "commit_id": "0123abcd", "requested_revision": "v9.8.7"},
        }
    )
    _install(monkeypatch=monkeypatch, direct_url=direct_url)

    assert await read_glossogen_build() == GlossogenBuild(
        version="9.8.7", git_commit="0123abcd", has_uncommitted_changes=False
    )


async def test_an_editable_checkout_records_head_and_a_clean_src(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = _committed_checkout(root=tmp_path)
    _install(monkeypatch=monkeypatch, direct_url=_editable_url(checkout=checkout))

    build = await read_glossogen_build()

    assert build.git_commit == _git(checkout=checkout, arguments=["rev-parse", "HEAD"])
    assert build.has_uncommitted_changes is False


async def test_an_untracked_file_under_src_counts_as_an_uncommitted_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = _committed_checkout(root=tmp_path)
    (checkout / "src" / "new_module.py").write_text("VALUE = 2\n")
    _install(monkeypatch=monkeypatch, direct_url=_editable_url(checkout=checkout))

    assert (await read_glossogen_build()).has_uncommitted_changes is True


async def test_a_change_outside_src_is_not_counted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = _committed_checkout(root=tmp_path)
    (checkout / "notes.txt").write_text("scratch\n")
    _install(monkeypatch=monkeypatch, direct_url=_editable_url(checkout=checkout))

    assert (await read_glossogen_build()).has_uncommitted_changes is False


async def test_an_editable_folder_without_git_records_no_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch=monkeypatch, direct_url=_editable_url(checkout=tmp_path))

    assert await read_glossogen_build() == GlossogenBuild(
        version="9.8.7", git_commit=None, has_uncommitted_changes=None
    )


async def test_a_checkout_that_git_cannot_read_records_no_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / ".git").write_text("gitdir: /nowhere\n")
    _install(monkeypatch=monkeypatch, direct_url=_editable_url(checkout=tmp_path))

    assert await read_glossogen_build() == GlossogenBuild(
        version="9.8.7", git_commit=None, has_uncommitted_changes=None
    )
    assert "git rev-parse HEAD failed" in caplog.text


async def test_a_checkout_without_git_installed_records_no_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    checkout = _committed_checkout(root=tmp_path)
    _install(monkeypatch=monkeypatch, direct_url=_editable_url(checkout=checkout))
    empty_bin = tmp_path / "empty_bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    assert await read_glossogen_build() == GlossogenBuild(
        version="9.8.7", git_commit=None, has_uncommitted_changes=None
    )
    assert "git is not installed" in caplog.text


async def test_a_direct_url_that_does_not_parse_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch=monkeypatch, direct_url=json.dumps({"dir_info": {}}))

    with pytest.raises(ValidationError):
        await read_glossogen_build()


async def test_the_installed_glossogen_reports_its_own_version() -> None:
    build = await read_glossogen_build()

    assert build.version == metadata.version("glossogen")
