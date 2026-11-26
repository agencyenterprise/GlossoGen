"""``GlossogenBuild``, the glossogen code that a run's log records it was written by."""

from pydantic import BaseModel


class GlossogenBuild(BaseModel):
    """The installed glossogen that wrote a run's log.

    ``version`` is the installed distribution's version. ``git_commit`` is the commit
    that the install came from: the commit that a git install recorded, or the
    checkout's ``HEAD`` for an editable install. It is None for an install that
    records no commit, such as one built from a wheel or a source folder.

    ``has_uncommitted_changes`` says whether an editable checkout held changes under
    ``src/`` that ``git_commit`` does not contain, tracked or untracked. It is False
    for a git install, which builds from a clean clone, and None when no commit is
    known.
    """

    version: str
    git_commit: str | None
    has_uncommitted_changes: bool | None
