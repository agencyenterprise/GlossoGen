"""Data model for representing the outcome of scenario evaluations
and report serialization.
"""

import logging
from pathlib import Path

import aiofiles
import orjson
from pydantic import BaseModel

from schmidt.evaluation.evaluation_cost import EvaluationCost
from schmidt.evaluation.measurement import Measurement

logger = logging.getLogger(__name__)


class EvaluationReport(BaseModel):
    """Aggregated evaluation output for a single simulation run.

    Attributes:
        simulation_id: Unique identifier of the simulation that was evaluated.
        scenario_name: Name of the scenario that was simulated.
        measurements: Collection of measurements produced by all metrics.
        evaluation_cost: Token usage and estimated dollar cost for the evaluation.
    """

    simulation_id: str
    scenario_name: str
    measurements: list[Measurement]
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


def merge_measurements(
    existing: list[Measurement],
    new: list[Measurement],
) -> list[Measurement]:
    """Combine prior and new measurements, letting new entries replace existing ones by name.

    The merge preserves any existing measurement whose metric_name is not
    present in the new list, so partial re-runs do not wipe unrelated results.
    """
    new_names = {m.metric_name for m in new}
    preserved = [m for m in existing if m.metric_name not in new_names]
    return preserved + new
