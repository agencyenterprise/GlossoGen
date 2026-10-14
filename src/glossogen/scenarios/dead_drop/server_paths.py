"""Path normalization, where a path is stored, and the access rules of the shared server.

An agent may write only inside its own home and ``/tmp``. The other user's home
is listed under ``/home`` but nothing below it can be reached. Under
``fs_isolated`` each agent's ``/tmp`` is its own volume, so the same path names a
different file for each agent.
"""

from pathlib import PurePosixPath
from typing import NamedTuple

from glossogen.scenarios.dead_drop.ids import PARTNER_OF, TMP_PATH, home_of

SERVER_VOLUME = "server"
SHARED_TMP_VOLUME = "tmp"


class Location(NamedTuple):
    """A file's volume and its path on that volume."""

    volume: str
    path: str


def normalize_path(path: str) -> str:
    """``path`` made absolute from ``/`` with ``.``, ``..`` and repeated slashes resolved."""
    parts: list[str] = []
    for part in PurePosixPath("/", path).parts[1:]:
        if part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def is_within(path: str, root: str) -> bool:
    """Whether normalized ``path`` is ``root`` or below it."""
    return path == root or path.startswith(root.rstrip("/") + "/")


def is_strictly_within(path: str, root: str) -> bool:
    """Whether normalized ``path`` is below ``root`` and not ``root`` itself."""
    return path != root and is_within(path=path, root=root)


def permission_denied() -> PermissionError:
    """The error a refused access raises.

    Its message is bash's wording, because the interpreter prints the message of an
    error raised while redirecting (``bash: /etc/x: Permission denied``).
    """
    return PermissionError("Permission denied")


class AccessPolicy(NamedTuple):
    """What one agent may do where."""

    agent_id: str
    partner_id: str

    def may_inspect(self, path: str) -> bool:
        """Stat or test for existence: everywhere but below the partner's home."""
        return not is_strictly_within(path=path, root=home_of(agent_id=self.partner_id))

    def may_read(self, path: str) -> bool:
        """Read a file or list a directory: everywhere but the partner's home."""
        return not is_within(path=path, root=home_of(agent_id=self.partner_id))

    def may_read_tree(self, path: str) -> bool:
        """Read ``path`` and everything below it, as a recursive copy does.

        False for a directory holding the partner's home, such as ``/home``.
        """
        if not self.may_read(path=path):
            return False
        return not is_within(path=home_of(agent_id=self.partner_id), root=path)

    def may_write(self, path: str) -> bool:
        """Create, change or remove: only below the agent's own home or ``/tmp``."""
        own_home = home_of(agent_id=self.agent_id)
        return is_strictly_within(path=path, root=own_home) or is_strictly_within(
            path=path, root=TMP_PATH
        )


def partner_can_read(agent_id: str, path: str, fs_isolated: bool) -> bool:
    """Whether the partner of ``agent_id`` can read ``path``, as ``agent_id`` names it.

    Under ``fs_isolated`` a path in ``/tmp`` names a different file for each agent,
    so the partner cannot reach it.
    """
    normalized = normalize_path(path=path)
    if fs_isolated and is_within(path=normalized, root=TMP_PATH):
        return False
    partner_policy = AccessPolicy(agent_id=PARTNER_OF[agent_id], partner_id=agent_id)
    return partner_policy.may_read(path=normalized)


def location_of(agent_id: str, path: str, fs_isolated: bool) -> Location:
    """Where ``path``, as ``agent_id`` names it, is stored."""
    normalized = normalize_path(path=path)
    if not is_within(path=normalized, root=TMP_PATH):
        return Location(volume=SERVER_VOLUME, path=normalized)
    if fs_isolated:
        return Location(volume=f"{SHARED_TMP_VOLUME}:{agent_id}", path=normalized)
    return Location(volume=SHARED_TMP_VOLUME, path=normalized)
