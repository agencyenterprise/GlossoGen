"""Show every worktree's state relative to the research reference branch.

Answers the questions that go stale fastest when several worktrees are open at
once: which worktree holds uncommitted findings, which branch carries commits the
reference branch has not absorbed, and whether the reference branch is pushed.
"""

import subprocess
import sys
from typing import NamedTuple

REFERENCE_BRANCH = "ncri-covenant"
RESEARCH_PREFIX = "docs/research/"


class WorktreeState(NamedTuple):
    """One worktree's path, branch, and divergence from the reference branch."""

    path: str
    branch: str
    dirty: int
    research_dirty: int
    ahead: int
    behind: int


def git(args, cwd):
    """Run a git command and return stripped stdout, or "" when it fails."""
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False, cwd=cwd
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def repo_root():
    """Return the common repository root for the current worktree."""
    return git(["rev-parse", "--show-toplevel"], cwd=None)


def list_worktrees(root):
    """Parse `git worktree list --porcelain` into (path, branch) pairs."""
    out = git(["worktree", "list", "--porcelain"], cwd=root)
    entries = []
    path = None
    branch = "(detached)"
    for line in out.splitlines():
        if line.startswith("worktree "):
            if path is not None:
                entries.append((path, branch))
            path = line[len("worktree ") :]
            branch = "(detached)"
        elif line.startswith("branch "):
            branch = line[len("branch refs/heads/") :]
    if path is not None:
        entries.append((path, branch))
    return entries


def collect(path, branch, root):
    """Build the WorktreeState for one worktree."""
    porcelain = git(["status", "--porcelain"], cwd=path)
    lines = [ln for ln in porcelain.splitlines() if ln]
    research = [ln for ln in lines if RESEARCH_PREFIX in ln]

    ahead, behind = 0, 0
    if branch != "(detached)":
        counts = git(
            ["rev-list", "--left-right", "--count", f"{REFERENCE_BRANCH}...{branch}"],
            cwd=root,
        )
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    return WorktreeState(
        path=path,
        branch=branch,
        dirty=len(lines),
        research_dirty=len(research),
        ahead=ahead,
        behind=behind,
    )


def reference_is_pushed(root):
    """Report whether the reference branch exists on origin and matches locally."""
    remote = git(["rev-parse", f"origin/{REFERENCE_BRANCH}"], cwd=root)
    local = git(["rev-parse", REFERENCE_BRANCH], cwd=root)
    if not local:
        return "reference branch does not exist locally"
    if not remote:
        return "NOT pushed to origin"
    if remote == local:
        return "in sync with origin"
    unpushed = git(
        ["rev-list", "--count", f"origin/{REFERENCE_BRANCH}..{REFERENCE_BRANCH}"],
        cwd=root,
    )
    return f"{unpushed} commit(s) not pushed to origin"


def main():
    root = repo_root()
    if not root:
        print("not inside a git repository", file=sys.stderr)
        return 1

    worktrees = list_worktrees(root)
    states = [collect(path=p, branch=b, root=root) for p, b in worktrees]

    print(f"reference branch: {REFERENCE_BRANCH} — {reference_is_pushed(root)}")
    print()
    header = f"{'BRANCH':<40} {'AHEAD':>5} {'DIRTY':>5} {'FINDINGS':>8}  PATH"
    print(header)
    print("-" * len(header))

    for state in sorted(states, key=lambda s: (-s.ahead, s.branch)):
        marks = []
        if state.research_dirty:
            marks.append("uncommitted findings")
        if state.ahead:
            marks.append(f"{state.ahead} commit(s) not in reference")
        suffix = ""
        if marks:
            suffix = "   <-- " + "; ".join(marks)
        print(
            f"{state.branch:<40} {state.ahead:>5} {state.dirty:>5} "
            f"{state.research_dirty:>8}  {state.path}{suffix}"
        )

    stragglers = [s for s in states if s.research_dirty or s.ahead]
    print()
    if stragglers:
        print(f"{len(stragglers)} worktree(s) hold work the reference branch lacks.")
    else:
        print("Every worktree is contained in the reference branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
