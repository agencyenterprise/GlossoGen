"""Sandboxed file workspace for buyer tests, seller code, and deliverables.

Manages per-team directories, validates filenames against path traversal,
and executes Python files in a subprocess with a timeout.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT_SECONDS = 30
ALLOWED_EXTENSION = ".py"


def _validate_filename(filename: str) -> None:
    """Reject filenames that attempt path traversal or use non-.py extensions."""
    if not filename.endswith(ALLOWED_EXTENSION):
        raise ValueError(f"Only .py files are allowed, got: {filename}")
    path = Path(filename)
    if path.is_absolute():
        raise ValueError(f"Absolute paths are not allowed: {filename}")
    if ".." in path.parts:
        raise ValueError(f"Path traversal is not allowed: {filename}")


class WorkspaceManager:
    """Manages sandboxed file workspaces for the procurement scenario.

    Directory layout under ``run_dir``:
    - ``workspaces/{team_id}/`` — engineer scratch space per team
    - ``deliverables/{team_id}/`` — submitted deliverables per team
    - ``buyer_tests/`` — buyer's private test files
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self._workspaces_dir = run_dir / "workspaces"
        self._deliverables_dir = run_dir / "deliverables"
        self._buyer_tests_dir = run_dir / "buyer_tests"

    def create_directories(self, team_ids: list[str]) -> None:
        """Create workspace, deliverable, and buyer_tests directories."""
        self._buyer_tests_dir.mkdir(parents=True, exist_ok=True)
        for tid in team_ids:
            (self._workspaces_dir / tid).mkdir(parents=True, exist_ok=True)
            (self._deliverables_dir / tid).mkdir(parents=True, exist_ok=True)

    # --- Engineer workspace operations ---

    async def write_file(self, team_id: str, filename: str, content: str) -> str:
        """Write a Python file to the team's workspace."""
        _validate_filename(filename=filename)
        path = self._workspaces_dir / team_id / filename
        path.write_text(content)
        return f"Written {filename} ({len(content)} chars)"

    async def read_file(self, team_id: str, filename: str) -> str:
        """Read a file from the team's workspace."""
        _validate_filename(filename=filename)
        path = self._workspaces_dir / team_id / filename
        if not path.exists():
            return f"File not found: {filename}"
        return path.read_text()

    async def list_files(self, team_id: str) -> str:
        """List Python files in the team's workspace."""
        workspace = self._workspaces_dir / team_id
        files = sorted(p.name for p in workspace.glob("*.py"))
        if not files:
            return "No files in workspace."
        return "\n".join(files)

    async def execute_file(self, team_id: str, filename: str) -> str:
        """Run a Python file in the team's workspace with a timeout."""
        _validate_filename(filename=filename)
        workspace = self._workspaces_dir / team_id
        filepath = workspace / filename
        if not filepath.exists():
            return f"File not found: {filename}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "python",
                str(filepath),
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception:
            logger.exception("Error launching subprocess for %s", filename)
            return f"Execution error for {filename}"

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=EXECUTION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS}s"

        output_parts: list[str] = []
        if stdout:
            output_parts.append(f"STDOUT:\n{stdout.decode(errors='replace')}")
        if stderr:
            output_parts.append(f"STDERR:\n{stderr.decode(errors='replace')}")
        if not output_parts:
            return f"Execution completed (exit code {proc.returncode}), no output."

        result = "\n".join(output_parts)
        return f"Exit code {proc.returncode}\n{result}"

    async def submit_deliverable(self, team_id: str, filename: str) -> str:
        """Copy a file from the workspace to the deliverables directory."""
        _validate_filename(filename=filename)
        src = self._workspaces_dir / team_id / filename
        if not src.exists():
            return f"File not found in workspace: {filename}"

        dst = self._deliverables_dir / team_id / filename
        shutil.copy2(str(src), str(dst))
        return f"Deliverable submitted: {filename}"

    # --- Buyer test operations ---

    async def write_buyer_test(self, filename: str, content: str) -> str:
        """Write a pytest file to the buyer's private test directory."""
        _validate_filename(filename=filename)
        path = self._buyer_tests_dir / filename
        path.write_text(content)
        return f"Test file written: {filename} ({len(content)} chars)"

    async def run_buyer_tests(self, team_id: str) -> str:
        """Run the buyer's pytest tests against a team's submitted deliverables.

        Copies deliverables and test files to a temp directory, runs pytest,
        and returns the output.
        """
        deliverable_dir = self._deliverables_dir / team_id
        deliverable_files = list(deliverable_dir.glob("*.py"))
        if not deliverable_files:
            return f"Team {team_id} has no submitted deliverables."

        test_files = list(self._buyer_tests_dir.glob("*.py"))
        if not test_files:
            return "No test files found. Use write_test to create tests first."

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for f in deliverable_files:
                shutil.copy2(str(f), str(tmp / f.name))
            for f in test_files:
                shutil.copy2(str(f), str(tmp / f.name))

            try:
                proc = await asyncio.create_subprocess_exec(
                    "python",
                    "-m",
                    "pytest",
                    "-v",
                    "--tb=short",
                    str(tmp),
                    cwd=str(tmp),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except Exception:
                logger.exception("Error launching pytest for %s", team_id)
                return f"Error running tests against {team_id}"

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=EXECUTION_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                proc.kill()
                return f"Test execution timed out after {EXECUTION_TIMEOUT_SECONDS}s"

            output_parts: list[str] = []
            if stdout:
                output_parts.append(stdout.decode(errors="replace"))
            if stderr:
                output_parts.append(stderr.decode(errors="replace"))
            if not output_parts:
                return f"Tests completed (exit code {proc.returncode}), no output."

            return "\n".join(output_parts)
