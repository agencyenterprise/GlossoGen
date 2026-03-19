"""Shared helper for running evaluators against a simulation log and writing a report."""

import logging
from pathlib import Path

from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import EvaluatorFactory
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


async def run_evaluators(
    scenario: SimulationScenario,
    log_path: Path,
    evaluator_names: list[str],
    report_path: Path,
    model: str,
    evaluator_registry: dict[str, EvaluatorFactory],
) -> EvaluationReport:
    """Run the named evaluators against a JSONL log and write the report.

    Looks up each evaluator name in the provided registry, runs it, collects
    results, and writes a JSON report to ``report_path``.
    """
    logger.info(
        "Running %d evaluator(s) against %s (model: %s)",
        len(evaluator_names),
        log_path,
        model,
    )
    events = await load_events(log_path=log_path)
    logger.info("Loaded %d events from %s", len(events), log_path)
    agent_configs = extract_agent_configs(events=events)
    simulation_id = extract_simulation_id(events=events)
    provider = ClaudeProvider(model=model)

    metrics: list[MetricResult] = []
    for eval_name in evaluator_names:
        if eval_name not in evaluator_registry:
            available = ", ".join(sorted(evaluator_registry.keys()))
            raise ValueError(f"Unknown evaluator: '{eval_name}'. Available: {available}")
        evaluator = evaluator_registry[eval_name]()
        logger.info("Running evaluator: %s", eval_name)
        result = await evaluator.evaluate(
            events=events,
            agent_configs=agent_configs,
            scenario=scenario,
            llm_provider=provider,
        )
        logger.info(
            "Evaluator %s finished: verdict=%s, score=%.2f",
            eval_name,
            result.verdict,
            result.score,
        )
        metrics.append(result)

    report = EvaluationReport(
        simulation_id=simulation_id,
        scenario_name=scenario.name(),
        metrics=metrics,
    )
    await write_report(report=report, report_path=report_path)
    logger.info("Evaluation report written to %s", report_path)
    return report
