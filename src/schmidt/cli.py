"""Command-line interface for the schmidt simulation runner.

Defines the ``schmidt`` CLI with two subcommands:

* ``run``      -- load and execute a simulation scenario
* ``evaluate`` -- score a previously-generated simulation log
"""

import argparse
import asyncio
import logging
from pathlib import Path

from schmidt.evaluation.evaluator_runner import run_evaluation
from schmidt.event_logger import EventLogger
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.scenario_loader import load_scenario
from schmidt.simulation_hub import SimulationHub
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def main() -> None:
    """Parse CLI arguments and dispatch to the ``run`` or ``evaluate`` subcommand."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(prog="schmidt")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    run_parser.add_argument("scenario_name", type=str, help="Name of the scenario to run")
    run_parser.add_argument("--log-dir", type=str, required=True, help="Directory for JSONL logs")
    run_parser.add_argument("--model", type=str, required=True, help="Claude model to use")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a simulation log")
    evaluate_parser.add_argument("log_file", type=str, help="Path to the JSONL log file")
    evaluate_parser.add_argument("--scenario", type=str, required=True, help="Scenario name")
    evaluate_parser.add_argument(
        "--evaluators", type=str, required=True, help="Comma-separated evaluator names"
    )
    evaluate_parser.add_argument(
        "--report", type=str, required=True, help="Path for the JSON evaluation report"
    )
    evaluate_parser.add_argument("--model", type=str, required=True, help="Claude model to use")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(_run_simulation(args=args))
    elif args.command == "evaluate":
        asyncio.run(_run_evaluation(args=args))
    else:
        parser.print_help()


async def _run_simulation(args: argparse.Namespace) -> None:
    """Load a scenario by name, wire up the simulation components, and execute the simulation.

    Writes a JSONL event log to ``<log-dir>/<scenario_name>.jsonl``.
    """
    log_dir = Path(args.log_dir)

    scenario = load_scenario(name=args.scenario_name)
    provider = ClaudeProvider(model=args.model)
    registry = ToolRegistry()

    log_path = log_dir / f"{args.scenario_name}.jsonl"
    event_logger = EventLogger(log_path=log_path)

    hub = SimulationHub(
        scenario=scenario,
        llm_provider=provider,
        tool_registry=registry,
        event_logger=event_logger,
    )

    logger.info("Running scenario: %s", args.scenario_name)
    logger.info("Model: %s", args.model)
    logger.info("Log: %s", log_path)

    await hub.run()

    logger.info("Simulation complete. Log written to %s", log_path)


async def _run_evaluation(args: argparse.Namespace) -> None:
    """Run the specified evaluators against a simulation log and write a JSON report."""
    evaluator_names = args.evaluators.split(",")
    report_path = Path(args.report)
    log_path = Path(args.log_file)

    await run_evaluation(
        log_path=log_path,
        scenario_name=args.scenario,
        evaluator_names=evaluator_names,
        report_path=report_path,
        model=args.model,
    )

    logger.info("Evaluation complete. Report written to %s", report_path)
