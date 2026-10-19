"""The ``run`` subcommand: launch or resume a simulation in autonomous mode.

``--config`` names the scenario knobs, and trailing ``key=value`` arguments
override individual fields using dot-notation paths. The ``agents.*``
namespace is reserved for per-agent model/provider overrides.
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from glossogen.autonomous_supervisor import AutonomousSupervisor
from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.config_overrides import (
    ResolvedAgentModel,
    apply_overrides,
    parse_overrides,
    split_agent_overrides,
    validate_agent_override_ids,
)
from glossogen.db.local_tenant import LOCAL_GROUP_SLUG
from glossogen.db.run_registry import register_run_standalone
from glossogen.evaluation.log_reader import load_events
from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.knobs_resolution import resolve_knobs_config
from glossogen.logging_format import EventBusLogHandler, JsonLineFormatter
from glossogen.message_rewind import RewindState
from glossogen.model_catalog import SIMULATION_PROVIDERS
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import RunStatus
from glossogen.provider_credentials import require_reachable_models
from glossogen.resume_context_writer import write_resume_context_files
from glossogen.resume_state_loader import load_resume_state, resume_first_round
from glossogen.run_archive import claim_run_dir
from glossogen.run_config_validation import validate_run_config
from glossogen.run_file_paths import debug_log_path, event_log_path
from glossogen.runners.pydantic_ai_runner import PydanticAIRunner
from glossogen.runtime.game_clock import minimum_duration_elapsed, wall_clock_phase_timeout
from glossogen.scenario_protocol import SimulationScenario
from glossogen.simulation_server import start_simulation_server, stop_simulation_server
from glossogen.telemetry.telemetry_bootstrap import flush_telemetry, init_langfuse_telemetry
from glossogen.telemetry.telemetry_settings import load_telemetry_settings

logger = logging.getLogger(__name__)

EVENT_BUS_MAX_QUEUE_SIZE = 1000
DEFAULT_MAX_AGENT_TURNS = 200


def add_run_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``run`` subcommand and its flags."""
    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    run_parser.add_argument(
        "scenario_name", type=str, choices=scenario_names, help="Name of the scenario to run"
    )
    run_parser.add_argument(
        "--runs-dir",
        type=str,
        help=(
            "Root directory for runs (output goes to runs-dir/scenario/timestamp/). "
            "Required unless --resume is given, which names the directory itself"
        ),
    )
    run_parser.add_argument("--model", type=str, required=True, help="LLM model identifier")
    run_parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=[provider.value for provider in SIMULATION_PROVIDERS],
        help="LLM provider; also the default for every agent",
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
        required=True,
        help=(
            "Scenario knobs: the name of a preset the scenario ships "
            "(e.g. knobs_default), or a path to a JSON file of your own"
        ),
    )
    run_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
    )


def handle_run(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    remaining: list[str],
    scenario_cls: type[SimulationScenario],
) -> None:
    """Validate the run's configuration and the models it reaches, then run it.

    ``remaining`` holds the trailing ``key=value`` overrides the second parse pass
    left unrecognised.
    """
    if args.resume is None and args.runs_dir is None:
        parser.error("--runs-dir is required unless --resume is given")
    config = _build_run_config(args=args, remaining=remaining, scenario_cls=scenario_cls)
    if args.resume is None:
        resume_dir = None
    else:
        resume_dir = Path(args.resume)
    try:
        validated = validate_run_config(
            scenario_cls=scenario_cls,
            scenario_config=config,
            default_provider=args.provider,
            valid_providers=set(SIMULATION_PROVIDERS),
        )
        scenario = scenario_cls.create_from_config(config=validated.scenario_config)
    except (SystemExit, ValueError, TypeError, KeyError) as exc:
        raise SystemExit(f"Invalid run configuration: {exc}") from exc
    try:
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=validated.scenario_config,
            agent_overrides=validated.normalized_agent_overrides,
            default_model=args.model,
            default_provider=args.provider,
            first_round=resume_first_round(
                resume_dir=resume_dir,
                scenario_name=scenario_cls.name(),
            ),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    asyncio.run(
        _run_simulation(
            args=args,
            scenario=scenario,
            agent_overrides=validated.normalized_agent_overrides or {},
        )
    )


def _build_run_config(
    args: argparse.Namespace,
    remaining: list[str],
    scenario_cls: type[SimulationScenario],
) -> dict[str, object]:
    """Build scenario config from --config and Hydra-style overrides.

    Resolves ``--config`` to a preset the scenario ships or to a JSON file,
    applies any key=value overrides from remaining args, and splits out the
    ``agents.*`` namespace as per-agent model/provider overrides.

    Returns the merged scenario config dict.
    """
    resolved = resolve_knobs_config(scenario_cls=scenario_cls, requested=args.config)
    logger.info("Scenario knobs from %s", resolved.source)
    config: dict[str, object] = dict(resolved.config)

    if remaining:
        overrides = parse_overrides(raw_args=remaining)
        config = apply_overrides(config=config, overrides=overrides)

    split = split_agent_overrides(config=config)
    if split.agent_overrides:
        existing_overrides = split.scenario_config.get("model_overrides")
        cli_overrides = {
            agent_id: override.model_dump(mode="json")
            for agent_id, override in split.agent_overrides.items()
        }
        if existing_overrides is None:
            split.scenario_config["model_overrides"] = cli_overrides
        elif isinstance(existing_overrides, dict):
            merged_overrides: dict[str, Any] = dict(cast(dict[str, Any], existing_overrides))
            merged_overrides.update(cli_overrides)
            split.scenario_config["model_overrides"] = merged_overrides
        else:
            raise SystemExit(
                "Invalid model_overrides in config: expected an object "
                "mapping agent IDs to override payloads."
            )
    return split.scenario_config


def _apply_agent_overrides(
    agents: list[AgentConfig],
    agent_overrides: dict[str, ResolvedAgentModel],
) -> list[AgentConfig]:
    """Apply the normalized per-agent model/provider overrides to the built agents.

    Validates that all override keys correspond to actual agent IDs.
    """
    if not agent_overrides:
        return agents

    agent_ids = {a.agent_id for a in agents}
    validate_agent_override_ids(
        agent_overrides=agent_overrides,
        valid_agent_ids=agent_ids,
    )

    for agent in agents:
        override = agent_overrides.get(agent.agent_id)
        if override is not None:
            agent.model = override.model
            agent.provider = override.provider

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
    debug_log_file = debug_log_path(run_dir=run_dir, scenario_name=scenario_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    json_handler = logging.FileHandler(debug_log_file)
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
    agent_overrides: dict[str, ResolvedAgentModel],
) -> None:
    """Wire up the autonomous supervisor, start the streaming server, and execute."""

    resume_dir: str | None = getattr(args, "resume", None)
    resuming = resume_dir is not None

    if resume_dir is not None:
        run_dir = Path(resume_dir)
    else:
        runs_dir = Path(args.runs_dir)
        run_dir = _compute_run_dir(runs_dir=runs_dir, scenario_name=scenario.name())
        # Print attribution markers BEFORE the simulation starts so an
        # orchestrator that detached this process can read the freshly-claimed
        # run id by tailing stdout, instead of racing on a directory snapshot.
        print(f"new_run_id={scenario.name()}/{run_dir.name}", flush=True)
        print(f"new_run_dir={run_dir}", flush=True)
        await register_run_standalone(
            group_slug=args.group_slug,
            scenario=scenario.name(),
            run_dir_name=run_dir.name,
            status=RunStatus.STARTING.value,
            created_at=datetime.now(tz=UTC),
            created_by_user_id=None,
            source_run_scenario=None,
            source_run_dir_name=None,
        )

    scenario.set_run_dir(run_dir=run_dir)
    agents = scenario.get_agents(default_model=args.model, default_provider=args.provider)

    agents = _apply_agent_overrides(
        agents=agents,
        agent_overrides=agent_overrides,
    )

    log_path = event_log_path(run_dir=run_dir, scenario_name=scenario.name())
    event_bus = EventBus(max_queue_size=EVENT_BUS_MAX_QUEUE_SIZE)

    event_logger = EventLogger(log_path=log_path, event_bus=event_bus)

    resume_state: RewindState | None = None
    if resuming:
        logger.info("Loading rewind state from %s", log_path)
        events = await load_events(log_path=log_path)
        resume_state = await load_resume_state(run_dir=run_dir, events=events)
        if resume_state.enter_round_by_advancing:
            logger.info(
                "Rewind state loaded: round %d is complete, advancing into round %d",
                resume_state.round_number,
                resume_state.round_number + 1,
            )
        else:
            logger.info(
                "Rewind state loaded: resuming from round %d",
                resume_state.round_number,
            )
        scenario.restore_state_from_events(events=events)
        write_resume_context_files(
            run_dir=run_dir,
            agent_message_histories=resume_state.agent_message_histories,
        )

    max_turns = args.max_agent_turns
    run_id = f"{scenario.name()}/{run_dir.name}"
    scenario_name = scenario.name()

    telemetry_handle = init_langfuse_telemetry(settings=load_telemetry_settings())

    def _make_runner() -> PydanticAIRunner:
        return PydanticAIRunner(
            max_turns=max_turns,
            event_bus=event_bus,
            run_id=run_id,
            scenario_name=scenario_name,
            telemetry_enabled=telemetry_handle is not None,
        )

    supervisor = AutonomousSupervisor(
        scenario=scenario,
        agent_configs=agents,
        event_logger=event_logger,
        idle_round_may_end=minimum_duration_elapsed,
        phase_timed_out=wall_clock_phase_timeout,
        runner_factory=_make_runner,
        resume_state=resume_state,
        run_id=run_id,
        provider=args.provider,
        log_path=log_path,
    )

    json_handler, bus_log_handler = _setup_logging(
        run_dir=run_dir,
        scenario_name=scenario.name(),
        event_bus=event_bus,
    )

    logger.info("Running scenario: %s", scenario.name())
    logger.info("Model: %s", args.model)
    logger.info("Max agent turns: %d", max_turns)
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
        if telemetry_handle is not None:
            flush_telemetry(handle=telemetry_handle)

    logger.info("Simulation complete. Run directory: %s", run_dir)
