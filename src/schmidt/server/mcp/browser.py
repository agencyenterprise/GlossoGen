"""MCP server for browsing simulation runs, mounted inside the FastAPI app.

Exposes tools over Streamable HTTP: list_scenarios, list_runs,
get_run_metadata, get_run, get_knobs_schema, get_knobs_preset, and
start_run. Designed for LLM clients (Claude Code, Cursor) to query run
data programmatically. All tools return structured JSON.

FastMCP construction is deferred to :func:`mount_mcp_browser` so that
OAuth configuration (which depends on environment variables) can be
injected at startup.
"""

import logging
from pathlib import Path
from typing import Any

import orjson
from fastapi import FastAPI
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from schmidt.evaluation.reports.evaluation_report import EvaluationReport
from schmidt.scenario_registry import SCENARIO_REGISTRY
from schmidt.server.mcp.models import (
    McpAgent,
    McpAgentModel,
    McpAgentObservation,
    McpDebugLog,
    McpExportArtifactsResult,
    McpForkSource,
    McpGetKnobsPresetResult,
    McpGetKnobsSchemaResult,
    McpGetRunResult,
    McpListRunsResult,
    McpListScenariosResult,
    McpMeasurement,
    McpMessage,
    McpModel,
    McpReasoning,
    McpRoundObservation,
    McpRunEntry,
    McpRunMetadata,
    McpScenario,
    McpStartRunResult,
    McpToolCall,
)
from schmidt.server.mcp.oauth_provider import SchmidtOAuthProvider
from schmidt.server.run_launcher import launch_simulation
from schmidt.server.runs.detail_reader import debug_log_path_for, load_debug_logs, load_run_detail
from schmidt.server.runs.discovery import discover_runs
from schmidt.server.runs.models import RunDetailResponse, RunSummary
from schmidt.token_pricing import list_models, list_providers

logger = logging.getLogger(__name__)

_SCENARIOS_BASE = Path(__file__).resolve().parent.parent.parent / "scenarios"

# Module-level state set by mount_mcp_browser().
_runs_dir: Path = Path("./runs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_knobs_files(scenario_name: str) -> list[str]:
    """Return sorted knobs filenames (without .json extension) for a scenario."""
    scenario_dir = _SCENARIOS_BASE / scenario_name
    if not scenario_dir.is_dir():
        return []
    return sorted(f.stem for f in scenario_dir.glob("knobs_*.json"))


async def _find_run_by_prefix(run_id_prefix: str) -> RunSummary:
    """Find a unique run whose run_id starts with the given prefix.

    Raises ValueError if zero or multiple runs match.
    """
    all_runs = await discover_runs(runs_dir=_runs_dir)
    matches = [r for r in all_runs if r.run_id.startswith(run_id_prefix)]
    if len(matches) == 0:
        raise ValueError(f"No run found matching prefix '{run_id_prefix}'")
    if len(matches) > 1:
        ids = ", ".join(r.run_id[:12] for r in matches[:5])
        raise ValueError(
            f"Ambiguous prefix '{run_id_prefix}' matches {len(matches)} runs: {ids}..."
        )
    return matches[0]


async def _load_detail(run_summary: RunSummary) -> RunDetailResponse:
    """Load full run detail from a RunSummary."""
    run_dir = Path(run_summary.run_dir)
    jsonl_path = run_dir / f"{run_summary.scenario_name}.jsonl"
    return await load_run_detail(log_path=jsonl_path)


def _run_summary_to_entry(run: RunSummary) -> McpRunEntry:
    """Convert a RunSummary to an McpRunEntry."""
    fork_source: McpForkSource | None = None
    if run.fork_source is not None:
        fork_source = McpForkSource(
            source_run_id=run.fork_source.source_run_id,
            target_message_id=run.fork_source.target_message_id,
            forked_at=run.fork_source.forked_at,
        )
    return McpRunEntry(
        run_id=run.run_id,
        scenario_name=run.scenario_name,
        status=run.status.value,
        timestamp=run.timestamp,
        total_messages=run.total_messages,
        total_cost_usd=run.total_cost_usd,
        duration_seconds=run.duration_seconds,
        provider=run.provider,
        models=run.models,
        is_forked=run.fork_source is not None,
        has_evaluation=run.has_evaluation,
        agent_models=[
            McpAgentModel(
                agent_id=a.agent_id,
                role_name=a.role_name,
                model=a.model,
                provider=a.provider,
            )
            for a in run.agent_models
        ],
        fork_source=fork_source,
    )


def _load_evaluation_measurements(run_summary: RunSummary) -> list[McpMeasurement] | None:
    """Load evaluation measurements from the report JSON, or return None."""
    run_dir = Path(run_summary.run_dir)
    report_path = run_dir / f"{run_summary.scenario_name}_report.json"
    if not report_path.exists():
        return None

    try:
        raw = orjson.loads(report_path.read_bytes())
        if "evaluation_cost" not in raw:
            raw["evaluation_cost"] = {
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "estimated_cost_usd": 0.0,
                "model": "unknown",
                "provider_name": "unknown",
            }
        report = EvaluationReport.model_validate(raw)
    except Exception:
        logger.exception("Failed to load evaluation report from %s", report_path)
        return None

    return [
        McpMeasurement(
            metric_name=m.metric_name,
            score=m.score,
            score_unit=m.score_unit,
            summary=m.summary,
            per_round=[
                McpRoundObservation(round_number=obs.round_number, value=obs.value, note=obs.note)
                for obs in m.per_round
            ],
            per_agent=[
                McpAgentObservation(agent_id=obs.agent_id, value=obs.value, note=obs.note)
                for obs in m.per_agent
            ],
        )
        for m in report.measurements
    ]


# ---------------------------------------------------------------------------
# MCP tool implementations (plain async functions, registered in mount)
# ---------------------------------------------------------------------------


_INSTRUCTIONS = """\
Schmidt simulation platform. Browse and launch multi-agent simulations.

## Browsing runs

1. `list_scenarios` — see available scenarios, knobs files, metrics, \
and supported models.
2. `list_runs` — browse runs with optional filters (scenario, model, \
status, is_forked). Paginate with offset/limit.
3. `get_run_metadata` — inspect a single run's config, agents, and \
evaluation results without loading messages. Pass a full run_id \
(e.g. `veyru/1776801080`) or a unique prefix of it.
4. `get_run` — load messages (paginated). Add flags for extra sections:
   - `with_reasoning=true` — LLM thinking/reasoning text
   - `with_tool_use=true` — tool invocations and results
   - `with_system_prompts=true` — full agent system prompts
   - `with_debug_logs=true` — backend debug log entries
   - `agent_id` — filter everything to one agent
   - `channel_id` — filter messages to one channel

## Starting runs

1. `get_knobs_schema` — get the JSON Schema for a scenario's knobs \
(field names, types, enum values, descriptions) and available presets.
2. `get_knobs_preset` — load a preset file to use as a starting point.
3. `start_run` — launch a simulation with a model, provider, and knobs.

## Tips

- Run IDs accept unique prefixes (e.g. "veyru/17" instead of the full id).
- `list_runs` returns newest runs first.
- `get_run` messages are paginated: use `message_offset` and \
`message_limit` to page through.
- Evaluation measurements include numeric scores plus per-round and \
per-agent observations.
- Use `get_knobs_preset` to load a baseline, modify fields, then pass \
to `start_run`.
"""


async def _tool_list_scenarios() -> McpListScenariosResult:
    """List available scenarios, models, and providers."""
    scenarios: list[McpScenario] = []
    for name in sorted(SCENARIO_REGISTRY.keys()):
        scenario_cls = SCENARIO_REGISTRY[name]
        scenarios.append(
            McpScenario(
                name=name,
                knobs_files=_list_knobs_files(scenario_name=name),
                metrics=scenario_cls.get_available_metric_names(),
            )
        )

    models = [
        McpModel(model_prefix=prefix, provider=provider) for prefix, provider in list_models()
    ]

    return McpListScenariosResult(
        scenarios=scenarios,
        models=models,
        providers=list_providers(),
    )


async def _tool_list_runs(
    offset: int = 0,
    limit: int = 20,
    scenario: str | None = None,
    model: str | None = None,
    is_forked: bool | None = None,
    status: str | None = None,
) -> McpListRunsResult:
    """List simulation runs with filtering and pagination."""
    all_runs = await discover_runs(runs_dir=_runs_dir)

    filtered = all_runs
    if scenario is not None:
        scenario_lower = scenario.lower()
        filtered = [r for r in filtered if scenario_lower in r.scenario_name.lower()]
    if model is not None:
        model_lower = model.lower()
        filtered = [r for r in filtered if any(model_lower in m.lower() for m in r.models)]
    if is_forked is not None:
        if is_forked:
            filtered = [r for r in filtered if r.fork_source is not None]
        else:
            filtered = [r for r in filtered if r.fork_source is None]
    if status is not None:
        status_lower = status.lower()
        filtered = [r for r in filtered if r.status.value.lower() == status_lower]

    total = len(filtered)
    page = filtered[offset : offset + limit]

    return McpListRunsResult(
        runs=[_run_summary_to_entry(run=r) for r in page],
        total=total,
        offset=offset,
        limit=limit,
    )


async def _tool_get_run_metadata(run_id: str) -> McpRunMetadata:
    """Get run metadata without loading full event log."""
    run = await _find_run_by_prefix(run_id_prefix=run_id)

    fork_source: McpForkSource | None = None
    if run.fork_source is not None:
        fork_source = McpForkSource(
            source_run_id=run.fork_source.source_run_id,
            target_message_id=run.fork_source.target_message_id,
            forked_at=run.fork_source.forked_at,
        )

    return McpRunMetadata(
        run_id=run.run_id,
        scenario_name=run.scenario_name,
        status=run.status.value,
        timestamp=run.timestamp,
        total_messages=run.total_messages,
        total_cost_usd=run.total_cost_usd,
        duration_seconds=run.duration_seconds,
        provider=run.provider,
        models=run.models,
        is_forked=run.fork_source is not None,
        scenario_config=run.scenario_config,
        agent_models=[
            McpAgentModel(
                agent_id=a.agent_id,
                role_name=a.role_name,
                model=a.model,
                provider=a.provider,
            )
            for a in run.agent_models
        ],
        fork_source=fork_source,
        evaluation=_load_evaluation_measurements(run_summary=run),
    )


async def _tool_get_run(
    run_id: str,
    agent_id: str | None = None,
    channel_id: str | None = None,
    with_reasoning: bool = False,
    with_tool_use: bool = False,
    with_debug_logs: bool = False,
    with_system_prompts: bool = False,
    message_limit: int = 50,
    message_offset: int = 0,
) -> McpGetRunResult:
    """Get detailed run content with opt-in sections and filtering."""
    run_summary = await _find_run_by_prefix(run_id_prefix=run_id)
    detail = await _load_detail(run_summary=run_summary)

    # Filter by agent across all sections
    if agent_id is not None:
        detail = RunDetailResponse(
            run_id=detail.run_id,
            scenario_name=detail.scenario_name,
            scenario_description=detail.scenario_description,
            scenario_config=detail.scenario_config,
            timestamp=detail.timestamp,
            total_messages=detail.total_messages,
            total_cost_usd=detail.total_cost_usd,
            duration_seconds=detail.duration_seconds,
            status=detail.status,
            channel_ids=detail.channel_ids,
            provider=detail.provider,
            agent_swap_events=[s for s in detail.agent_swap_events if s.agent_id == agent_id],
            agents=[a for a in detail.agents if a.agent_id == agent_id],
            messages=[m for m in detail.messages if m.sender_agent_id == agent_id],
            reasoning=[r for r in detail.reasoning if r.sender_agent_id == agent_id],
            tool_use=[t for t in detail.tool_use if t.sender_agent_id == agent_id],
            run_cycle_failures=[f for f in detail.run_cycle_failures if f.agent_id == agent_id],
            evaluation=detail.evaluation,
            evaluation_in_progress=detail.evaluation_in_progress,
            has_eval_log_file=detail.has_eval_log_file,
            fork_source=detail.fork_source,
            replace_agent_source=detail.replace_agent_source,
            cross_run_replace_agent_source=detail.cross_run_replace_agent_source,
            resume_at_round_source=detail.resume_at_round_source,
            labels=detail.labels,
            note=detail.note,
            round_endings=detail.round_endings,
            scenario_extras=detail.scenario_extras,
        )

    # Filter messages by channel
    messages = detail.messages
    if channel_id is not None:
        messages = [m for m in messages if m.channel_id == channel_id]

    # Paginate messages
    total_messages = len(messages)
    page = messages[message_offset : message_offset + message_limit]

    # Build optional sections
    agents: list[McpAgent] | None = None
    if with_system_prompts:
        agents = [
            McpAgent(
                agent_id=a.agent_id,
                role_name=a.role_name,
                model=a.model,
                provider=a.provider,
                tool_names=a.tool_names,
                channel_ids=a.channel_ids,
                system_prompt=a.system_prompt,
            )
            for a in detail.agents
        ]

    reasoning: list[McpReasoning] | None = None
    if with_reasoning:
        reasoning = [
            McpReasoning(
                message_id=r.message_id,
                sender_agent_id=r.sender_agent_id,
                text=r.text,
                timestamp=r.timestamp,
                round_number=r.round_number,
            )
            for r in detail.reasoning[:50]
        ]

    tool_use: list[McpToolCall] | None = None
    if with_tool_use:
        tool_use = [
            McpToolCall(
                message_id=t.message_id,
                sender_agent_id=t.sender_agent_id,
                tool_name=t.tool_name,
                arguments=t.arguments,
                result=t.result,
                timestamp=t.timestamp,
                round_number=t.round_number,
            )
            for t in detail.tool_use[:50]
        ]

    debug_logs: list[McpDebugLog] | None = None
    if with_debug_logs:
        run_dir = Path(run_summary.run_dir)
        jsonl_path = run_dir / f"{run_summary.scenario_name}.jsonl"
        raw_debug_logs = await load_debug_logs(
            debug_log_path=debug_log_path_for(
                log_path=jsonl_path, scenario_name=run_summary.scenario_name
            )
        )
        debug_logs = [
            McpDebugLog(
                timestamp=d.timestamp,
                logger_name=d.logger_name,
                level=d.level,
                message=d.message,
            )
            for d in raw_debug_logs[-100:]
        ]

    return McpGetRunResult(
        run_id=detail.run_id,
        scenario_name=detail.scenario_name,
        messages=[
            McpMessage(
                message_id=m.message_id,
                channel_id=m.channel_id,
                sender_agent_id=m.sender_agent_id,
                text=m.text,
                timestamp=m.timestamp,
                round_number=m.round_number,
            )
            for m in page
        ],
        total_messages=total_messages,
        message_offset=message_offset,
        message_limit=message_limit,
        agents=agents,
        reasoning=reasoning,
        tool_use=tool_use,
        debug_logs=debug_logs,
    )


async def _tool_get_knobs_schema(scenario_name: str) -> McpGetKnobsSchemaResult:
    """Get the knobs JSON schema and available presets for a scenario."""
    if scenario_name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    scenario_cls = SCENARIO_REGISTRY[scenario_name]
    return McpGetKnobsSchemaResult(
        scenario_name=scenario_name,
        knobs_schema=scenario_cls.knobs_json_schema(),
        knobs_files=_list_knobs_files(scenario_name=scenario_name),
    )


async def _tool_get_knobs_preset(
    scenario_name: str,
    knobs_file: str,
) -> McpGetKnobsPresetResult:
    """Load a knobs preset file."""
    if scenario_name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    knobs_path = _SCENARIOS_BASE / scenario_name / f"{knobs_file}.json"
    if not knobs_path.is_file():
        raise ValueError(f"Knobs file not found: {knobs_file}")

    knobs = orjson.loads(knobs_path.read_bytes())
    return McpGetKnobsPresetResult(
        scenario_name=scenario_name,
        knobs_file=knobs_file,
        knobs=knobs,
    )


async def _tool_start_run(
    scenario_name: str,
    model: str,
    provider: str,
    knobs: dict[str, Any] | None = None,
) -> McpStartRunResult:
    """Validate config and launch a simulation subprocess."""
    if scenario_name not in SCENARIO_REGISTRY:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    scenario_cls = SCENARIO_REGISTRY[scenario_name]

    launch_simulation(
        scenario_name=scenario_name,
        model=model,
        provider=provider,
        scenario_cls=scenario_cls,
        knobs=knobs,
        runs_dir=_runs_dir,
    )

    return McpStartRunResult(
        status="started",
        scenario_name=scenario_name,
        model=model,
        provider=provider,
    )


async def _tool_export_run_artifacts(run_id: str) -> McpExportArtifactsResult:
    """Return a download URL for exporting the run as a tar.gz bundle."""
    run_summary = await _find_run_by_prefix(run_id_prefix=run_id)
    full_run_id = run_summary.run_id
    run_dir_name = full_run_id.split("/", 1)[1]
    filename = f"{run_summary.scenario_name}_{run_dir_name}_bundle.tar.gz"
    download_url = f"/api/runs/{full_run_id}/export/bundle"
    return McpExportArtifactsResult(
        run_id=full_run_id,
        scenario_name=run_summary.scenario_name,
        download_url=download_url,
        filename=filename,
    )


# ---------------------------------------------------------------------------
# Tool registration table
# ---------------------------------------------------------------------------

_TOOL_DEFS: list[tuple[str, str, Any]] = [
    (
        "list_scenarios",
        "List all available simulation scenarios with their "
        "knobs files, metrics, and supported models/providers.",
        _tool_list_scenarios,
    ),
    (
        "list_runs",
        "List simulation runs with pagination and optional filtering. "
        "Returns runs sorted by timestamp (newest first).",
        _tool_list_runs,
    ),
    (
        "get_run_metadata",
        "Get lightweight metadata for a single run: header info, agents, "
        "configuration, and evaluation results. Does not load messages or "
        "reasoning. Accepts a full run_id or a unique prefix.",
        _tool_get_run_metadata,
    ),
    (
        "get_run",
        "Get detailed run content including messages. Optionally include "
        "reasoning, tool use, debug logs, and system prompts via flags. "
        "Filter by agent_id or channel_id. Messages are paginated via "
        "message_offset/message_limit.",
        _tool_get_run,
    ),
    (
        "get_knobs_schema",
        "Get the JSON Schema for a scenario's knobs configuration. "
        "Returns field names, types, enum values with descriptions, "
        "and the list of available preset files.",
        _tool_get_knobs_schema,
    ),
    (
        "get_knobs_preset",
        "Load the contents of a knobs preset file for a scenario. "
        "Use this to get a baseline configuration, then modify "
        "individual fields before passing to start_run.",
        _tool_get_knobs_preset,
    ),
    (
        "start_run",
        "Launch a new simulation as a background process. "
        "Requires scenario_name, model, and provider. "
        "Pass knobs from a preset (via get_knobs_preset) with "
        "any modifications applied.",
        _tool_start_run,
    ),
    (
        "export_run_artifacts",
        "Get a download URL for exporting all run artifacts as a zip archive. "
        "Returns a relative URL path that can be fetched from the backend server. "
        "Accepts a full run_id or a unique prefix.",
        _tool_export_run_artifacts,
    ),
]


# ---------------------------------------------------------------------------
# Factory & mount
# ---------------------------------------------------------------------------


def _build_mcp_server(oauth_provider: SchmidtOAuthProvider, issuer_url: str) -> FastMCP:
    """Construct the FastMCP instance with OAuth authentication."""
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(issuer_url),
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["read", "write"],
            default_scopes=["read", "write"],
        ),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=["read"],
    )

    server = FastMCP(
        "schmidt-runs-browser",
        instructions=_INSTRUCTIONS,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        auth=auth_settings,
        auth_server_provider=oauth_provider,
    )

    for tool_name, tool_desc, tool_fn in _TOOL_DEFS:
        server.tool(name=tool_name, description=tool_desc)(tool_fn)

    return server


def mount_mcp_browser(
    app: FastAPI,
    runs_dir: Path,
    oauth_provider: SchmidtOAuthProvider,
    issuer_url: str,
) -> None:
    """Mount the MCP runs browser on the FastAPI app at /mcp.

    Creates the Starlette sub-app and stores the session manager so the
    main app lifespan can start it (sub-app lifespans do not run when
    mounted inside FastAPI).
    """
    global _runs_dir  # noqa: PLW0603
    _runs_dir = runs_dir

    mcp = _build_mcp_server(oauth_provider=oauth_provider, issuer_url=issuer_url)
    starlette_app = mcp.streamable_http_app()
    app.mount("/mcp", starlette_app)
    app.state.mcp_session_manager = mcp.session_manager
    logger.info("MCP runs browser mounted at /mcp")
