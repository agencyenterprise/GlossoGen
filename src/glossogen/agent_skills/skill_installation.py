"""Copying the skills that glossogen ships into a project's skills folder."""

import shutil
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path

_SKILL_FILE_NAME = "SKILL.md"


class SkillAlreadyInstalled(RuntimeError):
    """The target folder already holds a skill of the same name."""


def shipped_skill_names() -> list[str]:
    """The names of the skills that this glossogen ships, sorted."""
    return sorted(skill.name for skill in _shipped_skill_folders())


def install_skills(target_dir: Path, replace: bool) -> list[Path]:
    """Copy every shipped skill into ``target_dir/<skill name>/`` and return those folders.

    Raises ``SkillAlreadyInstalled`` when a skill's folder already exists and
    ``replace`` is False, before anything is copied. With ``replace``, the existing
    folder, or a symbolic link in its place, is removed first.
    """
    skills = _shipped_skill_folders()
    existing = [
        target_dir / skill.name for skill in skills if _occupied(path=target_dir / skill.name)
    ]
    if existing and not replace:
        names = ", ".join(str(path) for path in existing)
        raise SkillAlreadyInstalled(
            f"{names} already exists. Pass --replace to overwrite it with this glossogen's copy."
        )
    installed: list[Path] = []
    for skill in skills:
        destination = target_dir / skill.name
        _remove(path=destination)
        _copy_tree(source=skill, destination=destination)
        installed.append(destination)
    return installed


def _shipped_skill_folders() -> list[Traversable]:
    """The folders in this package that hold a ``SKILL.md``."""
    package = resources.files(__package__)
    return [
        entry
        for entry in package.iterdir()
        if entry.is_dir() and entry.joinpath(_SKILL_FILE_NAME).is_file()
    ]


def _occupied(path: Path) -> bool:
    """Whether ``path`` exists, counting a symbolic link whose target is gone."""
    return path.exists() or path.is_symlink()


def _remove(path: Path) -> None:
    """Remove a folder or a symbolic link at ``path``; nothing when the path is free."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_tree(source: Traversable, destination: Path) -> None:
    """Copy the files under ``source`` to ``destination``, skipping Python caches."""
    destination.mkdir(parents=True)
    for entry in source.iterdir():
        if entry.name == "__pycache__":
            continue
        if entry.is_dir():
            _copy_tree(source=entry, destination=destination / entry.name)
        else:
            (destination / entry.name).write_bytes(entry.read_bytes())
