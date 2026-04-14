"""Command-line interface for the schmidt simulation runner.

Defines the ``schmidt`` CLI with three subcommands:

* ``run``      -- load and execute a simulation scenario in autonomous mode
* ``evaluate`` -- score a previously-generated simulation log
* ``serve``    -- start the FastAPI web server

The ``run`` subcommand uses Hydra-style config overrides: a base config
file (``--config``) is loaded and then any trailing ``key=value``
arguments override individual fields using dot-notation paths. The
``agents.*`` namespace is reserved for per-agent model/provider overrides.
"""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import uvicorn
from dotenv import load_dotenv

from schmidt.autonomous_supervisor import AutonomousSupervisor
from schmidt.config_overrides import (
    apply_overrides,
    normalize_agent_overrides,
    parse_overrides,
    split_agent_overrides,
    validate_agent_override_ids,
)
from schmidt.eval_manifest import delete_eval_manifest, write_eval_manifest
from schmidt.evaluation.log_reader import extract_scenario_config, load_events
from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.logging_format import EventBusLogHandler, JsonLineFormatter
from schmidt.message_rewind import RewindState, build_rewind_state_from_last_message
from schmidt.models.agent_config import AgentConfig
from schmidt.run_config_validation import validate_run_config
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.runners.pydantic_ai_runner import PydanticAIRunner
from schmidt.scenario_loader import get_scenario_class
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.simulation_server import start_simulation_server, stop_simulation_server
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)

EVENT_BUS_MAX_QUEUE_SIZE = 1000
DEFAULT_MCP_PORT = 8001
DEFAULT_MAX_AGENT_TURNS = 200


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and all subcommand parsers."""
    parser = argparse.ArgumentParser(prog="schmidt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scenario_names = sorted(SCENARIO_REGISTRY.keys())

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    run_parser.add_argument(
        "scenario_name", type=str, choices=scenario_names, help="Name of the scenario to run"
    )
    run_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory for runs (output goes to runs-dir/scenario/timestamp/)",
    )
    run_parser.add_argument("--model", type=str, required=True, help="LLM model identifier")
    run_parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=["anthropic", "openai", "google-gla", "ollama"],
        help="LLM provider (anthropic, openai, google-gla, ollama)",
    )
    run_parser.add_argument(
        "--mcp-port",
        type=int,
        default=DEFAULT_MCP_PORT,
        help=f"Port for the MCP server (default: {DEFAULT_MCP_PORT})",
    )
    run_parser.add_argument(
        "--max-agent-turns",
        type=int,
        default=DEFAULT_MAX_AGENT_TURNS,
        help=f"Max agentic turns per agent (default: {DEFAULT_MAX_AGENT_TURNS})",
    )
    run_parser.add_argument(
        "--resume",
        type=str,
        help="Path to an existing run directory to resume from",
    )
    run_parser.add_argument(
        "--config",
        type=str,
        help="Path to a JSON config file (scenario knobs + optional agents overrides)",
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
        help="Path to the run directory (e.g. runs/telephone/1742234567)",
    )
    evaluate_parser.add_argument(
        "--evaluators", type=str, required=True, help="Comma-separated evaluator names"
    )
    evaluate_parser.add_argument("--model", type=str, required=True, help="LLM model identifier")
    evaluate_parser.add_argument(
        "--provider",
        type=str,
        required=True,
        help="LLM provider to use",
    )
    evaluate_parser.add_argument(
        "--inference-provider",
        type=str,
        help="HuggingFace inference provider backend (e.g. together, fireworks-ai, cerebras)",
    )
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

    return parser


def main() -> None:
    """Parse CLI arguments and dispatch to the ``run``, ``evaluate``, or ``serve`` subcommand."""

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    parser = _build_parser()

    # First pass: discover the command (and scenario name for run/evaluate).
    known_args, _ = parser.parse_known_args()

    if known_args.command == "serve":
        args = parser.parse_args()
        _run_serve(args=args)
        return

    scenario_cls = get_scenario_class(name=known_args.scenario_name)

    # Second pass: parse known flags and capture remaining key=value overrides.
    args, remaining = parser.parse_known_args()

    if args.command == "run":
        config = _build_run_config(args=args, remaining=remaining)
        try:
            validated = validate_run_config(
                scenario_cls=scenario_cls,
                scenario_config=config,
                default_provider=args.provider,
                valid_providers=set(list_providers()),
            )
            scenario = scenario_cls.create_from_config(config=validated.scenario_config)
        except (SystemExit, ValueError, TypeError, KeyError) as exc:
            raise SystemExit(f"Invalid run configuration: {exc}") from exc
        asyncio.run(
            _run_simulation(
                args=args,
                scenario=scenario,
                agent_overrides=validated.normalized_agent_overrides or {},
            )
        )
    else:
        asyncio.run(_run_evaluation(args=args, scenario_cls=scenario_cls))


def _build_run_config(
    args: argparse.Namespace,
    remaining: list[str],
) -> dict[str, object]:
    """Build scenario config from --config file and Hydra-style overrides.

    Loads the base config JSON (if --config is provided), applies any
    key=value overrides from remaining args, and splits out the
    ``agents.*`` namespace as per-agent model/provider overrides.

    Returns the merged scenario config dict.
    """
    config: dict[str, object] = {}
    if args.config is not None:
        config = json.loads(Path(args.config).read_text())

    if remaining:
        overrides = parse_overrides(raw_args=remaining)
        config = apply_overrides(config=config, overrides=overrides)

    split = split_agent_overrides(config=config)
    if split.agent_overrides:
        existing_overrides = split.scenario_config.get("model_overrides")
        if existing_overrides is None:
            split.scenario_config["model_overrides"] = split.agent_overrides
        elif isinstance(existing_overrides, dict):
            merged_overrides = dict(existing_overrides)
            merged_overrides.update(split.agent_overrides)
            split.scenario_config["model_overrides"] = merged_overrides
        else:
            raise SystemExit(
                "Invalid model_overrides in config: expected an object "
                "mapping agent IDs to override payloads."
            )
    return split.scenario_config


def _apply_agent_overrides(
    agents: list[AgentConfig],
    agent_overrides: dict[str, dict[str, str]],
    default_provider: str,
) -> list[AgentConfig]:
    """Apply per-agent model/provider overrides extracted from the config.

    Validates that all override keys correspond to actual agent IDs.
    """
    if not agent_overrides:
        return agents

    normalized_overrides = normalize_agent_overrides(
        agent_overrides=agent_overrides,
        default_provider=default_provider,
        valid_providers=set(list_providers()),
    )

    agent_ids = {a.agent_id for a in agents}
    validate_agent_override_ids(
        agent_overrides=normalized_overrides,
        valid_agent_ids=agent_ids,
    )

    for agent in agents:
        if agent.agent_id in normalized_overrides:
            override = normalized_overrides[agent.agent_id]
            agent.model = override["model"]
            agent.provider = override["provider"]

    return agents


def _compute_run_dir(runs_dir: Path, scenario_name: str) -> Path:
    """Claim a unique run directory for a new simulation.

    Delegates to ``claim_run_dir`` which atomically creates the directory,
    appending a numeric suffix if two runs start in the same second.
    """
    return claim_run_dir(runs_dir=runs_dir, scenario_name=scenario_name)


def _setup_logging(
    run_dir: Path,
    scenario_name: str,
    event_bus: EventBus,
) -> tuple[logging.FileHandler, EventBusLogHandler]:
    """Set up JSON debug log file and EventBus log handler for frontend display.

    Returns the two handlers so they can be removed during teardown.
    """
    debug_log_path = run_dir / f"{scenario_name}_debug.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    json_handler = logging.FileHandler(debug_log_path)
    json_handler.setFormatter(JsonLineFormatter())
    logging.getLogger().addHandler(json_handler)

    bus_log_handler = EventBusLogHandler(event_bus=event_bus)
    logging.getLogger().addHandler(bus_log_handler)

    return json_handler, bus_log_handler


def _teardown_logging(
    json_handler: logging.FileHandler,
    bus_log_handler: EventBusLogHandler,
) -> None:
    """Remove and close log handlers added during setup."""
    logging.getLogger().removeHandler(json_handler)
    json_handler.close()
    logging.getLogger().removeHandler(bus_log_handler)


async def _run_simulation(
    args: argparse.Namespace,
    scenario: SimulationScenario,
    agent_overrides: dict[str, dict[str, str]],
) -> None:
    """Wire up the autonomous supervisor, start the streaming server, and execute."""

    resume_dir: str | None = getattr(args, "resume", None)
    resuming = resume_dir is not None

    if resume_dir is not None:
        run_dir = Path(resume_dir)
    else:
        runs_dir = Path(args.runs_dir)
        run_dir = _compute_run_dir(runs_dir=runs_dir, scenario_name=scenario.name())

    scenario.set_run_dir(run_dir=run_dir)
    agents = scenario.get_agents(default_model=args.model, default_provider=args.provider)

    agents = _apply_agent_overrides(
        agents=agents,
        agent_overrides=agent_overrides,
        default_provider=args.provider,
    )

    log_path = run_dir / f"{scenario.name()}.jsonl"
    event_bus = EventBus(max_queue_size=EVENT_BUS_MAX_QUEUE_SIZE)

    repo = RunRepository(run_dir=run_dir)
    if not resuming:
        await repo.init()

    event_logger = EventLogger(log_path=log_path, event_bus=event_bus, repo=repo)

    resume_state: RewindState | None = None
    if resuming:
        logger.info("Loading rewind state from %s", log_path)
        events = await load_events(log_path=log_path)
        resume_state = build_rewind_state_from_last_message(events=events)
        logger.info(
            "Rewind state loaded: resuming from round %d",
            resume_state.round_number,
        )

    max_turns = args.max_agent_turns
    run_id = str(uuid4())

    def _make_runner() -> PydanticAIRunner:
        return PydanticAIRunner(
            max_turns=max_turns,
            event_bus=event_bus,
        )

    supervisor = AutonomousSupervisor(
        scenario=scenario,
        agent_configs=agents,
        event_logger=event_logger,
        mcp_server_port=args.mcp_port,
        runner_factory=_make_runner,
        resume_state=resume_state,
        run_id=run_id,
        provider=args.provider,
    )

    json_handler, bus_log_handler = _setup_logging(
        run_dir=run_dir,
        scenario_name=scenario.name(),
        event_bus=event_bus,
    )

    logger.info("Running scenario: %s", scenario.name())
    logger.info("Model: %s", args.model)
    logger.info("MCP port: %d, max agent turns: %d", args.mcp_port, max_turns)
    logger.info("Run directory: %s", run_dir)
    logger.info("Log: %s", log_path)
    if resuming:
        logger.info("RESUMING from rewind state in %s", run_dir)

    server, port = await start_simulation_server(
        event_bus=event_bus,
        run_dir=run_dir,
        run_id=run_id,
    )
    logger.info("Streaming server started on port %d", port)

    try:
        await supervisor.run()
    finally:
        _teardown_logging(json_handler=json_handler, bus_log_handler=bus_log_handler)
        await stop_simulation_server(server=server, run_dir=run_dir)

    logger.info("Simulation complete. Run directory: %s", run_dir)


async def _run_evaluation(
    args: argparse.Namespace,
    scenario_cls: type[SimulationScenario],
) -> None:
    """Run the specified evaluators against a simulation log and write a JSON report.

    Reconstructs the scenario from the config stored in the JSONL event log,
    so the evaluate command does not need scenario-specific CLI flags.
    Writes an eval manifest while running so the web UI can detect progress.
    """
    evaluator_names = args.evaluators.split(",")
    run_dir = Path(args.run_dir)
    log_path = run_dir / f"{args.scenario_name}.jsonl"
    report_path = run_dir / f"{args.scenario_name}_report.json"

    events = await load_events(log_path=log_path)
    config = extract_scenario_config(events=events)
    scenario = scenario_cls.create_from_config(config=config)

    write_eval_manifest(run_dir=run_dir, pid=os.getpid())
    try:
        logger.info("Evaluating %s with evaluators: %s", args.scenario_name, args.evaluators)
        await scenario.run_evaluation(
            log_path=log_path,
            evaluator_names=evaluator_names,
            report_path=report_path,
            model=args.model,
            provider_name=args.provider,
            inference_provider=args.inference_provider,
            reasoning_effort=getattr(args, "reasoning_effort", None),
        )
        logger.info("Evaluation complete. Report written to %s", report_path)
    finally:
        delete_eval_manifest(run_dir=run_dir)


def _run_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI web server."""
    logger.info("Starting web server on port %d, runs dir: %s", args.port, args.runs_dir)
    os.environ["SCHMIDT_RUNS_DIR"] = args.runs_dir
    uvicorn.run(
        app="schmidt.server.app:app",
        host="0.0.0.0",
        port=args.port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
