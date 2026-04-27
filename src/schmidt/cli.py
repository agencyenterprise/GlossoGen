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
from typing import Any, NamedTuple

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
from schmidt.evaluation.label_writer import write_eval_labels
from schmidt.evaluation.log_reader import extract_scenario_config, load_events
from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.logging_format import EventBusLogHandler, JsonLineFormatter
from schmidt.message_rewind import (
    AgentHistoryFilter,
    RewindState,
    build_rewind_state_from_last_message,
)
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import AgentRegistered, SimulationStarted
from schmidt.port_allocator import find_free_port
from schmidt.replace_agent import ReplaceAgentRequest as ReplaceAgentCoreRequest
from schmidt.replace_agent import replace_agent_in_run
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
        help="Path to the run directory (e.g. runs/veyru/1742234567)",
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

    replace_parser = subparsers.add_parser(
        "replace-agent",
        help="Replace one agent in a finished run from a target message and re-run",
    )
    replace_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the source run belongs to",
    )
    replace_parser.add_argument(
        "--source-run-dir",
        type=str,
        required=True,
        help="Path to the source run directory (e.g. runs/veyru/1742234567)",
    )
    replace_parser.add_argument(
        "--round-start",
        dest="round_start",
        type=int,
        required=True,
        help=(
            "Round number that the resumed simulation should re-enter "
            "fresh. Rewinds to the last message before this round began."
        ),
    )
    replace_parser.add_argument(
        "--replaced-agent-id",
        type=str,
        required=True,
        help="agent_id of the agent to restart with empty history",
    )
    replace_parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="Model identifier for the replacement agent",
    )
    replace_parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=["anthropic", "openai", "google-gla", "ollama"],
        help="Provider for the replacement agent",
    )
    replace_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    replace_parser.add_argument(
        "--knobs",
        type=str,
        help="Optional path to a JSON file with scenario knob overrides",
    )
    replace_parser.add_argument(
        "--visible-history-channel",
        dest="visible_history_channels",
        action="append",
        default=None,
        help=(
            "Channel ID for which the replaced agent retains visibility of prior "
            "messages on resume. Repeatable. When the flag is omitted entirely, "
            "the per-channel defaults from the source run's "
            "`replace_agent_default_channel_visibility` knob are used (channels "
            "that map to false get wiped; the rest stay visible)."
        ),
    )
    replace_parser.add_argument(
        "--rounds-after-swap",
        dest="rounds_after_swap",
        type=int,
        default=10,
        help=(
            "Number of rounds the resumed simulation will play after the "
            "replacement boundary. round_count is set to round_start + "
            "rounds_after_swap. Default: 10."
        ),
    )

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

    if known_args.command == "replace-agent":
        args = parser.parse_args()
        asyncio.run(_run_replace_agent(args=args))
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


class _ReplaceManifestInfo(NamedTuple):
    """Replace-agent manifest fields needed to configure resume."""

    replaced_agent_id: str
    visible_channels: list[str]
    blocked_channel_ids: frozenset[str]


def _read_replace_manifest(run_dir: Path) -> _ReplaceManifestInfo | None:
    """Read ``replace_manifest.json`` if present and extract resume fields."""
    manifest_path = run_dir / "replace_manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    replaced = manifest.get("replaced_agent_id")
    if not isinstance(replaced, str):
        return None
    raw_visible = manifest.get("channels_with_visible_history", [])
    visible_channels: list[str] = []
    if isinstance(raw_visible, list):
        visible_channels = [str(channel_id) for channel_id in raw_visible]
    raw_blocked = manifest.get("blocked_tool_call_channels", [])
    blocked_channel_ids: frozenset[str] = frozenset()
    if isinstance(raw_blocked, list):
        blocked_channel_ids = frozenset(str(channel_id) for channel_id in raw_blocked)
    return _ReplaceManifestInfo(
        replaced_agent_id=replaced,
        visible_channels=visible_channels,
        blocked_channel_ids=blocked_channel_ids,
    )


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
        replace_info = _read_replace_manifest(run_dir=run_dir)
        agent_filters: dict[str, AgentHistoryFilter] = {}
        if replace_info is not None:
            agent_filters[replace_info.replaced_agent_id] = AgentHistoryFilter(
                tool_calls_only=True,
                blocked_channel_ids=replace_info.blocked_channel_ids,
            )
        resume_state = build_rewind_state_from_last_message(
            events=events,
            agent_filters=agent_filters,
        )
        if replace_info is not None:
            resume_state = resume_state._replace(
                replaced_agent_ids=frozenset({replace_info.replaced_agent_id}),
                replaced_agent_channels_with_visible_history={
                    replace_info.replaced_agent_id: replace_info.visible_channels,
                },
            )
            logger.info(
                "Replace-agent run detected: %s resuming with visible channels %s, "
                "blocked tool-call channels %s",
                replace_info.replaced_agent_id,
                replace_info.visible_channels,
                sorted(replace_info.blocked_channel_ids),
            )
        logger.info(
            "Rewind state loaded: resuming from round %d",
            resume_state.round_number,
        )

    max_turns = args.max_agent_turns
    run_id = f"{scenario.name()}/{run_dir.name}"

    def _make_runner() -> PydanticAIRunner:
        return PydanticAIRunner(
            max_turns=max_turns,
            event_bus=event_bus,
        )

    mcp_port = find_free_port()

    supervisor = AutonomousSupervisor(
        scenario=scenario,
        agent_configs=agents,
        event_logger=event_logger,
        mcp_server_port=mcp_port,
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
    logger.info("MCP port: %d, max agent turns: %d", mcp_port, max_turns)
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
        report = await scenario.run_evaluation(
            log_path=log_path,
            evaluator_names=evaluator_names,
            report_path=report_path,
            model=args.model,
            provider_name=args.provider,
            inference_provider=args.inference_provider,
            reasoning_effort=getattr(args, "reasoning_effort", None),
        )
        write_eval_labels(run_dir=run_dir, report=report)
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


async def _run_replace_agent(args: argparse.Namespace) -> None:
    """Drive the replace-agent operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and resolves the
    visible-history channel list (explicit ``--visible-history-channel``
    flags, or the source run's per-channel defaults), calls the shared
    helper, and prints the new run ID and run dir on success.
    """
    knobs: dict[str, Any] | None = None
    if args.knobs is not None:
        knobs = json.loads(Path(args.knobs).read_text())

    source_run_dir = Path(args.source_run_dir).resolve()

    if args.visible_history_channels is None:
        visible_channels = await _resolve_default_visible_channels(
            source_run_dir=source_run_dir,
            scenario_name=args.scenario_name,
            replaced_agent_id=args.replaced_agent_id,
        )
    else:
        visible_channels = list(args.visible_history_channels)

    logger.info(
        "Replace-agent: replaced=%s visible_channels=%s",
        args.replaced_agent_id,
        visible_channels,
    )

    request = ReplaceAgentCoreRequest(
        source_run_dir=source_run_dir,
        scenario_name=args.scenario_name,
        round_start=args.round_start,
        rounds_after_swap=args.rounds_after_swap,
        replaced_agent_id=args.replaced_agent_id,
        model=args.model,
        provider=args.provider,
        knobs=knobs,
        channels_with_visible_history=visible_channels,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"replace-agent failed: {exc}") from exc

    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")


async def _resolve_default_visible_channels(
    source_run_dir: Path,
    scenario_name: str,
    replaced_agent_id: str,
) -> list[str]:
    """Compute the default visible-history channel list from source-run state.

    Combines the source run's ``replace_agent_default_channel_visibility``
    knob (channel_id → bool) with the replaced agent's actual channel
    memberships taken from its ``AgentRegistered`` event. A channel is
    visible by default unless the knob explicitly maps it to ``False``.
    """
    log_path = source_run_dir / f"{scenario_name}.jsonl"
    events = await load_events(log_path=log_path)

    visibility_map: dict[str, bool] = {}
    agent_channels: list[str] = []
    for event in events:
        if isinstance(event, SimulationStarted):
            raw = event.scenario_config.get("replace_agent_default_channel_visibility", {})
            if isinstance(raw, dict):
                visibility_map = {
                    str(channel_id): bool(visible) for channel_id, visible in raw.items()
                }
        elif isinstance(event, AgentRegistered) and event.agent_id == replaced_agent_id:
            agent_channels = list(event.channel_ids)

    return [channel_id for channel_id in agent_channels if visibility_map.get(channel_id, True)]
