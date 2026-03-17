"""Command-line interface for the schmidt simulation runner.

Defines the ``schmidt`` CLI with two subcommands:

* ``run``      -- load and execute a simulation scenario
* ``evaluate`` -- score a previously-generated simulation log
"""

import argparse
import asyncio
import logging
from pathlib import Path

from schmidt.event_logger import EventLogger
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.scenario_loader import get_scenario_class
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.simulation_hub import SimulationHub
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def _build_parsers() -> (
    tuple[argparse.ArgumentParser, argparse.ArgumentParser, argparse.ArgumentParser]
):
    """Build the top-level parser and subcommand parsers.

    Returns the root parser, the ``run`` subparser, and the ``evaluate``
    subparser so that scenario-specific arguments can be added before the
    final parse.
    """
    parser = argparse.ArgumentParser(prog="schmidt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    scenario_names = sorted(SCENARIO_REGISTRY.keys())
    run_parser.add_argument(
        "scenario_name", type=str, choices=scenario_names, help="Name of the scenario to run"
    )
    run_parser.add_argument("--log-dir", type=str, required=True, help="Directory for JSONL logs")
    run_parser.add_argument("--model", type=str, required=True, help="Claude model to use")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a simulation log")
    evaluate_parser.add_argument("log_file", type=str, help="Path to the JSONL log file")
    evaluate_parser.add_argument(
        "--scenario",
        type=str,
        required=True,
        choices=scenario_names,
        dest="scenario_name",
        help="Scenario name",
    )
    evaluate_parser.add_argument(
        "--evaluators", type=str, required=True, help="Comma-separated evaluator names"
    )
    evaluate_parser.add_argument(
        "--report", type=str, required=True, help="Path for the JSON evaluation report"
    )
    evaluate_parser.add_argument("--model", type=str, required=True, help="Claude model to use")

    return parser, run_parser, evaluate_parser


def main() -> None:
    """Parse CLI arguments and dispatch to the ``run`` or ``evaluate`` subcommand."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser, run_parser, evaluate_parser = _build_parsers()

    # First pass: discover the scenario name so its class can register CLI args.
    known_args, _ = parser.parse_known_args()

    scenario_cls = get_scenario_class(name=known_args.scenario_name)
    if known_args.command == "run":
        target_parser = run_parser
    else:
        target_parser = evaluate_parser
    scenario_cls.add_cli_arguments(parser=target_parser)

    # Second pass: full parse including scenario-specific args.
    args = parser.parse_args()

    scenario = scenario_cls.create(args=args)

    if args.command == "run":
        asyncio.run(_run_simulation(args=args, scenario=scenario))
    else:
        asyncio.run(_run_evaluation(args=args, scenario=scenario))


def _build_agent_providers(
    agents: list[AgentConfig],
) -> dict[str, LLMProvider]:
    """Build a per-agent LLM provider mapping.

    Providers are deduped so agents sharing the same model share the same
    ``ClaudeProvider`` instance.
    """
    providers_by_model: dict[str, ClaudeProvider] = {}
    agent_providers: dict[str, LLMProvider] = {}

    for agent in agents:
        if agent.model not in providers_by_model:
            providers_by_model[agent.model] = ClaudeProvider(model=agent.model)
        agent_providers[agent.agent_id] = providers_by_model[agent.model]

    return agent_providers


async def _run_simulation(
    args: argparse.Namespace,
    scenario: SimulationScenario,
) -> None:
    """Wire up the simulation components and execute the simulation.

    Writes a JSONL event log to ``<log-dir>/<scenario_name>.jsonl``.
    """
    log_dir = Path(args.log_dir)
    agents = scenario.get_agents(default_model=args.model)
    agent_providers = _build_agent_providers(agents=agents)
    registry = ToolRegistry()

    log_path = log_dir / f"{scenario.name()}.jsonl"
    event_logger = EventLogger(log_path=log_path)

    hub = SimulationHub(
        scenario=scenario,
        agents=agents,
        agent_providers=agent_providers,
        tool_registry=registry,
        event_logger=event_logger,
    )

    logger.info("Running scenario: %s", scenario.name())
    logger.info("Model: %s", args.model)
    logger.info("Log: %s", log_path)

    await hub.run()

    logger.info("Simulation complete. Log written to %s", log_path)


async def _run_evaluation(
    args: argparse.Namespace,
    scenario: SimulationScenario,
) -> None:
    """Run the specified evaluators against a simulation log and write a JSON report."""
    evaluator_names = args.evaluators.split(",")
    report_path = Path(args.report)
    log_path = Path(args.log_file)

    await scenario.run_evaluation(
        log_path=log_path,
        evaluator_names=evaluator_names,
        report_path=report_path,
        model=args.model,
    )

    logger.info("Evaluation complete. Report written to %s", report_path)
