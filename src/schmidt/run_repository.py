"""Git-backed repository for a single simulation run directory.

Each run directory is initialized as a git repository. Meaningful simulation
events (messages, tool results, round advances) trigger commits that capture
the JSONL event log and any filesystem artifacts. Forking a run clones the
repository to a new directory at the target commit, giving the forked run
the correct filesystem state without replayers.

Uses dulwich (pure Python git implementation) for all git operations.
"""

import asyncio
import logging
import time
from io import BytesIO, StringIO
from pathlib import Path
from typing import NamedTuple

import dulwich.porcelain as git

logger = logging.getLogger(__name__)

_GITIGNORE_CONTENT = """\
stream.json
*_stdout.log
*_debug.jsonl
__pycache__/
*.pyc
"""


class GitCommitInfo(NamedTuple):
    """Metadata for a single git commit."""

    sha: str
    message: str


class RunRepository:
    """Async wrapper around dulwich git operations for a run directory.

    All operations are offloaded to a thread via ``asyncio.to_thread``
    to avoid blocking the event loop.
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    @property
    def run_dir(self) -> Path:
        """The root directory of this git repository."""
        return self._run_dir

    async def init(self) -> None:
        """Initialize a new git repository and create the initial .gitignore."""
        await asyncio.to_thread(self._init_sync)
        logger.info("Initialized git repository at %s", self._run_dir)

    def _init_sync(self) -> None:
        self._run_dir.mkdir(parents=True, exist_ok=True)
        git.init(path=str(self._run_dir))
        gitignore_path = self._run_dir / ".gitignore"
        gitignore_path.write_text(_GITIGNORE_CONTENT)
        git.add(repo=str(self._run_dir), paths=[".gitignore"])
        git.commit(
            repo=str(self._run_dir),
            message=b"init: repository created",
            author=b"schmidt <schmidt@simulation>",
            committer=b"schmidt <schmidt@simulation>",
        )

    async def commit(self, message: str, paths: list[Path] | None) -> str:
        """Stage files and create a commit. Returns the commit SHA.

        When ``paths`` is None, stages all tracked and untracked files.
        Otherwise stages only the specified paths.
        """
        sha = await asyncio.to_thread(self._commit_sync, message, paths)
        logger.debug("Committed %s: %.80s", sha[:8], message.split("\n")[0])
        return sha

    def _commit_sync(self, message: str, paths: list[Path] | None) -> str:
        repo_path = str(self._run_dir)

        if paths is None:
            # Stage all tracked, modified, and untracked files
            status = git.status(repo=repo_path)
            all_paths: list[str] = []
            # Staged changes
            for path_set in status.staged.values():
                all_paths.extend(p.decode() for p in path_set)
            # Unstaged changes
            all_paths.extend(p.decode() for p in status.unstaged)
            # Untracked files
            all_paths.extend(status.untracked)
            if not all_paths:
                return self._get_head_sha_sync()
            git.add(repo=repo_path, paths=all_paths)
        else:
            str_paths = [str(p.relative_to(self._run_dir)) for p in paths]
            git.add(repo=repo_path, paths=str_paths)

        sha_bytes = git.commit(
            repo=repo_path,
            message=message.encode(),
            author=b"schmidt <schmidt@simulation>",
            committer=b"schmidt <schmidt@simulation>",
        )
        return sha_bytes.decode()

    async def get_head_sha(self) -> str:
        """Return the SHA of the current HEAD commit."""
        return await asyncio.to_thread(self._get_head_sha_sync)

    def _get_head_sha_sync(self) -> str:
        sha_bytes = git.rev_parse(repo=str(self._run_dir), rev="HEAD")
        return sha_bytes.decode()

    async def clone_to(self, target_dir: Path) -> "RunRepository":
        """Clone this repository to a new directory. Returns a RunRepository for the clone."""
        await asyncio.to_thread(self._clone_to_sync, target_dir)
        logger.info("Cloned %s -> %s", self._run_dir, target_dir)
        return RunRepository(run_dir=target_dir)

    def _clone_to_sync(self, target_dir: Path) -> None:
        git.clone(
            source=str(self._run_dir),
            target=str(target_dir),
            errstream=BytesIO(),
        )

    async def checkout(self, sha: str) -> None:
        """Check out a specific commit, detaching HEAD."""
        await asyncio.to_thread(self._checkout_sync, sha)
        logger.info("Checked out %s in %s", sha[:8], self._run_dir)

    def _checkout_sync(self, sha: str) -> None:
        git.checkout(
            repo=str(self._run_dir),
            target=sha.encode(),
            force=True,
        )

    async def find_commit_for_message(self, message_id: str) -> str | None:
        """Search commit messages for a message_id and return the commit SHA."""
        return await asyncio.to_thread(self._find_commit_for_message_sync, message_id)

    def _find_commit_for_message_sync(self, message_id: str) -> str | None:
        search = f"message_id: {message_id}"
        commits = _parse_dulwich_log(
            repo_path=str(self._run_dir),
            max_entries=None,
        )
        for sha, message in commits:
            if search in message:
                return sha
        return None

    async def find_commit_for_event_id(self, event_id: str) -> str | None:
        """Search commit messages for an event_id and return the commit SHA.

        Every committable event's commit message embeds an ``event_id:``
        line, so this works for any event type (round_advanced, round_ended,
        injection_delivered, message_sent, etc.).
        """
        return await asyncio.to_thread(self._find_commit_for_event_id_sync, event_id)

    def _find_commit_for_event_id_sync(self, event_id: str) -> str | None:
        search = f"event_id: {event_id}"
        commits = _parse_dulwich_log(
            repo_path=str(self._run_dir),
            max_entries=None,
        )
        for sha, message in commits:
            if search in message:
                return sha
        return None

    async def log(self, max_count: int) -> list[GitCommitInfo]:
        """Return recent commits as a list of ``GitCommitInfo``."""
        return await asyncio.to_thread(self._log_sync, max_count)

    def _log_sync(self, max_count: int) -> list[GitCommitInfo]:
        raw = _parse_dulwich_log(
            repo_path=str(self._run_dir),
            max_entries=max_count,
        )
        return [GitCommitInfo(sha=sha, message=msg) for sha, msg in raw]


def _parse_dulwich_log(
    repo_path: str,
    max_entries: int | None,
) -> list[tuple[str, str]]:
    """Parse dulwich log output into (sha, full_message) pairs.

    Dulwich outputs commits separated by dashed lines, with ``commit: {sha}``
    headers and unindented message bodies.
    """
    buf = StringIO()
    git.log(repo=repo_path, outstream=buf, max_entries=max_entries)

    results: list[tuple[str, str]] = []
    current_sha: str | None = None
    message_lines: list[str] = []
    in_header = True

    for line in buf.getvalue().splitlines():
        if line.startswith("---"):
            if current_sha is not None:
                results.append((current_sha, "\n".join(message_lines).strip()))
            current_sha = None
            message_lines = []
            in_header = True
            continue

        if line.startswith("commit: "):
            current_sha = line.split()[1]
            continue

        if line.startswith("Author:") or line.startswith("Date:"):
            continue

        if in_header and line == "":
            in_header = False
            continue

        if not in_header:
            message_lines.append(line)

    if current_sha is not None:
        results.append((current_sha, "\n".join(message_lines).strip()))

    return results


def claim_run_dir(runs_dir: Path, scenario_name: str) -> Path:
    """Atomically claim a unique run directory using the current unix timestamp.

    Creates ``{runs_dir}/{scenario_name}/{unix_timestamp}/``. If the directory
    already exists (another run started in the same second), appends ``_2``,
    ``_3``, etc. until a free slot is found. Uses ``mkdir(exist_ok=False)`` for
    atomic collision detection on POSIX filesystems.
    """
    base_dir = runs_dir / scenario_name
    unix_ts = str(int(time.time()))

    candidate = base_dir / unix_ts
    try:
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate
    except FileExistsError:
        pass

    suffix = 2
    while True:
        candidate = base_dir / f"{unix_ts}_{suffix}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            suffix += 1
