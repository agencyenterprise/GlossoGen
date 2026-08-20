"""Asking every installed metric what it wrote beside its report.

The analysis layer names no metric, and this is what keeps that true once sidecars
are in play: it walks the registry, asks each metric for its keyed observations, and
returns them by metric name. A metric another distribution ships gets read the same
way, because it is in the same registry.

Reading is per run and hits the filesystem once per metric that has a file, so it is
never done unless a query actually groups by a metric key.
"""

import asyncio
import logging
from pathlib import Path

from glossogen.evaluation.metric_core.keyed_observation import KeyedObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_registry import available_metrics

logger = logging.getLogger(__name__)


async def _read_one(
    name: str,
    metric_class: type[Metric],
    run_dir: Path,
) -> list[KeyedObservation]:
    """Read one metric's sidecar, treating any failure as nothing to report."""
    try:
        return await metric_class().read_keyed_observations(run_dir=run_dir)
    except Exception:
        logger.exception("Could not read %s's sidecar in %s", name, run_dir)
        return []


async def read_keyed_observations(run_dir: Path) -> dict[str, list[KeyedObservation]]:
    """Return every installed metric's keyed observations for one run, by metric name.

    Metrics that wrote no sidecar contribute nothing, so the result carries only the
    metrics this run actually has numbers for.
    """
    metrics = available_metrics()
    results = await asyncio.gather(
        *(
            _read_one(name=name, metric_class=metric_class, run_dir=run_dir)
            for name, metric_class in metrics.items()
        )
    )
    return {
        name: observations
        for name, observations in zip(metrics, results, strict=True)
        if observations
    }
