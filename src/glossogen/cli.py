"""Command-line interface for the glossogen simulation runner.

Defines the ``glossogen`` CLI with three subcommands:

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
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, cast

import uvicorn
from pydantic import ValidationError

from glossogen.autonomous_supervisor import AutonomousSupervisor
from glossogen.config_overrides import (
    apply_overrides,
    normalize_agent_overrides,
    parse_overrides,
    split_agent_overrides,
    validate_agent_override_ids,
)
from glossogen.cross_run_replace_agent import CrossRunReplaceAgentRequest as CrossRunCoreRequest
from glossogen.cross_run_replace_agent import cross_run_replace_agent_in_run
from glossogen.db.local_tenant import LOCAL_GROUP_SLUG
from glossogen.db.run_registry import register_run_standalone
from glossogen.dotenv_loader import load_env_from_working_directory
from glossogen.eval_manifest import delete_eval_manifest, write_eval_manifest
from glossogen.evaluation.log_reader import extract_scenario_config, load_events
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.scenario_evaluation_runner import run_scenario_evaluation
from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.frontend_container import (
    allow_ui_origin,
    default_frontend_image,
    start_frontend_container,
    stop_frontend_container,
)
from glossogen.knob_filter import knob_filter_problem
from glossogen.knobs_resolution import resolve_knobs_config, resolve_knobs_overrides
from glossogen.logging_format import EventBusLogHandler, JsonLineFormatter
from glossogen.message_rewind import RewindState
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import (
    AgentRegistered,
    RoundAdvanced,
    RunStatus,
    SimulationStarted,
)
from glossogen.oauth_client import CREDENTIALS_PATH, run_login
from glossogen.port_allocator import find_free_port
from glossogen.prod_metadata_sync import MetadataSyncSpec, run_metadata_sync
from glossogen.prod_push import PushSpec, run_push_to_prod
from glossogen.provider_credentials import require_reachable_models
from glossogen.replace_agent import ReplaceAgentRequest as ReplaceAgentCoreRequest
from glossogen.replace_agent import replace_agent_in_run
from glossogen.resume_context_writer import write_resume_context_files
from glossogen.resume_state_loader import (
    load_resume_state,
    read_cross_run_manifest_info,
    read_replace_manifest_info,
)
from glossogen.run_analysis.analysis_field_catalog import build_field_catalog
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_limits import MAX_RESULT_ROWS as MAX_ANALYSIS_RESULT_ROWS
from glossogen.run_analysis.analysis_query_engine import run_analysis_query
from glossogen.run_analysis.analysis_query_models import AnalysisQuerySpec, ResultSort
from glossogen.run_analysis.analysis_run_record import load_analysis_records
from glossogen.run_analysis.analysis_spec_parsing import (
    AnalysisSpecError,
    parse_filter,
    parse_measure,
)
from glossogen.run_analysis.analysis_text_table import render_field_catalog, render_text_table
from glossogen.run_archive import claim_run_dir, resume_round_from_log
from glossogen.run_config_validation import validate_run_config
from glossogen.run_export.csv_export_archive import (
    build_export_frames,
    build_legend_frame,
    write_frames_to_directory,
)
from glossogen.run_export.export_column_catalog import build_export_preview
from glossogen.run_export.export_limits import MAX_EXPORT_RUN_COUNT, ExportTooLargeError
from glossogen.run_export.export_request_models import (
    CsvExportRequest,
    ExplicitRunSelection,
    ExportFrame,
    FilterRunSelection,
    RunSelection,
)
from glossogen.run_export.export_run_record import load_export_run_records
from glossogen.run_export.run_selection_resolution import resolve_selection
from glossogen.run_export.runs_zip_archive import write_runs_zip
from glossogen.runners.pydantic_ai_runner import PydanticAIRunner
from glossogen.runtime.game_clock import minimum_duration_elapsed, wall_clock_phase_timeout
from glossogen.runtime.mcp_transport import ServeOverHttp
from glossogen.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_loader import available_scenario_names, get_scenario_class
from glossogen.scenario_package_checks import check_scenario_package
from glossogen.scenario_path_loader import registered_for_checks
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_scaffold import (
    ScaffoldError,
    default_glossogen_ref,
    write_scenario_package,
)
from glossogen.scenario_target import ScenarioPathError, resolve_check_target
from glossogen.server.runs.discovery import discover_runs
from glossogen.server.runs.models import RunSummary
from glossogen.simulation_server import start_simulation_server, stop_simulation_server
from glossogen.telemetry_bootstrap import flush_telemetry, init_langfuse_telemetry
from glossogen.telemetry_settings import load_telemetry_settings
from glossogen.thread_export.export_agent_thread import (
    ThreadExportFormat,
    export_agent_thread_from_run_dir,
)
from glossogen.token_pricing import list_providers

logger = logging.getLogger(__name__)

EVENT_BUS_MAX_QUEUE_SIZE = 1000
DEFAULT_MAX_AGENT_TURNS = 200


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level parser and all subcommand parsers."""
    parser = argparse.ArgumentParser(prog="glossogen")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scenario_names = available_scenario_names()

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
            "Path to a consolidated communication-feature ontology JSON file, "
            "pinning communication_feature_presence to one ontology. Omit it and "
            "the metric reads the most recently modified JSON under "
            "runs/<scenario>/_ontology/."
        ),
    )
    evaluate_parser.add_argument(
        "--knobs",
        type=str,
        default=None,
        help=(
            "Optional scenario knob overrides (a preset name or a path to a "
            "JSON file) merged onto the run's recorded scenario_config before validating the "
            "scenario. Useful for evaluating runs whose schema gained a "
            "required knob after the run was created (e.g. veyru's "
            "easy_round_numbers on pre-existing baselines)."
        ),
    )

    export_parser = subparsers.add_parser(
        "export",
        help="Export many runs as CSV tables or as a zip of their run folders",
    )
    export_parser.add_argument(
        "--runs-dir",
        type=str,
        default="./runs",
        help="Directory holding the run data (default: ./runs)",
    )
    export_parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Directory to write the export into (created if absent)",
    )
    _add_run_selection_flags(parser=export_parser, verb="Export")
    export_parser.add_argument(
        "--frames",
        type=str,
        default="run_level,round_level,agent_level",
        help=(
            "Comma-separated tables to emit: run_level, round_level, agent_level, "
            "message_level, round_context (default: the first three; the last two "
            "read every run's event log)"
        ),
    )
    export_parser.add_argument(
        "--include-metric-summaries",
        action="store_true",
        help=(
            "Add each metric's unit and one-line summary at run level, and its "
            "per-observation note on the round and agent tables"
        ),
    )
    export_parser.add_argument(
        "--no-repeat-run-columns",
        dest="repeat_run_columns",
        action="store_false",
        help="Keep the long tables narrow, joining back on run_id instead",
    )
    export_parser.add_argument(
        "--raw",
        action="store_true",
        help="Also write a zip of the selected runs' folders",
    )
    export_parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Keep debug and stdout logs in the raw zip (they are dropped by default)",
    )
    export_parser.add_argument(
        "--max-runs",
        type=int,
        default=MAX_EXPORT_RUN_COUNT,
        help=f"Refuse a selection larger than this (default: {MAX_EXPORT_RUN_COUNT})",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Group and aggregate many runs' metrics into one table",
    )
    analyze_parser.add_argument(
        "--runs-dir",
        type=str,
        default="./runs",
        help="Directory holding the run data (default: ./runs)",
    )
    _add_run_selection_flags(parser=analyze_parser, verb="Analyze")
    analyze_parser.add_argument(
        "--grain",
        type=str,
        default=AnalysisGrain.RUN.value,
        choices=[grain.value for grain in AnalysisGrain],
        help="What one observation is (default: run)",
    )
    analyze_parser.add_argument(
        "--group-by",
        action="append",
        default=[],
        metavar="DIMENSION",
        help=(
            "Group on this dimension (repeatable, at most two: the x axis then the "
            "series). Omit to aggregate the whole selection into one row."
        ),
    )
    analyze_parser.add_argument(
        "--measure",
        action="append",
        default=[],
        metavar="SPEC",
        help=(
            "What to aggregate, as key:aggregate (a metric) or source:key:aggregate "
            "(e.g. run_column:total_cost_usd:sum). Repeatable."
        ),
    )
    analyze_parser.add_argument(
        "--filter",
        action="append",
        default=[],
        dest="dimension_filter",
        metavar="SPEC",
        help=(
            "Narrow the observations, as key:operator[:values] "
            "(e.g. knob.round_time_budget_seconds:gte:1000). Repeatable."
        ),
    )
    analyze_parser.add_argument(
        "--sort",
        type=str,
        default=ResultSort.GROUP.value,
        choices=[sort.value for sort in ResultSort],
        help="Row order (default: by the group values, numerically where they are numbers)",
    )
    analyze_parser.add_argument(
        "--sort-measure",
        type=int,
        default=0,
        metavar="INDEX",
        help="Which --measure a measure sort orders by, counting from 0 (default: 0)",
    )
    analyze_parser.add_argument(
        "--limit",
        type=int,
        default=MAX_ANALYSIS_RESULT_ROWS,
        help=f"Keep at most this many groups (default: {MAX_ANALYSIS_RESULT_ROWS})",
    )
    analyze_parser.add_argument(
        "--list-fields",
        action="store_true",
        help="Print the dimensions and measures this selection carries, and stop",
    )
    analyze_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print the result as JSON instead of an aligned table",
    )
    analyze_parser.add_argument(
        "--max-runs",
        type=int,
        default=MAX_EXPORT_RUN_COUNT,
        help=f"Refuse a selection larger than this (default: {MAX_EXPORT_RUN_COUNT})",
    )

    export_thread_parser = subparsers.add_parser(
        "export-thread",
        help="Export one agent's reconstructed thread as a provider-native API request body",
    )
    export_thread_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the run belongs to",
    )
    export_thread_parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to the run directory (e.g. runs/veyru/1742234567)",
    )
    export_thread_parser.add_argument(
        "--agent-id",
        type=str,
        required=True,
        help="Agent whose thread to export (e.g. field_observer)",
    )
    export_thread_parser.add_argument(
        "--round",
        dest="round",
        type=int,
        default=None,
        help=(
            "Exclusive round cutoff: drops every tool call whose round_number >= R, "
            "so the exported history covers rounds 1..R-1. Pass --round=R+1 to capture "
            "the agent's state at the END of round R. Omit for the full end-of-run thread."
        ),
    )
    export_thread_parser.add_argument(
        "--format",
        dest="format",
        type=str,
        choices=["anthropic", "openai"],
        default=None,
        help=(
            "Target provider format for the request body. Defaults to the format "
            "matching the agent's own provider (anthropic->anthropic, "
            "openai/self-hosted->openai)."
        ),
    )
    export_thread_parser.add_argument(
        "--include-thinking",
        dest="include_thinking",
        action="store_true",
        help=(
            "Keep reasoning/thinking parts as text blocks. Dropped by default because "
            "replaying provider reasoning blocks in a raw request requires signatures."
        ),
    )
    export_thread_parser.add_argument(
        "--flatten-tools",
        dest="flatten_tools",
        action="store_true",
        help=(
            "Render tool calls and results as plain text instead of native tool_use/"
            "tool_result blocks, producing a body that needs no tool configuration."
        ),
    )
    export_thread_parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Write the export JSON to this path. Omit to print it to stdout.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Check a scenario against the contract, without launching it",
    )
    validate_parser.add_argument(
        "target",
        type=str,
        help=(
            "An installed scenario's name, or the directory holding a package's "
            "pyproject.toml, which is the one `new-scenario` created rather than the "
            f"module inside it. Installed: {', '.join(scenario_names)}"
        ),
    )

    new_scenario_parser = subparsers.add_parser(
        "new-scenario",
        help="Write a runnable scenario package of your own",
    )
    new_scenario_parser.add_argument(
        "scenario_name",
        type=str,
        help=(
            "Name of the scenario to create. Becomes the package directory, the "
            "module, the entry-point key and what name() returns, so it has to be "
            "a lowercase identifier"
        ),
    )
    new_scenario_parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Directory to write the new package into",
    )
    new_scenario_parser.add_argument(
        "--glossogen-ref",
        type=str,
        default=None,
        help=(
            "Git ref the generated pyproject.toml pins glossogen to. Defaults to "
            "the release tag matching the installed version"
        ),
    )

    serve_parser = subparsers.add_parser("serve", help="Start the web server")
    serve_parser.add_argument(
        "--runs-dir", type=str, required=True, help="Root directory containing simulation runs"
    )
    serve_parser.add_argument("--port", type=int, required=True, help="Port to listen on")
    serve_parser.add_argument(
        "--ui-port",
        type=int,
        default=None,
        help=(
            "Also start the web UI on this port, from the published frontend "
            "image, wired to this server. Requires Docker. Omit to run the "
            "backend alone."
        ),
    )
    serve_parser.add_argument(
        "--ui-image",
        type=str,
        default=None,
        help=(
            "Frontend image to run with --ui-port. Defaults to the latest "
            "published one; pass a version tag to pin the UI to a release."
        ),
    )

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
        "--after-round",
        dest="after_round",
        type=int,
        required=True,
        help=(
            "The fork boundary: rounds 1..N stay complete, verdict and "
            "postmortem included, and the replacement agent enters round N+1."
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
        help=(
            "Optional scenario knob overrides: a preset name the scenario "
            "ships, or a path to a JSON file"
        ),
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
        "--rounds-after",
        dest="rounds_after",
        type=int,
        default=None,
        help=(
            "Number of new rounds the fork plays. round_count is set to "
            "after_round + rounds_after. When omitted, defaults to "
            "source_round_count - after_round (the source rounds past the "
            "boundary); forking after the source's final round requires an "
            "explicit value."
        ),
    )
    replace_parser.add_argument(
        "--history-from-round",
        dest="history_from_round",
        type=int,
        default=None,
        help=(
            "Window the replaced agent's visible-channel history: it sees those "
            "channels only from this round onward (read_channel returns dropped, "
            "send_message kept from this round). Applies to every channel in the "
            "resolved visible set. For the previous P rounds before the boundary, "
            "pass after_round - P + 1. When omitted, visible channels keep full "
            "prior history."
        ),
    )
    replace_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
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
        "--after-round",
        dest="after_round",
        type=int,
        required=True,
        help=(
            "The fork boundary in source A: rounds 1..N stay complete and the "
            "imported agent enters round N+1."
        ),
    )
    cross_run_parser.add_argument(
        "--source-b-round-end",
        dest="source_b_round_end",
        type=int,
        default=None,
        help=(
            "Last round of source B whose events feed into the imported "
            "agent's history. Defaults to min(after_round, B_max_round) "
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
        help=(
            "Optional scenario knob overrides: a preset name the scenario "
            "ships, or a path to a JSON file"
        ),
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
        "--rounds-after",
        dest="rounds_after",
        type=int,
        default=None,
        help=(
            "Number of new rounds the fork plays. round_count is set to "
            "after_round + rounds_after. When omitted, defaults to "
            "source_a_round_count - after_round."
        ),
    )
    cross_run_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
    )

    fork_parser = subparsers.add_parser(
        "fork-at-round",
        help=(
            "Clone a finished run keeping rounds 1..N complete and play round "
            "N+1 onward in a new run directory, without replacing any agent; "
            "every agent keeps its full reconstructed history. --rounds-after "
            "sets how far it plays, past the source's own end included. "
            "Optional knob overrides are merged onto the source's "
            "scenario_config so the fork can flip postmortem or add "
            "scheduled_events; round_count is derived from the flags and "
            "cannot be overridden."
        ),
    )
    fork_parser.add_argument(
        "scenario_name",
        type=str,
        choices=scenario_names,
        help="Name of the scenario the source run belongs to",
    )
    fork_parser.add_argument(
        "--source-run-dir",
        type=str,
        required=True,
        help="Path to the source run directory (e.g. runs/veyru/1742234567)",
    )
    fork_parser.add_argument(
        "--after-round",
        dest="after_round",
        type=int,
        required=True,
        help=(
            "The fork boundary: rounds 1..N stay complete, verdict and "
            "postmortem included, and the fork plays round N+1 onward."
        ),
    )
    fork_parser.add_argument(
        "--runs-dir",
        type=str,
        required=True,
        help="Root directory where the new run is written",
    )
    fork_parser.add_argument(
        "--knobs",
        type=str,
        help=(
            "Optional scenario knob overrides: a preset name the scenario "
            "ships, or a path to a JSON file. "
            "Shallow-merged onto the source's scenario_config; useful for "
            "flipping postmortem_enabled, scheduling post-hoc swaps via "
            "scheduled_events, or extending round_count beyond the source."
        ),
    )
    fork_parser.add_argument(
        "--rounds-after",
        dest="rounds_after",
        type=int,
        default=None,
        help=(
            "Number of new rounds the fork plays. round_count is set to "
            "after_round + rounds_after. When omitted, defaults to "
            "source_round_count - after_round (the source rounds past the "
            "boundary); forking after the source's final round requires an "
            "explicit value."
        ),
    )
    fork_parser.add_argument(
        "--group-slug",
        type=str,
        default=LOCAL_GROUP_SLUG,
        help=f"Tenant group slug that owns the new run (default: {LOCAL_GROUP_SLUG})",
    )

    login_parser = subparsers.add_parser(
        "login",
        help=(
            "Authenticate the CLI against a remote glossogen server via OAuth 2.0 "
            "PKCE. Opens a browser to the consent page; the CLI's "
            "loopback server collects the code and writes the resulting tokens "
            "to ~/.glossogen/credentials.json."
        ),
    )
    login_parser.add_argument(
        "--url",
        dest="url",
        type=str,
        required=True,
        help=(
            "Base URL of the glossogen backend to authenticate against "
            "(e.g. https://your-backend.example.com)."
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
            "Walk the local runs directory, diff against the remote glossogen "
            "server (filtered by label + has-report), and POST each missing "
            "run's bundle to /api/g/{slug}/runs/import using the OAuth token "
            "from `glossogen login`."
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
            "Max concurrent uploads (default 1, hard-capped at 16). The export "
            "side holds the bundle bytes in memory, so high concurrency can "
            "overwhelm the laptop on bundles that are still large."
        ),
    )

    sync_metadata_parser = subparsers.add_parser(
        "sync-metadata-to-prod",
        help=(
            "Sync local labels onto runs that already exist on prod. Walks "
            "local runs/, diffs each run's labels.json against the labels "
            "the remote returns from /runs, and PUTs the local list onto "
            "/api/g/{slug}/runs/{scenario}/{run_dir_name}/labels for every "
            "drifted run. Local is the source of truth — the PUT replaces "
            "the remote list (use `push-to-prod` for runs that aren't yet "
            "on prod at all)."
        ),
    )
    sync_metadata_parser.add_argument(
        "--runs-dir",
        dest="runs_dir",
        type=str,
        default="./runs",
        help="Root directory of local runs (default: ./runs).",
    )
    sync_metadata_parser.add_argument(
        "--scenario",
        dest="scenarios",
        action="append",
        default=[],
        help=(
            "Restrict to runs of this scenario (repeatable, OR semantics). "
            "When omitted, every scenario directory is considered."
        ),
    )
    sync_metadata_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print the per-run drift without sending any PUTs.",
    )
    sync_metadata_parser.add_argument(
        "--concurrency",
        dest="concurrency",
        type=int,
        default=4,
        help=(
            "Max concurrent PUTs (default 4, hard-capped at 8). Lightweight "
            "compared to bundle uploads because the payload is just the "
            "label list."
        ),
    )

    return parser


def main() -> None:
    """Parse CLI arguments and dispatch to the ``run``, ``evaluate``, or ``serve`` subcommand."""

    load_env_from_working_directory()

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

    if known_args.command == "fork-at-round":
        args = parser.parse_args()
        asyncio.run(_run_fork_at_round(args=args))
        return

    if known_args.command == "login":
        args = parser.parse_args()
        asyncio.run(_run_login(args=args))
        return

    if known_args.command == "push-to-prod":
        args = parser.parse_args()
        asyncio.run(_run_push_to_prod(args=args))
        return

    if known_args.command == "sync-metadata-to-prod":
        args = parser.parse_args()
        asyncio.run(_run_sync_metadata_to_prod(args=args))
        return

    if known_args.command == "validate":
        args = parser.parse_args()
        _run_validate(args=args)
        return

    if known_args.command == "new-scenario":
        args = parser.parse_args()
        _run_new_scenario(args=args)
        return

    if known_args.command == "export":
        args = parser.parse_args()
        asyncio.run(_run_export(args=args))
        return

    if known_args.command == "analyze":
        args = parser.parse_args()
        asyncio.run(_run_analyze(args=args))
        return

    if known_args.command == "export-thread":
        args = parser.parse_args()
        asyncio.run(_run_export_thread(args=args))
        return

    scenario_cls = get_scenario_class(name=known_args.scenario_name)

    # Second pass: parse known flags and capture remaining key=value overrides.
    args, remaining = parser.parse_known_args()

    if args.command == "run":
        if args.resume is None and args.runs_dir is None:
            parser.error("--runs-dir is required unless --resume is given")
        config = _build_run_config(args=args, remaining=remaining, scenario_cls=scenario_cls)
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
        try:
            require_reachable_models(
                scenario_cls=scenario_cls,
                scenario_config=validated.scenario_config,
                agent_overrides=validated.normalized_agent_overrides,
                default_model=args.model,
                default_provider=args.provider,
                first_round=first_round_of(resume_dir=args.resume, scenario_cls=scenario_cls),
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
    else:
        asyncio.run(_run_evaluation(args=args, scenario_cls=scenario_cls))


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


async def _register_derived_run(
    scenario: str,
    run_dir_name: str,
    source_run_scenario: str,
    source_run_dir_name: str,
    group_slug: str,
) -> None:
    """Insert a ``runs`` row for a derived run (replace-agent / fork-at-round / cross-run).

    The detached ``glossogen run --resume`` subprocess that actually executes the
    derived simulation skips registration (it inherits the run dir from this
    parent CLI), so the parent has to register on its behalf or the FE never
    sees the run.
    """
    try:
        await register_run_standalone(
            group_slug=group_slug,
            scenario=scenario,
            run_dir_name=run_dir_name,
            status=RunStatus.STARTING.value,
            created_at=datetime.now(tz=UTC),
            created_by_user_id=None,
            source_run_scenario=source_run_scenario,
            source_run_dir_name=source_run_dir_name,
        )
    except Exception:
        logger.exception("Failed to register derived run %s/%s in Postgres", scenario, run_dir_name)


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
        default_provider=args.provider,
    )

    log_path = run_dir / f"{scenario.name()}.jsonl"
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

    mcp_port = find_free_port()

    supervisor = AutonomousSupervisor(
        scenario=scenario,
        agent_configs=agents,
        event_logger=event_logger,
        mcp_transport=ServeOverHttp(port=mcp_port),
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
        if telemetry_handle is not None:
            flush_telemetry(handle=telemetry_handle)

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
    config: dict[str, Any] = dict(extract_scenario_config(events=events))
    overrides = resolve_knobs_overrides(scenario_cls=scenario_cls, requested=args.knobs)
    if overrides is not None:
        config.update(overrides.config)
        logger.info(
            "Merged --knobs overrides from %s into scenario_config: keys=%s",
            overrides.source,
            sorted(overrides.config),
        )
    scenario = scenario_cls.create_from_config(config=config)

    options = MetricRunOptions(
        probe_round=args.probe_round,
        probe_replicas=args.probe_replicas,
        ontology_path=Path(args.ontology_path) if args.ontology_path else None,
    )

    write_eval_manifest(run_dir=run_dir, pid=os.getpid())
    try:
        logger.info("Evaluating %s with metrics: %s", args.scenario_name, args.metrics)
        await run_scenario_evaluation(
            scenario=scenario,
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


def _add_run_selection_flags(parser: argparse.ArgumentParser, verb: str) -> None:
    """Add the flags :func:`_export_selection_from_args` reads.

    Shared by `export` and `analyze` because that function reads them off
    whichever namespace it is given: a parser missing one raises AttributeError
    on every invocation of its command, not only on the ones that pass it.

    ``verb`` names the command in the ``--run-id`` help, the one line that
    differed between the two copies this replaced.
    """
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="NAME",
        help="Only these scenarios (repeatable). Omit for every scenario.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="LABEL",
        help="Only runs carrying every one of these labels (repeatable)",
    )
    parser.add_argument(
        "--run-id-contains",
        type=str,
        default=None,
        help="Only runs whose scenario/run_dir_name id contains this substring",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        metavar="ID",
        help=(
            f"{verb} exactly these run ids (repeatable, e.g. veyru/1777638061). "
            "Cannot be combined with the filter flags."
        ),
    )
    parser.add_argument(
        "--knob",
        action="append",
        default=[],
        metavar="CONDITION",
        help=(
            "Only runs whose recorded scenario_config satisfies this condition, "
            "written <knob><operator><value> with the operator one of "
            "= != >= <= > <. Quote it, or the shell reads > and < as redirection: "
            "--knob 'round_time_budget_seconds>=200' --knob postmortem_enabled=true. "
            "Repeatable; every condition must hold."
        ),
    )
    parser.add_argument(
        "--contains-agent-id",
        type=str,
        default=None,
        metavar="AGENT_ID",
        help="Only runs that registered this agent (e.g. field_observer)",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        choices=[status.value for status in RunStatus],
        help="Only runs in this state (e.g. scenario_complete to skip crashed runs)",
    )


def _export_selection_from_args(args: argparse.Namespace) -> RunSelection:
    """Build the selection the flags describe, refusing a mix of the two forms."""
    filter_flags_used = bool(
        args.scenario
        or args.label
        or args.run_id_contains
        or args.status is not None
        or args.contains_agent_id is not None
        or args.knob
    )
    if args.run_id and filter_flags_used:
        raise SystemExit(
            "Pass either --run-id or the filter flags (--scenario / --label / "
            "--run-id-contains / --status / --contains-agent-id / --knob), not both."
        )
    if args.run_id:
        return ExplicitRunSelection(kind="explicit", run_ids=list(args.run_id))
    status = None
    if args.status is not None:
        status = RunStatus(args.status)
    # Checked before building, so the model's own validator never fires here. It
    # would raise, and reporting a mistyped flag through an exception means either
    # a pydantic traceback on stderr or a logging rule broken to avoid one.
    problem = knob_filter_problem(raw_filters=list(args.knob))
    if problem is not None:
        raise SystemExit(problem)
    return FilterRunSelection(
        kind="filters",
        scenario=list(args.scenario),
        labels=list(args.label),
        run_id_contains=args.run_id_contains,
        status=status,
        contains_agent_id=args.contains_agent_id,
        knob=list(args.knob),
    )


def _requested_frames(raw: str) -> list[ExportFrame]:
    """Parse the --frames flag, naming any value that is not a table."""
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise SystemExit("--frames needs at least one table name.")
    valid = {frame.value for frame in ExportFrame}
    unknown = [name for name in names if name not in valid]
    if unknown:
        raise SystemExit(
            f"Unknown table(s): {', '.join(unknown)}. Choose from {', '.join(sorted(valid))}."
        )
    return [ExportFrame(name) for name in names]


async def _run_export(args: argparse.Namespace) -> None:
    """Export many runs as CSV tables, and optionally as a zip of their folders.

    Reads the runs directory directly, so it needs no server and no database. It
    covers runs that were never evaluated and runs still in progress; their metric
    cells are empty rather than zero.
    """
    frames_requested = _requested_frames(raw=args.frames)
    if args.include_logs and not args.raw:
        raise SystemExit("--include-logs only affects the raw zip; pass --raw as well.")

    selection, summaries = await _resolved_local_runs(args=args)
    records = await load_export_run_records(runs=summaries)
    preview = build_export_preview(
        records=records,
        missing_run_ids=[],
        raw_bytes_estimate=None,
    )
    logger.info(
        "Exporting %d runs across %s: %d columns, %d metrics",
        preview.run_count,
        ", ".join(preview.scenario_names),
        len(preview.columns),
        len(preview.metrics),
    )
    if preview.runs_without_report:
        logger.info(
            "%d of them have no evaluation report, so their metric cells are empty",
            len(preview.runs_without_report),
        )

    request = CsvExportRequest(
        selection=selection,
        frames=frames_requested,
        columns=list(dict.fromkeys(column.key for column in preview.columns)),
        metrics=[metric.metric_name for metric in preview.metrics],
        repeat_run_columns=args.repeat_run_columns,
        include_metric_summaries=args.include_metric_summaries,
    )
    out_dir = Path(args.out).resolve()
    written = write_frames_to_directory(
        frames=build_export_frames(records=records, request=request),
        legend=build_legend_frame(records=records, request=request),
        out_dir=out_dir,
    )
    for path in written:
        print(path)

    if args.raw:
        zip_path = out_dir / "runs.zip"
        try:
            with zip_path.open("wb") as handle:
                tally = write_runs_zip(
                    runs=summaries,
                    include_logs=args.include_logs,
                    destination=handle,
                )
        except ExportTooLargeError as exc:
            zip_path.unlink(missing_ok=True)
            raise SystemExit(str(exc)) from exc
        logger.info("Raw zip: %d runs, %d files", tally.run_count, tally.file_count)
        print(zip_path)


class LocalSelection(NamedTuple):
    """The selection the flags describe, and the runs it resolves to on disk."""

    selection: RunSelection
    summaries: list[RunSummary]


async def _resolved_local_runs(args: argparse.Namespace) -> LocalSelection:
    """Resolve the selection the flags describe against a runs directory on disk.

    Shared by the export and the analysis commands: both read the runs directory
    directly, so neither needs a server or a database, and both refuse the same
    three ways (a named run that is not there, a selection matching nothing, and one
    over the run ceiling).
    """
    selection = _export_selection_from_args(args=args)
    runs_dir = Path(args.runs_dir).resolve()
    if not runs_dir.is_dir():
        raise SystemExit(f"No runs directory at {runs_dir}")
    summaries = await discover_runs(runs_dir=runs_dir)
    resolved = resolve_selection(candidates=summaries, selection=selection)

    if resolved.missing_run_ids:
        raise SystemExit(f"No run found for: {', '.join(sorted(resolved.missing_run_ids))}")
    if not resolved.summaries:
        raise SystemExit("That selection matches no runs.")
    if len(resolved.summaries) > args.max_runs:
        raise SystemExit(
            f"That selection is {len(resolved.summaries)} runs, over the --max-runs "
            f"limit of {args.max_runs}."
        )
    return LocalSelection(selection=selection, summaries=resolved.summaries)


def _analysis_spec_from_args(args: argparse.Namespace) -> AnalysisQuerySpec:
    """Build the query spec the flags describe, naming what could not be read."""
    if not args.measure:
        raise SystemExit(
            "Pass at least one --measure (e.g. --measure round_success:mean). "
            "Run with --list-fields to see what this selection carries."
        )
    try:
        measures = [parse_measure(text=text) for text in args.measure]
        filters = [parse_filter(text=text) for text in args.dimension_filter]
    except AnalysisSpecError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        return AnalysisQuerySpec(
            grain=AnalysisGrain(args.grain),
            filters=filters,
            group_by=list(args.group_by),
            measures=measures,
            sort=ResultSort(args.sort),
            sort_measure_index=args.sort_measure,
            limit=args.limit,
        )
    except ValidationError as exc:
        raise SystemExit(str(exc)) from exc


async def _run_analyze(args: argparse.Namespace) -> None:
    """Group and aggregate the selected runs into one table.

    Reads the runs directory directly, so it needs no server and no database, and runs
    the same engine the web UI's charts do.
    """
    summaries = (await _resolved_local_runs(args=args)).summaries
    grain = AnalysisGrain(args.grain)
    records = await load_analysis_records(
        runs=summaries, read_sidecars=grain is AnalysisGrain.KEYED
    )

    if args.list_fields:
        catalog = build_field_catalog(records=records, grain=grain)
        if args.as_json:
            print(catalog.model_dump_json(indent=2))
            return
        print(render_field_catalog(catalog=catalog))
        return

    result = run_analysis_query(records=records, spec=_analysis_spec_from_args(args=args))
    if args.as_json:
        print(result.model_dump_json(indent=2))
        return
    print(render_text_table(result=result))


async def _run_export_thread(args: argparse.Namespace) -> None:
    """Export one agent's reconstructed thread as a provider-native request body.

    Writes the ``ThreadExport`` JSON to ``--out`` (or stdout). The consumer
    appends their own trailing user message (and ``max_tokens`` for Anthropic)
    to ``request`` and POSTs it straight to the provider.
    """
    if args.format == "anthropic":
        output_format: ThreadExportFormat | None = "anthropic_messages"
    elif args.format == "openai":
        output_format = "openai_chat"
    else:
        output_format = None

    export = await export_agent_thread_from_run_dir(
        run_dir=Path(args.run_dir).resolve(),
        scenario_name=args.scenario_name,
        agent_id=args.agent_id,
        cutoff_round=args.round,
        output_format=output_format,
        include_thinking=args.include_thinking,
        flatten_tools=args.flatten_tools,
    )
    payload = export.model_dump_json(indent=2)
    if args.out is None:
        print(payload)
        return
    out_path = Path(args.out)
    out_path.write_text(payload + "\n")
    logger.info(
        "Wrote thread export for agent %s (%s, %d messages) -> %s",
        export.meta.agent_id,
        export.meta.format,
        export.meta.num_messages,
        out_path,
    )


def first_round_of(resume_dir: str | None, scenario_cls: type[SimulationScenario]) -> int:
    """Return the round this launch will open at, which fresh runs answer with 1.

    A resumed run inherits its source's schedule, and the boundaries below where
    it opens are ones the clock will never cross. The run's own log answers for
    a plain ``--resume``; a fork past the source's final round holds no
    ``RoundAdvanced`` for its entry round, so the manifest's entry round wins
    when it is higher.
    """
    if resume_dir is None:
        return 1
    run_dir = Path(resume_dir)
    first_round = resume_round_from_log(log_path=run_dir / f"{scenario_cls.name()}.jsonl")
    replace_info = read_replace_manifest_info(run_dir=run_dir)
    if replace_info is not None:
        first_round = max(first_round, replace_info.entry_round)
    cross_info = read_cross_run_manifest_info(run_dir=run_dir)
    if cross_info is not None:
        first_round = max(first_round, cross_info.entry_round)
    return first_round


def _run_validate(args: argparse.Namespace) -> None:
    """Check a scenario against the contract and report everything that failed.

    Takes a name or a directory. Which one it was decides only how the class is
    found: the contract checks are the same either way. A directory additionally
    gets the package checks, which are about the distribution around the scenario
    and so have nothing to look at once that distribution is installed.

    Exits non-zero when anything failed, so this works as a CI step in whichever
    package ships the scenario.

    Needs no API key, and checks no model's reachability: describing a scenario
    must not require a credential, and a launch checks what it can reach where the
    run's own model and provider are known.
    """
    try:
        target = resolve_check_target(target=args.target)
    except (ScenarioPathError, ValueError) as refusal:
        raise SystemExit(f"FAIL {args.target}: {refusal}") from refusal

    notes = list(target.notes)
    outcomes: list[CheckOutcome] = []
    if target.loaded is None:
        outcomes.extend(check_scenario(scenario_cls=target.scenario_cls))
    else:
        # The package checks run first and outside the registration below, because
        # the collision check has to see the registry as it really is.
        package = check_scenario_package(loaded=target.loaded)
        notes.extend(package.notes)
        with registered_for_checks(loaded=target.loaded):
            outcomes.extend(package.outcomes)
            outcomes.extend(check_scenario(scenario_cls=target.scenario_cls))

    failed = failures(outcomes)
    for outcome in failed:
        where = target.label
        if outcome.preset:
            where = f"{where} [{outcome.preset}]"
        print(f"FAIL {where}: {outcome.check} — {outcome.detail}")
    for note in notes:
        print(f"NOTE {target.label}: {note}")
    if failed:
        # Printed rather than raised with a message, so the summary lands after
        # the failures it counts rather than ahead of them on another stream.
        print(f"{len(failed)} of {len(outcomes)} checks failed for {target.label}.")
        raise SystemExit(1)
    presets = target.scenario_cls.knobs_preset_names()
    print(
        f"{target.label}: {len(outcomes)} checks passed "
        f"across {len(presets)} preset(s): {', '.join(presets)}"
    )


def _run_new_scenario(args: argparse.Namespace) -> None:
    """Write a new scenario package and print what to do with it.

    The next steps are printed rather than left to the README, because their order
    is not obvious: `validate` reads the package's own declaration and so works on
    what was just written, while `pytest` needs the install for the harness.
    """
    ref = args.glossogen_ref
    if ref is None:
        ref = default_glossogen_ref()

    try:
        package = write_scenario_package(
            scenario_name=args.scenario_name,
            target_dir=Path(args.target_dir),
            glossogen_ref=ref,
        )
    except ScaffoldError as refusal:
        raise SystemExit(str(refusal)) from refusal

    print(f"Wrote {len(package.files)} files to {package.package_dir}")
    # Named because it is inferred from the installed version unless it was
    # passed, and it is what the generated package installs glossogen from.
    print(f"Pinned to glossogen {ref}; pass --glossogen-ref to pin another.")
    print(f"  cd {package.package_dir}")
    print("  glossogen validate .            # the contract, before installing anything")
    print('  pip install -e ".[testing]"')
    print("  pytest")


def _run_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI web server, and the web UI when ``--ui-port`` asks for it."""
    logger.info("Starting web server on port %d, runs dir: %s", args.port, args.runs_dir)
    os.environ["GLOSSOGEN_RUNS_DIR"] = args.runs_dir
    if args.ui_port is None:
        _run_uvicorn(port=args.port)
        return

    allow_ui_origin(ui_port=args.ui_port)
    container = start_frontend_container(
        api_port=args.port,
        ui_port=args.ui_port,
        image=_resolve_ui_image(requested_image=args.ui_image),
    )
    logger.info("Web UI at %s", container.url)
    try:
        _run_uvicorn(port=args.port)
    finally:
        stop_frontend_container(container_id=container.container_id)


def _run_uvicorn(port: int) -> None:
    """Serve the FastAPI app until interrupted."""
    uvicorn.run(
        app="glossogen.server.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def _resolve_ui_image(requested_image: str | None) -> str:
    """Return the frontend image to run, defaulting to the installed version's."""
    if requested_image is not None:
        return requested_image
    return default_frontend_image()


def _resolve_knob_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    """Return the `--knobs` overrides for a swap or resume flow, or None.

    Resolves a preset name as well as a path, so the flag reads the same as
    ``--config`` does on ``run``.
    """
    overrides = resolve_knobs_overrides(
        scenario_cls=get_scenario_class(name=args.scenario_name),
        requested=args.knobs,
    )
    if overrides is None:
        return None
    logger.info("Knob overrides from %s", overrides.source)
    return overrides.config


async def _run_replace_agent(args: argparse.Namespace) -> None:
    """Drive the replace-agent operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and resolves the
    visible-history channel list (explicit ``--visible-history-channel``
    flags, or the source run's per-channel defaults), calls the shared
    helper, and prints the new run ID and run dir on success.
    """
    knobs = _resolve_knob_overrides(args=args)

    source_run_dir = Path(args.source_run_dir).resolve()

    if args.visible_history_channels is None:
        visible_channels = await _resolve_default_visible_channels(
            source_run_dir=source_run_dir,
            scenario_name=args.scenario_name,
            replaced_agent_id=args.replaced_agent_id,
        )
    else:
        visible_channels = list(args.visible_history_channels)

    if args.history_from_round is None:
        channel_history_floors: dict[str, int] = {}
    else:
        channel_history_floors = {
            channel_id: args.history_from_round for channel_id in visible_channels
        }

    logger.info(
        "Replace-agent: replaced=%s visible_channels=%s history_floors=%s",
        args.replaced_agent_id,
        visible_channels,
        channel_history_floors,
    )

    request = ReplaceAgentCoreRequest(
        source_run_dir=source_run_dir,
        scenario_name=args.scenario_name,
        after_round=args.after_round,
        rounds_after=args.rounds_after,
        replaced_agent_id=args.replaced_agent_id,
        model=args.model,
        provider=args.provider,
        knobs=knobs,
        channels_with_visible_history=visible_channels,
        channel_history_floors=channel_history_floors,
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"replace-agent failed: {exc}") from exc

    await _register_derived_run(
        scenario=args.scenario_name,
        run_dir_name=Path(result.new_run_dir).name,
        source_run_scenario=args.scenario_name,
        source_run_dir_name=source_run_dir.name,
        group_slug=args.group_slug,
    )
    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")


async def _run_fork_at_round(args: argparse.Namespace) -> None:
    """Drive the fork-at-round operation from the CLI.

    Loads optional knob overrides from ``--knobs`` and forwards them to
    the shared replace-agent core with ``replaced_agent_id=None`` so no
    agent is restarted. Every agent keeps its full reconstructed history
    in the fork.
    """
    knobs = _resolve_knob_overrides(args=args)

    source_run_dir = Path(args.source_run_dir).resolve()

    logger.info(
        "Fork-at-round: source=%s after_round=%d",
        source_run_dir,
        args.after_round,
    )

    request = ReplaceAgentCoreRequest(
        source_run_dir=source_run_dir,
        scenario_name=args.scenario_name,
        after_round=args.after_round,
        rounds_after=args.rounds_after,
        replaced_agent_id=None,
        model=None,
        provider=None,
        knobs=knobs,
        channels_with_visible_history=None,
        channel_history_floors={},
        runs_dir=Path(args.runs_dir).resolve(),
    )
    try:
        result = await replace_agent_in_run(request=request)
    except ValueError as exc:
        raise SystemExit(f"fork-at-round failed: {exc}") from exc

    await _register_derived_run(
        scenario=args.scenario_name,
        run_dir_name=Path(result.new_run_dir).name,
        source_run_scenario=args.scenario_name,
        source_run_dir_name=source_run_dir.name,
        group_slug=args.group_slug,
    )
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
    missing. The orchestrator will catch the same case later, but this
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
    ``--source-b-round-end`` to ``min(after_round, B_max_round)``
    so the imported agent gets the largest possible slice of source B's
    history without exceeding what B actually played, calls the shared
    helper, and prints the new run ID and run dir on success.
    """
    knobs = _resolve_knob_overrides(args=args)

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
        source_b_round_end = min(args.after_round, source_b_max_round)
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
        "Cross-run replace-agent: replaced=%s after_round=%d source_b_round_end=%d "
        "visible_channels=%s model=%s provider=%s",
        args.replaced_agent_id,
        args.after_round,
        source_b_round_end,
        visible_channels,
        model,
        provider,
    )

    request = CrossRunCoreRequest(
        source_a_run_dir=source_a_run_dir,
        source_b_run_dir=source_b_run_dir,
        scenario_name=args.scenario_name,
        after_round=args.after_round,
        source_b_round_end=source_b_round_end,
        rounds_after=args.rounds_after,
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

    await _register_derived_run(
        scenario=args.scenario_name,
        run_dir_name=Path(result.new_run_dir).name,
        source_run_scenario=args.scenario_name,
        source_run_dir_name=source_a_run_dir.name,
        group_slug=args.group_slug,
    )
    print(f"new_run_id={result.new_run_id}")
    print(f"new_run_dir={result.new_run_dir}")


async def _run_login(args: argparse.Namespace) -> None:
    """Drive the ``glossogen login`` subcommand."""
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
    """Drive the ``glossogen push-to-prod`` subcommand."""
    concurrency = max(1, min(int(args.concurrency), 16))
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


async def _run_sync_metadata_to_prod(args: argparse.Namespace) -> None:
    """Drive the ``glossogen sync-metadata-to-prod`` subcommand."""
    concurrency = max(1, min(int(args.concurrency), 8))
    scenarios_arg: list[str] = args.scenarios
    scenarios = frozenset(scenarios_arg) if scenarios_arg else None
    spec = MetadataSyncSpec(
        runs_dir=Path(args.runs_dir),
        scenarios=scenarios,
        dry_run=args.dry_run,
        concurrency=concurrency,
    )
    tally = await run_metadata_sync(spec=spec)
    print(
        f"Done. labels={len(tally.synced_labels)}  eval={len(tally.synced_eval)}  "
        f"unchanged={len(tally.unchanged)}  failed={len(tally.failed)}"
    )
    if tally.failed:
        raise SystemExit(1)
