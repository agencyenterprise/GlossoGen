"""Runs a scenario's configured metrics against a simulation log and writes the report.

This is platform logic that operates on a :class:`SimulationScenario` rather than
scenario-specific behaviour: it loads the JSONL event log, resolves the requested
metric names against the generic metric registry, runs each metric, and merges the
results (and provider cost) into the on-disk evaluation report.
"""

import logging
from pathlib import Path

from glossogen.evaluation.log_reader import (
    extract_agent_configs,
    extract_simulation_id,
    load_events,
)
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_registry import GENERIC_METRIC_REGISTRY
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.reports.evaluation_cost import compute_evaluation_cost
from glossogen.evaluation.reports.evaluation_report import (
    EvaluationReport,
    load_report,
    merge_evaluation_costs,
    merge_measurements,
    write_report,
)
from glossogen.llm.provider_factory import create_provider
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


async def run_scenario_evaluation(
    scenario: SimulationScenario,
    log_path: Path,
    metric_names: list[str],
    report_path: Path,
    model: str,
    provider_name: str,
    inference_provider: str | None,
    reasoning_effort: str | None,
    options: MetricRunOptions,
) -> EvaluationReport:
    """Run the requested metrics against a simulation log and write the report."""
    events = await load_events(log_path=log_path)
    agent_configs = extract_agent_configs(events=events)
    simulation_id = extract_simulation_id(events=events)
    provider = create_provider(
        provider_name=provider_name,
        model=model,
        inference_provider=inference_provider,
        reasoning_effort=reasoning_effort,
    )

    registry: dict[str, type[Metric]] = dict(GENERIC_METRIC_REGISTRY)
    for metric_name in metric_names:
        if metric_name not in registry:
            available = ", ".join(sorted(registry.keys()))
            raise ValueError(f"Unknown metric: '{metric_name}'. Available: {available}")

    new_measurements: list[Measurement] = []
    failed_metrics: list[str] = []
    for metric_name in metric_names:
        metric = registry[metric_name]()
        logger.info("Running metric: %s", metric_name)
        try:
            measurements = await metric.compute(
                events=events,
                agent_configs=agent_configs,
                scenario=scenario,
                llm_provider=provider,
                run_dir=log_path.parent,
                options=options,
            )
        except Exception:
            logger.exception("Metric %s failed; continuing with remaining metrics", metric_name)
            failed_metrics.append(metric_name)
            continue
        for measurement in measurements:
            logger.info(
                "Metric %s finished: %s score=%.3f (%s)",
                metric_name,
                measurement.metric_name,
                measurement.score,
                measurement.score_unit,
            )
        new_measurements.extend(measurements)
    if failed_metrics:
        logger.warning(
            "Evaluation completed with %d failed metric(s): %s",
            len(failed_metrics),
            ", ".join(failed_metrics),
        )

    invocation_cost = compute_evaluation_cost(
        usage=provider.get_accumulated_usage(),
        model=model,
        provider_name=provider_name,
    )

    attempted_metric_names = set(metric_names)
    existing_report = await load_report(report_path=report_path)
    if existing_report is None:
        merged = new_measurements
        cumulative_cost = invocation_cost
    else:
        merged = merge_measurements(
            existing=existing_report.measurements,
            new=new_measurements,
            attempted_metric_names=attempted_metric_names,
        )
        cumulative_cost = merge_evaluation_costs(
            existing=existing_report.evaluation_cost,
            new=invocation_cost,
        )
    report = EvaluationReport(
        simulation_id=simulation_id,
        scenario_name=scenario.name(),
        measurements=merged,
        evaluation_cost=cumulative_cost,
    )
    await write_report(report=report, report_path=report_path)
    return report
