"""Reading which glossogen build is running, for the run log's ``simulation_started``.

The version comes from the installed distribution. The commit comes from the
install's ``direct_url.json`` (PEP 610): a git install records its commit there,
and an editable install records the checkout folder, whose ``HEAD`` and status are
read with git. When git is not installed or cannot read the checkout, the commit is
recorded as unknown.
"""

import asyncio
import json
import logging
from importlib import metadata
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiofiles.os
from pydantic import BaseModel

from glossogen.models.glossogen_build import GlossogenBuild

logger = logging.getLogger(__name__)

_DISTRIBUTION_NAME = "glossogen"


class _GitUnavailable(RuntimeError):
    """git is not installed, or it failed in a glossogen checkout that has a ``.git`` entry."""


class _VcsInfo(BaseModel):
    """The ``vcs_info`` object of a ``direct_url.json``."""

    commit_id: str


class _DirInfo(BaseModel):
    """The ``dir_info`` object of a ``direct_url.json``; PEP 610 makes ``editable`` optional."""

    editable: bool = False


class _DirectUrl(BaseModel):
    """The parts of a ``direct_url.json`` that name a commit or a checkout.

    PEP 610 gives a direct URL exactly one of ``vcs_info``, ``dir_info`` and
    ``archive_info``, so the other two are absent.
    """

    url: str
    vcs_info: _VcsInfo | None = None
    dir_info: _DirInfo | None = None


class _GitState(BaseModel):
    """A checkout's ``HEAD`` commit and whether ``src/`` differs from it."""

    commit: str
    has_uncommitted_changes: bool


async def read_glossogen_build() -> GlossogenBuild:
    """Return the version and commit of the glossogen that this process runs.

    The commit is None when the install records none, and when the install is an
    editable git checkout that git cannot read, for example because git is not
    installed. Raises a pydantic ``ValidationError`` when the install's
    ``direct_url.json`` does not parse.
    """
    distribution = metadata.distribution(_DISTRIBUTION_NAME)
    version = distribution.version
    raw_direct_url = distribution.read_text("direct_url.json")
    if raw_direct_url is None:
        return _build_without_commit(version=version)
    direct_url = _DirectUrl.model_validate(json.loads(raw_direct_url))
    if direct_url.vcs_info is not None:
        return GlossogenBuild(
            version=version,
            git_commit=direct_url.vcs_info.commit_id,
            has_uncommitted_changes=False,
        )
    if direct_url.dir_info is None or not direct_url.dir_info.editable:
        return _build_without_commit(version=version)
    checkout = _local_path(file_url=direct_url.url)
    if not await aiofiles.os.path.exists(checkout / ".git"):
        return _build_without_commit(version=version)
    git_state = await _read_git_state(checkout=checkout)
    if git_state is None:
        return _build_without_commit(version=version)
    return GlossogenBuild(
        version=version,
        git_commit=git_state.commit,
        has_uncommitted_changes=git_state.has_uncommitted_changes,
    )


def _build_without_commit(version: str) -> GlossogenBuild:
    """A build whose commit is unknown."""
    return GlossogenBuild(version=version, git_commit=None, has_uncommitted_changes=None)


def _local_path(file_url: str) -> Path:
    """The folder that a ``file://`` URL names."""
    return Path(unquote(urlparse(file_url).path))


async def _read_git_state(checkout: Path) -> _GitState | None:
    """Read ``checkout``'s ``HEAD`` and whether ``src/`` has changes, tracked or untracked.

    Returns None, and logs why, when git is not installed or cannot read ``checkout``.
    """
    try:
        commit = await _run_git(checkout=checkout, arguments=["rev-parse", "HEAD"])
        status = await _run_git(
            checkout=checkout,
            arguments=["status", "--porcelain", "--untracked-files=normal", "--", "src"],
        )
    except _GitUnavailable:
        logger.exception("Recording the glossogen commit as unknown")
        return None
    return _GitState(commit=commit, has_uncommitted_changes=status != "")


async def _run_git(checkout: Path, arguments: list[str]) -> str:
    """Run git in ``checkout`` and return its stripped output."""
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(checkout),
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise _GitUnavailable(
            f"git is not installed, so it cannot read the glossogen checkout {checkout}"
        ) from error
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise _GitUnavailable(
            f"git {' '.join(arguments)} failed in the glossogen checkout {checkout}: "
            f"{stderr.decode().strip()}"
        )
    return stdout.decode().strip()
