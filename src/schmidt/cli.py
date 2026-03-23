"""Command-line interface for the schmidt simulation runner.

Defines the ``schmidt`` CLI with three subcommands:

* ``run``      -- load and execute a simulation scenario
* ``evaluate`` -- score a previously-generated simulation log
* ``serve``    -- start the FastAPI web server
"""

import argparse
import asyncio
import logging
import os
import time
from pathlib import Path

import uvicorn

from schmidt.checkpoint_loader import ResumeState, build_resume_state
from schmidt.evaluation.log_reader import load_events
from schmidt.event_logger import EventLogger
from schmidt.llm.provider import LLMProvider
from schmidt.llm.provider_factory import create_provider
from schmidt.logging_format import JsonLineFormatter
from schmidt.models.agent_config import AgentConfig
from schmidt.scenario_loader import get_scenario_class
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.simulation_hub import SimulationHub
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


def _build_parsers() -> tuple[
    argparse.ArgumentParser,
    argparse.ArgumentParser,
    argparse.ArgumentParser,
    argparse.ArgumentParser,
]:
    """Build the top-level parser and subcommand parsers.

    Returns the root parser, the ``run`` subparser, the ``evaluate``
    subparser, and the ``serve`` subparser so that scenario-specific
    arguments can be added before the final parse.
    """
    parser = argparse.ArgumentParser(prog="schmidt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    scenario_names = sorted(SCENARIO_REGISTRY.keys())
    run_parser.add_argument(
        "scenario_name", type=str, choices=scenario_names, help="Name of the scenario to run"
    )
    run_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory for runs (output goes to runs-dir/scenario/timestamp/)",
    )
    run_parser.add_argument("--model", type=str, required=True, help="LLM model to use")
    run_parser.add_argument(
        "--reasoning-effort",
        type=str,
        choices=["low", "medium", "high"],
        help="Reasoning effort level for OpenAI reasoning models (low/medium/high)",
    )
    run_parser.add_argument(
        "--resume",
        type=str,
        help="Path to an existing run directory to resume from (e.g. runs/car_recall/1742234567)",
    )

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a simulation log")
    evaluate_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario to evaluate",
    )
    evaluate_parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the run directory (e.g. runs/car_recall/1742234567)",
    )
    evaluate_parser.add_argument(
        "--evaluators", type=str, required=True, help="Comma-separated evaluator names"
    )
    evaluate_parser.add_argument("--model", type=str, required=True, help="LLM model to use")
    evaluate_parser.add_argument(
        "--reasoning-effort",
        type=str,
        choices=["low", "medium", "high"],
        help="Reasoning effort level for OpenAI reasoning models (low/medium/high)",
    )

    serve_parser = subparsers.add_parser("serve", help="Start the web server")
    serve_parser.add_argument(
        "--runs-dir", type=str, required=True, help="Root directory containing simulation runs"
    )
    serve_parser.add_argument("--port", type=int, required=True, help="Port to listen on")

    return parser, run_parser, evaluate_parser, serve_parser


def main() -> None:
    """Parse CLI arguments and dispatch to the ``run``, ``evaluate``, or ``serve`` subcommand."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser, run_parser, evaluate_parser, _ = _build_parsers()

    # First pass: discover the command (and scenario name for run/evaluate).
    known_args, _ = parser.parse_known_args()

    if known_args.command == "serve":
        args = parser.parse_args()
        _run_serve(args=args)
        return

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
    reasoning_effort: str | None,
) -> dict[str, LLMProvider]:
    """Build a per-agent LLM provider mapping.

    Providers are deduped so agents sharing the same model share the same
    provider instance. Routes to the appropriate provider (OpenAI or Claude)
    based on model name.
    """
    providers_by_model: dict[str, LLMProvider] = {}
    agent_providers: dict[str, LLMProvider] = {}

    for agent in agents:
        if agent.model not in providers_by_model:
            providers_by_model[agent.model] = create_provider(
                model=agent.model, reasoning_effort=reasoning_effort
            )
        agent_providers[agent.agent_id] = providers_by_model[agent.model]

    return agent_providers


def _compute_run_dir(runs_dir: Path, scenario_name: str) -> Path:
    """Compute the output directory for a new simulation run.

    Uses the current unix timestamp to create a unique subdirectory:
    ``{runs_dir}/{scenario_name}/{unix_timestamp}/``
    """
    unix_ts = int(time.time())
    return runs_dir / scenario_name / str(unix_ts)


async def _run_simulation(
    args: argparse.Namespace,
    scenario: SimulationScenario,
) -> None:
    """Wire up the simulation components and execute the simulation.

    Writes a JSONL event log to ``{runs_dir}/{scenario_name}/{timestamp}/{scenario_name}.jsonl``.
    When ``--resume`` is specified, loads the checkpoint from the existing run
    directory and continues from where it left off.
    """
    resume_dir: str | None = getattr(args, "resume", None)
    resuming = resume_dir is not None

    if resume_dir is not None:
        run_dir = Path(resume_dir)
    else:
        runs_dir = Path(args.runs_dir)
        run_dir = _compute_run_dir(runs_dir=runs_dir, scenario_name=scenario.name())

    agents = scenario.get_agents(default_model=args.model)
    reasoning_effort = getattr(args, "reasoning_effort", None)
    agent_providers = _build_agent_providers(agents=agents, reasoning_effort=reasoning_effort)
    registry = ToolRegistry()

    log_path = run_dir / f"{scenario.name()}.jsonl"
    event_logger = EventLogger(log_path=log_path)

    resume_state: ResumeState | None = None
    if resuming:
        logger.info("Loading checkpoint from %s", log_path)
        events = await load_events(log_path=log_path)
        resume_state = build_resume_state(events=events)
        logger.info(
            "Checkpoint loaded: resuming from turn %d, round %d",
            resume_state.turn_number,
            resume_state.round_number,
        )

    hub = SimulationHub(
        scenario=scenario,
        agents=agents,
        agent_providers=agent_providers,
        tool_registry=registry,
        event_logger=event_logger,
        resume_state=resume_state,
    )

    # Add JSON debug log file for frontend display
    debug_log_path = run_dir / f"{scenario.name()}_debug.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    json_handler = logging.FileHandler(debug_log_path)
    json_handler.setFormatter(JsonLineFormatter())
    logging.getLogger().addHandler(json_handler)

    logger.info("Running scenario: %s", scenario.name())
    logger.info("Model: %s", args.model)
    logger.info("Run directory: %s", run_dir)
    logger.info("Log: %s", log_path)
    if resuming:
        logger.info("RESUMING from checkpoint in %s", run_dir)

    try:
        await hub.run()
    finally:
        logging.getLogger().removeHandler(json_handler)
        json_handler.close()

    logger.info("Simulation complete. Run directory: %s", run_dir)


async def _run_evaluation(
    args: argparse.Namespace,
    scenario: SimulationScenario,
) -> None:
    """Run the specified evaluators against a simulation log and write a JSON report."""
    evaluator_names = args.evaluators.split(",")
    run_dir = Path(args.run_dir)
    log_path = run_dir / f"{args.scenario_name}.jsonl"
    report_path = run_dir / f"{args.scenario_name}_report.json"

    reasoning_effort = getattr(args, "reasoning_effort", None)
    await scenario.run_evaluation(
        log_path=log_path,
        evaluator_names=evaluator_names,
        report_path=report_path,
        model=args.model,
        reasoning_effort=reasoning_effort,
    )

    logger.info("Evaluation complete. Report written to %s", report_path)


def _run_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI web server."""
    os.environ["SCHMIDT_RUNS_DIR"] = args.runs_dir
    uvicorn.run(
        app="schmidt.server.app:app",
        host="0.0.0.0",
        port=args.port,
        reload=False,
    )
