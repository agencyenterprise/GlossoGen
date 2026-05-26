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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, cast

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
from schmidt.cross_run_replace_agent import CrossRunReplaceAgentRequest as CrossRunCoreRequest
from schmidt.cross_run_replace_agent import cross_run_replace_agent_in_run
from schmidt.cross_run_replace_manifest import read_cross_run_replace_manifest
from schmidt.db.local_tenant import LOCAL_GROUP_SLUG
from schmidt.db.run_registry import register_run_standalone
from schmidt.eval_manifest import delete_eval_manifest, write_eval_manifest
from schmidt.evaluation.log_reader import extract_scenario_config, load_events
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.logging_format import EventBusLogHandler, JsonLineFormatter
from schmidt.message_rewind import (
    AgentHistoryFilter,
    ImportedHistory,
    RewindState,
    build_rewind_state_at_event,
    build_rewind_state_from_last_message,
)
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    AgentRegistered,
    RoundAdvanced,
    RunStatus,
    SimulationEvent,
    SimulationStarted,
)
from schmidt.oauth_client import CREDENTIALS_PATH, run_login
from schmidt.port_allocator import find_free_port
from schmidt.prod_push import PushSpec, run_push_to_prod
from schmidt.replace_agent import ReplaceAgentRequest as ReplaceAgentCoreRequest
from schmidt.replace_agent import replace_agent_in_run
from schmidt.replace_manifest import read_replace_manifest
from schmidt.resume_context_writer import write_resume_context_files
from schmidt.run_archive import claim_run_dir
from schmidt.run_config_validation import validate_run_config
from schmidt.runners.pydantic_ai_runner import PydanticAIRunner
from schmidt.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFull,
    ChannelVisibilityNone,
)
from schmidt.scenario_loader import get_scenario_class
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenario_registry import SCENARIO_REGISTRY
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
        choices=["anthropic", "openai", "google-gla", "ollama", "self-hosted"],
        help="LLM provider (anthropic, openai, google-gla, ollama, self-hosted)",
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
    run_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
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
        "--metrics", type=str, required=True, help="Comma-separated metric names"
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
    evaluate_parser.add_argument(
        "--probe-round",
        dest="probe_round",
        type=int,
        default=None,
        help=(
            "Cutoff for the protocol_probe metric: drops every tool call whose "
            "round_number >= R, so reconstructed history covers rounds 1..R-1 "
            "(inclusive). Pass --probe-round=R+1 to capture the agent's state "
            "at the END of round R. Omit for the full end-of-run history."
        ),
    )
    evaluate_parser.add_argument(
        "--probe-replicas",
        dest="probe_replicas",
        type=int,
        default=None,
        help=(
            "Number of independent replicas the protocol_probe metric runs per "
            "(agent, question). Required when --metrics includes protocol_probe."
        ),
    )
    evaluate_parser.add_argument(
        "--ontology-path",
        dest="ontology_path",
        type=str,
        default=None,
        help=(
            "Path to a consolidated communication-feature ontology JSON file. "
            "Required when --metrics includes communication_feature_presence."
        ),
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
        choices=["anthropic", "openai", "google-gla", "ollama", "self-hosted"],
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
        default=None,
        help=(
            "Number of rounds the resumed simulation will play after the "
            "replacement boundary. round_count is set to round_start + "
            "rounds_after_swap. When omitted, defaults to "
            "source_round_count - round_start (the remaining rounds in the "
            "original run)."
        ),
    )

    cross_run_parser = subparsers.add_parser(
        "cross-run-replace-agent",
        help=(
            "Import an agent from one finished run into another at a chosen "
            "round boundary, retaining its full pydantic-ai history"
        ),
    )
    cross_run_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario both source runs belong to",
    )
    cross_run_parser.add_argument(
        "--source-a-run-dir",
        type=str,
        required=True,
        help="Path to the target run directory whose timeline is being modified",
    )
    cross_run_parser.add_argument(
        "--source-b-run-dir",
        type=str,
        required=True,
        help="Path to the run directory the imported agent comes from",
    )
    cross_run_parser.add_argument(
        "--round-start",
        dest="round_start",
        type=int,
        required=True,
        help=(
            "Round number in source A that the resumed simulation should "
            "re-enter. Rewinds source A to the boundary just before this round."
        ),
    )
    cross_run_parser.add_argument(
        "--source-b-round-end",
        dest="source_b_round_end",
        type=int,
        default=None,
        help=(
            "Last round of source B whose events feed into the imported "
            "agent's history. Defaults to min(round_start - 1, B_max_round) "
            "so the imported agent gets all of B's history without exceeding "
            "what B actually played."
        ),
    )
    cross_run_parser.add_argument(
        "--replaced-agent-id",
        type=str,
        required=True,
        help=(
            "agent_id of the agent slot in source A to fill with the imported "
            "agent (must also exist in source B)"
        ),
    )
    cross_run_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override the imported agent's model (defaults to source B's model)",
    )
    cross_run_parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=["anthropic", "openai", "google-gla", "ollama", "self-hosted"],
        help="Override the imported agent's provider (defaults to source B's provider)",
    )
    cross_run_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    cross_run_parser.add_argument(
        "--knobs",
        type=str,
        help="Optional path to a JSON file with scenario knob overrides",
    )
    cross_run_parser.add_argument(
        "--visible-history-channel",
        dest="visible_history_channels",
        action="append",
        default=None,
        help=(
            "Channel ID for which the imported agent retains visibility of "
            "prior source-A messages on resume. Repeatable. When omitted, "
            "the per-channel defaults from source A's "
            "`replace_agent_default_channel_visibility` knob are used."
        ),
    )
    cross_run_parser.add_argument(
        "--rounds-after-swap",
        dest="rounds_after_swap",
        type=int,
        default=None,
        help=(
            "Number of rounds the resumed simulation will play after the "
            "replacement boundary. round_count is set to round_start + "
            "rounds_after_swap. When omitted, defaults to "
            "source_a_round_count - round_start."
        ),
    )

    resume_parser = subparsers.add_parser(
        "resume-at-round",
        help=(
            "Clone a finished run at the start of a chosen round and resume "
            "without replacing any agent; every agent keeps its full "
            "reconstructed history. Optional knob overrides are merged onto "
            "the source's scenario_config so the resumed simulation can flip "
            "postmortem, add scheduled_events, extend round_count, etc."
        ),
    )
    resume_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the source run belongs to",
    )
    resume_parser.add_argument(
        "--source-run-dir",
        type=str,
        required=True,
        help="Path to the source run directory (e.g. runs/veyru/1742234567)",
    )
    resume_parser.add_argument(
        "--round-start",
        dest="round_start",
        type=int,
        required=True,
        help=(
            "Round number that the resumed simulation should re-enter. "
            "Rewinds to the source's RoundAdvanced commit for that round."
        ),
    )
    resume_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    resume_parser.add_argument(
        "--knobs",
        type=str,
        help=(
            "Optional path to a JSON file with scenario knob overrides. "
            "Shallow-merged onto the source's scenario_config; useful for "
            "flipping postmortem_enabled, scheduling post-hoc swaps via "
            "scheduled_events, or extending round_count beyond the source."
        ),
    )
    resume_parser.add_argument(
        "--rounds-after-resume",
        dest="rounds_after_resume",
        type=int,
        default=None,
        help=(
            "Number of rounds the resumed simulation will play after the "
            "resume boundary. round_count is set to round_start + "
            "rounds_after_resume. When omitted, defaults to "
            "source_round_count - round_start (the remaining rounds in the "
            "original run after the resume boundary)."
        ),
    )

    login_parser = subparsers.add_parser(
        "login",
        help=(
            "Authenticate the CLI against a remote schmidt server via OAuth 2.0 "
            "PKCE. Opens a browser to the Clerk-gated consent page; the CLI's "
            "loopback server collects the code and writes the resulting tokens "
            "to ~/.schmidt/credentials.json."
        ),
    )
    login_parser.add_argument(
        "--url",
        dest="url",
        type=str,
        required=True,
        help=(
            "Base URL of the schmidt backend to authenticate against "
            "(e.g. https://schmidtsciencesapi.up.railway.app)."
        ),
    )
    login_parser.add_argument(
        "--timeout",
        dest="timeout_seconds",
        type=float,
        default=300.0,
        help="Seconds to wait for the OAuth callback before aborting (default: 300).",
    )

    push_parser = subparsers.add_parser(
        "push-to-prod",
        help=(
            "Walk the local runs directory, diff against the remote schmidt "
            "server (filtered by label + has-report), and POST each missing "
            "run's bundle to /api/g/{slug}/runs/import using the OAuth token "
            "from `schmidt login`."
        ),
    )
    push_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        default="./runs",
        help="Root directory of local runs (default: ./runs).",
    )
    push_parser.add_argument(
        "--label",
        dest="labels",
        action="append",
        default=[],
        help=(
            "Require the run's labels.json to contain this label. Repeatable; "
            "all listed labels must be present (AND semantics)."
        ),
    )
    push_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=[],
        help=(
            "Restrict to runs of this scenario (repeatable, OR semantics). "
            "When omitted, every scenario directory is considered."
        ),
    )
    push_parser.add_argument(
        "--include-incomplete",
        dest="include_incomplete",
        action="store_true",
        help=(
            "Sync runs even when their <scenario>_report.json is missing. "
            "Off by default — completed runs (those with an eval report) are "
            "the safe set to sync."
        ),
    )
    push_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print the diff (what would be uploaded) without sending bytes.",
    )
    push_parser.add_argument(
        "--concurrency",
        dest="concurrency",
        type=int,
        default=1,
        help=(
            "Max concurrent uploads (default 1, hard-capped at 4). The export "
            "side holds the bundle bytes in memory, so high concurrency can "
            "overwhelm the laptop on bundles that are still large."
        ),
    )

    return parser


def main() -> None:
    """Parse CLI arguments and dispatch to the ``run``, ``evaluate``, or ``serve`` subcommand."""

    load_dotenv()

    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
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

    if known_args.command == "cross-run-replace-agent":
        args = parser.parse_args()
        asyncio.run(_run_cross_run_replace_agent(args=args))
        return

    if known_args.command == "resume-at-round":
        args = parser.parse_args()
        asyncio.run(_run_resume_at_round(args=args))
        return

    if known_args.command == "login":
        args = parser.parse_args()
        asyncio.run(_run_login(args=args))
        return

    if known_args.command == "push-to-prod":
        args = parser.parse_args()
        asyncio.run(_run_push_to_prod(args=args))
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
            merged_overrides: dict[str, Any] = dict(cast(dict[str, Any], existing_overrides))
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
    """Replace-agent / round-anchored resume manifest fields needed at resume time.

    ``replaced_agent_id`` is ``None`` for a round-anchored resume; the
    resume code path then treats every agent as a non-replaced agent
    (full reconstructed history, no channel-visibility filtering).
    """

    replaced_agent_id: str | None
    channel_visibility: dict[str, ChannelVisibility]
    target_event_id: str
    round_start: int


def _channel_visibility_from_manifest(
    visible_channels: list[str],
    blocked_channels: list[str],
) -> dict[str, ChannelVisibility]:
    """Translate replace-agent manifest channel lists into a visibility dict.

    ``visible_channels`` (channels whose prior history remains visible)
    map to ``ChannelVisibilityFull``. ``blocked_channels`` (channels
    whose tool calls are stripped from the predecessor's history) map
    to ``ChannelVisibilityNone``. Channels not in either list are
    omitted (caller decides default behaviour).
    """
    result: dict[str, ChannelVisibility] = {}
    for channel_id in visible_channels:
        result[channel_id] = ChannelVisibilityFull()
    for channel_id in blocked_channels:
        result[channel_id] = ChannelVisibilityNone()
    return result


def read_replace_manifest_info(run_dir: Path) -> _ReplaceManifestInfo | None:
    """Read ``replace_manifest.json`` if present and project to resume fields."""
    manifest = read_replace_manifest(run_dir=run_dir)
    if manifest is None:
        return None
    return _ReplaceManifestInfo(
        replaced_agent_id=manifest.replaced_agent_id,
        channel_visibility=_channel_visibility_from_manifest(
            visible_channels=list(manifest.channels_with_visible_history),
            blocked_channels=list(manifest.blocked_tool_call_channels),
        ),
        target_event_id=manifest.target_event_id,
        round_start=manifest.round_start,
    )


class _CrossRunManifestInfo(NamedTuple):
    """Cross-run replace-agent manifest fields needed to configure resume."""

    replaced_agent_id: str
    channel_visibility: dict[str, ChannelVisibility]
    target_event_id: str
    round_start: int
    imported_history_path: Path
    source_b_round_end: int
    source_b_cutoff_event_id: str


def _read_cross_run_manifest(run_dir: Path) -> _CrossRunManifestInfo | None:
    """Read ``cross_run_replace_manifest.json`` if present and project to resume fields."""
    manifest = read_cross_run_replace_manifest(run_dir=run_dir)
    if manifest is None:
        return None
    return _CrossRunManifestInfo(
        replaced_agent_id=manifest.replaced_agent_id,
        channel_visibility=_channel_visibility_from_manifest(
            visible_channels=list(manifest.channels_with_visible_history),
            blocked_channels=list(manifest.blocked_tool_call_channels),
        ),
        target_event_id=manifest.target_event_id,
        round_start=manifest.round_start,
        imported_history_path=run_dir / manifest.imported_history_source,
        source_b_round_end=manifest.source_b_round_end,
        source_b_cutoff_event_id=manifest.source_b_cutoff_event_id,
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
        default_provider=args.provider,
    )

    log_path = run_dir / f"{scenario.name()}.jsonl"
    event_bus = EventBus(max_queue_size=EVENT_BUS_MAX_QUEUE_SIZE)

    event_logger = EventLogger(log_path=log_path, event_bus=event_bus)

    resume_state: RewindState | None = None
    if resuming:
        logger.info("Loading rewind state from %s", log_path)
        events = await load_events(log_path=log_path)
        replace_info = read_replace_manifest_info(run_dir=run_dir)
        cross_run_info = _read_cross_run_manifest(run_dir=run_dir)
        agent_filters: dict[str, AgentHistoryFilter] = {}
        if cross_run_info is not None:
            cross_run_resume = await _build_cross_run_resume_state(
                events=events,
                run_dir=run_dir,
                cross_run_info=cross_run_info,
            )
            resume_state = cross_run_resume
            logger.info(
                "Cross-run replace-agent run detected: %s resuming with full Sim B "
                "history (cutoff round=%d), channel_visibility=%s",
                cross_run_info.replaced_agent_id,
                cross_run_info.source_b_round_end,
                cross_run_info.channel_visibility,
            )
        elif replace_info is not None:
            if replace_info.replaced_agent_id is None:
                resume_state = build_rewind_state_at_event(
                    events=events,
                    target_event_id=replace_info.target_event_id,
                    cutoff_round=None,
                    agent_filters={},
                )
                logger.info(
                    "Round-anchored resume detected: resuming at round %d "
                    "with full reconstructed history for every agent",
                    replace_info.round_start,
                )
            else:
                agent_filters[replace_info.replaced_agent_id] = AgentHistoryFilter(
                    tool_calls_only=True,
                    channel_visibility=replace_info.channel_visibility,
                    imported=None,
                )
                base_state = build_rewind_state_at_event(
                    events=events,
                    target_event_id=replace_info.target_event_id,
                    cutoff_round=replace_info.round_start,
                    agent_filters=agent_filters,
                )
                resume_state = base_state._replace(
                    replaced_agent_ids=frozenset({replace_info.replaced_agent_id}),
                    replaced_agent_channel_visibility={
                        replace_info.replaced_agent_id: replace_info.channel_visibility,
                    },
                )
                logger.info(
                    "Replace-agent run detected: %s resuming with channel_visibility=%s",
                    replace_info.replaced_agent_id,
                    replace_info.channel_visibility,
                )
        else:
            resume_state = build_rewind_state_from_last_message(
                events=events,
                agent_filters=agent_filters,
            )
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
        log_path=log_path,
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
    """Run the specified metrics against a simulation log and write a JSON report.

    Reconstructs the scenario from the config stored in the JSONL event log,
    so the evaluate command does not need scenario-specific CLI flags.
    Writes an eval manifest while running so the web UI can detect progress.
    """
    metric_names = args.metrics.split(",")
    run_dir = Path(args.run_dir)
    log_path = run_dir / f"{args.scenario_name}.jsonl"
    report_path = run_dir / f"{args.scenario_name}_report.json"

    events = await load_events(log_path=log_path)
    config = extract_scenario_config(events=events)
    scenario = scenario_cls.create_from_config(config=config)

    options = MetricRunOptions(
        probe_round=args.probe_round,
        probe_replicas=args.probe_replicas,
        ontology_path=Path(args.ontology_path) if args.ontology_path else None,
    )

    write_eval_manifest(run_dir=run_dir, pid=os.getpid())
    try:
        logger.info("Evaluating %s with metrics: %s", args.scenario_name, args.metrics)
        await scenario.run_evaluation(
            log_path=log_path,
            metric_names=metric_names,
            report_path=report_path,
            model=args.model,
            provider_name=args.provider,
            inference_provider=args.inference_provider,
            reasoning_effort=getattr(args, "reasoning_effort", None),
            options=options,
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


async def _run_resume_at_round(args: argparse.Namespace) -> None:
    """Drive the round-anchored resume operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and forwards them to
    the shared replace-agent core with ``replaced_agent_id=None`` so no
    agent is restarted. Every agent keeps its full reconstructed history
    on resume.
    """
    knobs: dict[str, Any] | None = None
    if args.knobs is not None:
        knobs = json.loads(Path(args.knobs).read_text())

    source_run_dir = Path(args.source_run_dir).resolve()

    logger.info(
        "Resume-at-round: source=%s round_start=%d",
        source_run_dir,
        args.round_start,
    )

    request = ReplaceAgentCoreRequest(
        source_run_dir=source_run_dir,
        scenario_name=args.scenario_name,
        round_start=args.round_start,
        rounds_after_swap=args.rounds_after_resume,
        replaced_agent_id=None,
        model=None,
        provider=None,
        knobs=knobs,
        channels_with_visible_history=None,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"resume-at-round failed: {exc}") from exc

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
                    str(channel_id): bool(visible)
                    for channel_id, visible in cast(dict[Any, Any], raw).items()
                }
        elif isinstance(event, AgentRegistered) and event.agent_id == replaced_agent_id:
            agent_channels = list(event.channel_ids)

    return [channel_id for channel_id in agent_channels if visibility_map.get(channel_id, True)]


async def _resolve_imported_model_from_source_b(
    source_b_run_dir: Path,
    scenario_name: str,
    replaced_agent_id: str,
) -> tuple[str, str]:
    """Read source B's ``AgentRegistered`` for the replaced agent.

    Returns ``(model, provider)``. Raises ``SystemExit`` if the agent is
    missing — the orchestrator will catch the same case later, but this
    gives a clearer CLI error message.
    """
    log_path = source_b_run_dir / f"{scenario_name}.jsonl"
    events = await load_events(log_path=log_path)
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id == replaced_agent_id:
            return event.model, event.provider
    raise SystemExit(
        f"cross-run-replace-agent: agent {replaced_agent_id!r} not found in "
        f"source B run {source_b_run_dir}"
    )


async def _resolve_source_b_max_round(source_b_run_dir: Path, scenario_name: str) -> int:
    """Return the highest ``RoundAdvanced.round_number`` observed in source B.

    Used to clamp the default ``source_b_round_end`` to source B's
    actual reach when source A's swap point is past source B's tail.
    Raises ``SystemExit`` if source B has no ``RoundAdvanced`` events.
    """
    log_path = source_b_run_dir / f"{scenario_name}.jsonl"
    events = await load_events(log_path=log_path)
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number > max_round:
            max_round = event.round_number
    if max_round == 0:
        raise SystemExit(
            f"cross-run-replace-agent: source B run {source_b_run_dir} has no RoundAdvanced events"
        )
    return max_round


async def _run_cross_run_replace_agent(args: argparse.Namespace) -> None:
    """Drive the cross-run replace-agent operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and resolves the
    visible-history channel list (explicit ``--visible-history-channel``
    flags, or source A's per-channel defaults), defaults
    ``--source-b-round-end`` to ``min(round_start - 1, B_max_round)``
    so the imported agent gets the largest possible slice of source B's
    history without exceeding what B actually played, calls the shared
    helper, and prints the new run ID and run dir on success.
    """
    knobs: dict[str, Any] | None = None
    if args.knobs is not None:
        knobs = json.loads(Path(args.knobs).read_text())

    source_a_run_dir = Path(args.source_a_run_dir).resolve()
    source_b_run_dir = Path(args.source_b_run_dir).resolve()

    if args.visible_history_channels is None:
        visible_channels = await _resolve_default_visible_channels(
            source_run_dir=source_a_run_dir,
            scenario_name=args.scenario_name,
            replaced_agent_id=args.replaced_agent_id,
        )
    else:
        visible_channels = list(args.visible_history_channels)

    if args.source_b_round_end is None:
        source_b_max_round = await _resolve_source_b_max_round(
            source_b_run_dir=source_b_run_dir,
            scenario_name=args.scenario_name,
        )
        source_b_round_end = min(args.round_start - 1, source_b_max_round)
    else:
        source_b_round_end = args.source_b_round_end

    if (args.model is None) != (args.provider is None):
        raise SystemExit(
            "cross-run-replace-agent: --model and --provider must be provided "
            "together (both or neither)"
        )
    if args.model is None:
        model, provider = await _resolve_imported_model_from_source_b(
            source_b_run_dir=source_b_run_dir,
            scenario_name=args.scenario_name,
            replaced_agent_id=args.replaced_agent_id,
        )
    else:
        model = args.model
        provider = args.provider

    logger.info(
        "Cross-run replace-agent: replaced=%s round_start=%d source_b_round_end=%d "
        "visible_channels=%s model=%s provider=%s",
        args.replaced_agent_id,
        args.round_start,
        source_b_round_end,
        visible_channels,
        model,
        provider,
    )

    request = CrossRunCoreRequest(
        source_a_run_dir=source_a_run_dir,
        source_b_run_dir=source_b_run_dir,
        scenario_name=args.scenario_name,
        round_start=args.round_start,
        source_b_round_end=source_b_round_end,
        rounds_after_swap=args.rounds_after_swap,
        replaced_agent_id=args.replaced_agent_id,
        model=model,
        provider=provider,
        knobs=knobs,
        channels_with_visible_history=visible_channels,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await cross_run_replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"cross-run-replace-agent failed: {exc}") from exc

    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")


async def _build_cross_run_resume_state(
    events: list[SimulationEvent],
    run_dir: Path,
    cross_run_info: _CrossRunManifestInfo,
) -> RewindState:
    """Build the rewind state for a cross-run replace-agent resume.

    Loads source B's events from ``imported_history_path``, computes
    the cutoff timestamp (Sim B's ``RoundAdvanced(source_b_round_end +
    1)`` event, or Sim B's last event when Sim B did not advance
    further), and constructs an ``AgentHistoryFilter`` that redirects
    the imported agent's history reconstruction to source B's events.
    Replaced-agent channel visibility on source A is applied by the
    caller via ``replaced_agent_channel_visibility``.
    """
    imported_events = await load_events(log_path=cross_run_info.imported_history_path)
    if cross_run_info.source_b_cutoff_event_id:
        imported_target_timestamp = next(
            event.timestamp
            for event in imported_events
            if event.event_id == cross_run_info.source_b_cutoff_event_id
        )
    else:
        imported_target_timestamp = imported_events[-1].timestamp

    agent_filters: dict[str, AgentHistoryFilter] = {
        cross_run_info.replaced_agent_id: AgentHistoryFilter(
            tool_calls_only=False,
            channel_visibility=cross_run_info.channel_visibility,
            imported=ImportedHistory(
                events=tuple(imported_events),
                target_timestamp=imported_target_timestamp,
                cutoff_round=cross_run_info.source_b_round_end + 1,
            ),
        )
    }
    base_state = build_rewind_state_at_event(
        events=events,
        target_event_id=cross_run_info.target_event_id,
        cutoff_round=cross_run_info.round_start,
        agent_filters=agent_filters,
    )
    _ = run_dir
    return base_state._replace(
        replaced_agent_ids=frozenset({cross_run_info.replaced_agent_id}),
        replaced_agent_channel_visibility={
            cross_run_info.replaced_agent_id: cross_run_info.channel_visibility,
        },
    )


async def _run_login(args: argparse.Namespace) -> None:
    """Drive the ``schmidt login`` subcommand."""
    try:
        credentials = await run_login(
            issuer_url=args.url,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        logger.exception("Login failed")
        raise SystemExit(f"Login failed: {exc}") from exc
    print(
        f"Logged in to {credentials.issuer_url} as group "
        f"{credentials.group_slug!r}. "
        f"Credentials saved to {CREDENTIALS_PATH}."
    )


async def _run_push_to_prod(args: argparse.Namespace) -> None:
    """Drive the ``schmidt push-to-prod`` subcommand."""
    concurrency = max(1, min(int(args.concurrency), 4))
    scenarios_arg: list[str] = args.scenarios
    scenarios = frozenset(scenarios_arg) if scenarios_arg else None
    spec = PushSpec(
        runs_dir=Path(args.runs_dir),
        labels=frozenset(args.labels),
        scenarios=scenarios,
        require_report=not args.include_incomplete,
        dry_run=args.dry_run,
        concurrency=concurrency,
    )
    tally = await run_push_to_prod(spec=spec)
    print(
        f"Done. uploaded={len(tally.uploaded)}  "
        f"skipped={len(tally.skipped)}  "
        f"failed={len(tally.failed)}"
    )
    if tally.failed:
        raise SystemExit(1)
