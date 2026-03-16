"""Data models for representing the outcome of scenario evaluations,
and shared verdict-parsing utilities used by all evaluators."""

from enum import Enum

from pydantic import BaseModel


class Verdict(str, Enum):
    """Three-valued outcome for a single evaluation metric."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


def parse_verdict_line(line: str) -> tuple[Verdict, float]:
    """Parse a single uppercased verdict line into a Verdict and numeric score.

    Returns PARTIAL with score 0.5 when the line is empty or does not
    contain a recognized verdict keyword. Checks FAIL before PASS
    to avoid matching the substring "PASS" inside "PARTIAL".
    """
    if not line:
        return Verdict.PARTIAL, 0.5
    if "FAIL" in line:
        return Verdict.FAIL, 0.0
    if "PARTIAL" in line:
        return Verdict.PARTIAL, 0.5
    if "PASS" in line:
        return Verdict.PASS, 1.0
    return Verdict.PARTIAL, 0.5


def parse_verdict_from_response(response_text: str | None) -> tuple[Verdict, float]:
    """Extract a verdict from the first line of an LLM judge response.

    Uppercases the first line and delegates to ``parse_verdict_line``.
    Returns PARTIAL with score 0.5 when the response is None or empty.
    """
    if response_text is None:
        return Verdict.PARTIAL, 0.5
    first_line = response_text.strip().split("\n")[0].strip().upper()
    return parse_verdict_line(line=first_line)


class MetricResult(BaseModel):
    """Result of a single evaluator applied to a simulation run.

    Attributes:
        evaluator_name: Identifier of the evaluator that produced this result.
        verdict: Pass, fail, or partial outcome.
        score: Numeric score assigned by the evaluator.
        evidence: Supporting text fragments that justify the verdict.
        per_agent: Mapping of agent identifiers to their individual verdict.
    """

    evaluator_name: str
    verdict: Verdict
    score: float
    evidence: list[str]
    per_agent: dict[str, Verdict]


class EvaluationReport(BaseModel):
    """Aggregated evaluation output for a single simulation run.

    Attributes:
        simulation_id: Unique identifier of the simulation that was evaluated.
        scenario_name: Name of the scenario that was simulated.
        metrics: Collection of individual metric results from all evaluators.
    """

    simulation_id: str
    scenario_name: str
    metrics: list[MetricResult]
