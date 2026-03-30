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
