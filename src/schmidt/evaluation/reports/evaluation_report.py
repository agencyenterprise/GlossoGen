"""Data model for representing the outcome of scenario evaluations
and report serialization.
"""

import hashlib
import logging
from pathlib import Path

import aiofiles
import orjson
from pydantic import BaseModel

from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.reports.evaluation_cost import (
    EvaluationCost,
    EvaluationTokenUsage,
    compute_evaluation_cost,
)

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
    attempted_metric_names: set[str],
) -> list[Measurement]:
    """Combine prior and new measurements, dropping stale entries for re-attempted metrics.

    A metric whose name appears in ``attempted_metric_names`` had its
    ``compute()`` called this invocation. The new list contains its
    output: zero or more Measurements. After the merge, the report
    reflects the latest verdict for every attempted metric:

    * Existing measurements whose metric_name was attempted are removed
      (the new result — empty or otherwise — replaces them). This is how
      a "doesn't apply" re-run clears a stale zero-score sentinel from a
      prior invocation that ran under different code or against
      different data.
    * Existing measurements whose metric_name was NOT attempted are
      preserved, so partial re-runs do not wipe unrelated results.
    * The new list may contain metric_names not in
      ``attempted_metric_names`` — a base metric like ``round_success``
      emits ``round_success_team_a`` / ``round_success_team_b``, and
      ``dialog_retransmission`` emits ``dialog_count`` /
      ``retransmission_request_count``. Existing measurements sharing any
      of those emitted names are also dropped, so re-running such a metric
      replaces its prior output instead of stacking duplicate copies.
    """
    stale_names = attempted_metric_names | {m.metric_name for m in new}
    preserved = [m for m in existing if m.metric_name not in stale_names]
    return preserved + new


def merge_evaluation_costs(
    existing: EvaluationCost | None,
    new: EvaluationCost,
) -> EvaluationCost:
    """Sum token usage across two eval invocations when the model matches.

    Returns ``new`` unchanged when ``existing`` is ``None`` or when the
    ``(model, provider_name)`` pair differs (a mid-stream judge swap
    invalidates the cumulative cost; resetting to the new invocation's
    cost is the safer default). When the model matches, sums usage
    field-by-field and recomputes the dollar cost so the report's
    ``evaluation_cost`` reflects the lifetime spend rather than just the
    most recent invocation.
    """
    if existing is None:
        return new
    if existing.model != new.model or existing.provider_name != new.provider_name:
        logger.info(
            "Evaluation judge changed (%s/%s → %s/%s); resetting cumulative cost",
            existing.model,
            existing.provider_name,
            new.model,
            new.provider_name,
        )
        return new
    summed = EvaluationTokenUsage(
        input_tokens=existing.usage.input_tokens + new.usage.input_tokens,
        output_tokens=existing.usage.output_tokens + new.usage.output_tokens,
        cache_read_input_tokens=(
            existing.usage.cache_read_input_tokens + new.usage.cache_read_input_tokens
        ),
        cache_creation_input_tokens=(
            existing.usage.cache_creation_input_tokens + new.usage.cache_creation_input_tokens
        ),
    )
    return compute_evaluation_cost(
        usage=summed,
        model=new.model,
        provider_name=new.provider_name,
    )


def compute_measurements_hash(measurements: list[Measurement]) -> str:
    """Return a stable 32-char hex digest of an evaluation report's measurements.

    Serializes the measurements list as canonical JSON (sorted keys, list
    order preserved) and hashes with blake2b, so a byte-identical report
    always maps to the same digest. Excludes ``evaluation_cost`` because
    that field changes on every re-eval (token usage, dollar cost) even
    when the measurements are semantically unchanged — the hash needs to
    survive cost drift to be useful as a drift-detection signal for
    ``schmidt sync-metadata-to-prod``.
    """
    payload = [m.model_dump(mode="json") for m in measurements]
    canonical = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.blake2b(canonical, digest_size=16).hexdigest()
