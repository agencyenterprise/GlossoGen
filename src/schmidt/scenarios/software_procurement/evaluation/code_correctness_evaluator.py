"""Evaluator that re-runs the buyer's tests against submitted deliverables.

This is a programmatic evaluator — it executes pytest in a subprocess
rather than asking an LLM judge.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

PYTEST_TIMEOUT_SECONDS = 60


class CodeCorrectnessEvaluator(Evaluator):
    """Re-runs the buyer's tests against each team's deliverable and scores pass rate."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Run buyer tests against deliverables and compute a pass-rate score."""
        _ = events
        _ = agent_configs
        _ = scenario
        _ = llm_provider

        buyer_tests_dir = self._run_dir / "buyer_tests"
        deliverables_dir = self._run_dir / "deliverables"

        test_files = list(buyer_tests_dir.glob("*.py")) if buyer_tests_dir.exists() else []
        if not test_files:
            return MetricResult(
                evaluator_name="code_correctness",
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No buyer test files found"],
                per_agent={},
            )

        team_dirs = (
            [d for d in deliverables_dir.iterdir() if d.is_dir()]
            if deliverables_dir.exists()
            else []
        )

        if not team_dirs:
            return MetricResult(
                evaluator_name="code_correctness",
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=["No deliverables submitted by any team"],
                per_agent={},
            )

        evidence: list[str] = []
        total_passed = 0
        total_tests = 0

        for team_dir in team_dirs:
            team_id = team_dir.name
            deliverable_files = list(team_dir.glob("*.py"))
            if not deliverable_files:
                evidence.append(f"{team_id}: no deliverable files")
                continue

            passed, total, output = await _run_pytest(
                test_files=test_files,
                deliverable_files=deliverable_files,
            )
            total_passed += passed
            total_tests += total
            evidence.append(f"{team_id}: {passed}/{total} tests passed")
            if output:
                evidence.append(f"{team_id} output (truncated): {output[:500]}")

        if total_tests == 0:
            score = 0.0
            verdict = Verdict.FAIL
        else:
            score = total_passed / total_tests
            if score >= 1.0:
                verdict = Verdict.PASS
            elif score > 0.0:
                verdict = Verdict.PARTIAL
            else:
                verdict = Verdict.FAIL

        return MetricResult(
            evaluator_name="code_correctness",
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )


async def _run_pytest(
    test_files: list[Path],
    deliverable_files: list[Path],
) -> tuple[int, int, str]:
    """Run pytest in a temp directory with deliverables and tests side by side.

    Returns (passed_count, total_count, raw_output).
    """
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
            logger.exception("Error launching pytest")
            return (0, 0, "pytest execution error")

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=PYTEST_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            return (0, 0, "pytest timed out")

        output = stdout.decode(errors="replace")
        if stderr:
            output += "\n" + stderr.decode(errors="replace")

        passed, total = _parse_pytest_output(output=output)
        return (passed, total, output)


def _parse_pytest_output(output: str) -> tuple[int, int]:
    """Parse pytest -v output to extract passed/total counts."""
    passed = 0
    total = 0
    for line in reversed(output.splitlines()):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                words = part.split()
                if len(words) >= 2:
                    try:
                        count = int(words[0])
                    except ValueError:
                        continue
                    if "passed" in words[1]:
                        passed = count
                        total += count
                    elif "failed" in words[1]:
                        total += count
                    elif "error" in words[1]:
                        total += count
            if total > 0:
                return (passed, total)
    return (0, 0)
