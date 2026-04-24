"""Data models for representing the outcome of scenario evaluations
and report serialization.
"""

import logging
from enum import Enum
from pathlib import Path

import aiofiles
import orjson
from pydantic import BaseModel

from schmidt.evaluation.evaluation_cost import EvaluationCost

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    """Three-valued outcome for a single evaluation metric."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class MetricResult(BaseModel):
    """Result of a single evaluator applied to a simulation run.

    Attributes:
        evaluator_name: Identifier of the evaluator that produced this result.
        verdict: Pass, fail, or partial outcome.
        score: Numeric score assigned by the evaluator.
        evidence: Supporting text fragments that justify the verdict.
        per_agent: Mapping of agent identifiers to their individual verdict.
        rounds_identified: Round numbers this metric flagged. Semantics depend on the
            evaluator (e.g. rounds where an anomaly was observed, rounds that were won).
            Empty when the evaluator has nothing to report at the round level.
    """

    evaluator_name: str
    verdict: Verdict
    score: float
    evidence: list[str]
    per_agent: dict[str, Verdict]
    rounds_identified: list[int]


class EvaluationReport(BaseModel):
    """Aggregated evaluation output for a single simulation run.

    Attributes:
        simulation_id: Unique identifier of the simulation that was evaluated.
        scenario_name: Name of the scenario that was simulated.
        metrics: Collection of individual metric results from all evaluators.
        evaluation_cost: Token usage and estimated dollar cost for the evaluation.
    """

    simulation_id: str
    scenario_name: str
    metrics: list[MetricResult]
    evaluation_cost: EvaluationCost


async def write_report(report: EvaluationReport, report_path: Path) -> None:
    """Serialize an evaluation report to JSON and write it to disk."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(report_path, mode="wb") as f:
        await f.write(orjson.dumps(report.model_dump(mode="json"), option=orjson.OPT_INDENT_2))
    logger.info("Evaluation report written to %s", report_path)


async def load_report(report_path: Path) -> EvaluationReport | None:
    """Load an existing evaluation report, or return None if the file does not exist."""
    if not report_path.exists():
        return None
    async with aiofiles.open(report_path, mode="rb") as f:
        raw = await f.read()
    return EvaluationReport.model_validate(orjson.loads(raw))


def merge_metrics(
    existing: list[MetricResult],
    new: list[MetricResult],
) -> list[MetricResult]:
    """Combine prior and new metric results, letting new entries replace existing ones by name.

    The merge preserves any existing metric whose evaluator_name is not present in the new
    list, so partial re-runs do not wipe unrelated results.
    """
    new_names = {metric.evaluator_name for metric in new}
    preserved = [metric for metric in existing if metric.evaluator_name not in new_names]
    return preserved + new
