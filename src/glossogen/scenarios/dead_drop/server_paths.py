"""Path normalization and the access rules of the shared server.

An agent may write only inside its own home and ``/tmp``. The other user's home
is listed under ``/home`` but nothing below it can be read, unless the run makes
homes readable, in which case it can be read and still not written.
"""

from pathlib import PurePosixPath
from typing import NamedTuple

from glossogen.scenarios.dead_drop.ids import PARTNER_OF, TMP_PATH, home_of


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
    home_dirs_readable: bool

    def may_inspect(self, path: str) -> bool:
        """Stat or test for existence: everywhere but below an unreadable partner home."""
        if self.home_dirs_readable:
            return True
        return not is_strictly_within(path=path, root=home_of(agent_id=self.partner_id))

    def may_read(self, path: str) -> bool:
        """Read a file or list a directory."""
        if self.home_dirs_readable:
            return True
        return not is_within(path=path, root=home_of(agent_id=self.partner_id))

    def may_read_tree(self, path: str) -> bool:
        """Read ``path`` and everything below it, as a recursive copy does.

        False for a directory holding the partner's home, such as ``/home``, when
        that home is not readable.
        """
        if not self.may_read(path=path):
            return False
        if self.home_dirs_readable:
            return True
        return not is_within(path=home_of(agent_id=self.partner_id), root=path)

    def may_write(self, path: str) -> bool:
        """Create, change or remove: only below the agent's own home or ``/tmp``."""
        own_home = home_of(agent_id=self.agent_id)
        return is_strictly_within(path=path, root=own_home) or is_strictly_within(
            path=path, root=TMP_PATH
        )


def partner_can_read(agent_id: str, path: str, fs_isolated: bool, home_dirs_readable: bool) -> bool:
    """Whether the partner of ``agent_id`` can read ``path``, as ``agent_id`` names it.

    Under ``fs_isolated`` a path in ``/tmp`` names a different file for each agent,
    so the partner cannot reach it.
    """
    normalized = normalize_path(path=path)
    if fs_isolated and is_within(path=normalized, root=TMP_PATH):
        return False
    partner_id = PARTNER_OF[agent_id]
    partner_policy = AccessPolicy(
        agent_id=partner_id, partner_id=agent_id, home_dirs_readable=home_dirs_readable
    )
    return partner_policy.may_read(path=normalized)
