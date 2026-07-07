"""MCP server for browsing simulation runs, mounted inside the FastAPI app.

Exposes tools over Streamable HTTP for listing scenarios and runs, inspecting
run metadata and content, exporting run artifacts and per-agent threads, and
launching runs (full set in ``_TOOL_DEFS``). Designed for LLM clients (Claude
Code, Cursor) to query run data programmatically. All tools return structured
JSON.

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

from glossogen.evaluation.reports.evaluation_report import EvaluationReport
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.server.mcp.asgi_context import McpRunContextMiddleware
from glossogen.server.mcp.models import (
    McpAgent,
    McpAgentModel,
    McpAgentObservation,
    McpCrossRunReplaceAgentSource,
    McpDebugLog,
    McpDerivedRun,
    McpExportArtifactsResult,
    McpForkSource,
    McpGetKnobsPresetResult,
    McpGetKnobsSchemaResult,
    McpGetRunResult,
    McpHeadlineMeasurement,
    McpListDerivedRunsResult,
    McpListRunsResult,
    McpListScenariosResult,
    McpMeasurement,
    McpMessage,
    McpModel,
    McpReasoning,
    McpReplaceAgentSource,
    McpResumeAtRoundSource,
    McpRoundObservation,
    McpRunEntry,
    McpRunMetadata,
    McpScenario,
    McpStartRunResult,
    McpToolCall,
)
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from glossogen.server.mcp.run_context import get_run_context
from glossogen.server.run_launcher import launch_simulation
from glossogen.server.runs.derived_run_references import (
    build_derived_run_references,
    timeline_parent_run_id,
)
from glossogen.server.runs.detail_reader import debug_log_path_for, load_debug_logs, load_run_detail
from glossogen.server.runs.listing import list_runs_owned_by_group
from glossogen.server.runs.models import DerivedRunReference, RunDetailResponse, RunSummary
from glossogen.thread_export.export_agent_thread import (
    ThreadExportFormat,
    export_agent_thread_from_run_dir,
)
from glossogen.thread_export.thread_export_models import ThreadExport
from glossogen.token_pricing import list_models, list_providers

logger = logging.getLogger(__name__)

_SCENARIOS_BASE = Path(__file__).resolve().parent.parent.parent / "scenarios"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_knobs_files(scenario_name: str) -> list[str]:
    """Return sorted knobs filenames (without .json extension) for a scenario."""
    scenario_dir = _SCENARIOS_BASE / scenario_name
    if not scenario_dir.is_dir():
        return []
    return sorted(f.stem for f in scenario_dir.glob("knobs_*.json"))


async def _list_runs_for_active_group(scenario_filter: str | None) -> list[RunSummary]:
    """Return summaries for every run owned by the active group on this request."""
    ctx = get_run_context()
    return await list_runs_owned_by_group(
        pool=ctx.pool,
        runs_dir=ctx.runs_dir,
        group_id=ctx.group_id,
        scenario_filter=scenario_filter,
    )


async def _find_run_by_prefix(run_id_prefix: str) -> RunSummary:
    """Find a unique run (within the active group) whose run_id starts with ``run_id_prefix``.

    Raises ValueError if zero or multiple runs match.
    """
    all_runs = await _list_runs_for_active_group(scenario_filter=None)
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
    return await load_run_detail(log_path=jsonl_path, children=[])


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
        parent_run_id=timeline_parent_run_id(summary=run),
        labels=run.labels,
    )


def _replace_agent_source_of(run: RunSummary) -> McpReplaceAgentSource | None:
    """Convert a run's replace-agent provenance, or None if not a replace-agent run."""
    source = run.replace_agent_source
    if source is None:
        return None
    return McpReplaceAgentSource(
        source_run_id=source.source_run_id,
        round_start=source.round_start,
        replaced_agent_id=source.replaced_agent_id,
        replacement_model=source.replacement_model,
        replacement_provider=source.replacement_provider,
        replaced_at=source.replaced_at,
    )


def _resume_at_round_source_of(run: RunSummary) -> McpResumeAtRoundSource | None:
    """Convert a run's resume-at-round provenance, or None if not a resume-at-round run."""
    source = run.resume_at_round_source
    if source is None:
        return None
    return McpResumeAtRoundSource(
        source_run_id=source.source_run_id,
        round_start=source.round_start,
        rounds_after_resume=source.rounds_after_resume,
        resumed_at=source.resumed_at,
    )


def _cross_run_source_of(run: RunSummary) -> McpCrossRunReplaceAgentSource | None:
    """Convert a run's cross-run replace-agent provenance, or None if not a cross-run run."""
    source = run.cross_run_replace_agent_source
    if source is None:
        return None
    return McpCrossRunReplaceAgentSource(
        source_a_run_id=source.source_a_run_id,
        source_b_run_id=source.source_b_run_id,
        round_start=source.round_start,
        source_b_round_end=source.source_b_round_end,
        replaced_agent_id=source.replaced_agent_id,
        imported_model=source.imported_model,
        imported_provider=source.imported_provider,
        replaced_at=source.replaced_at,
    )


def _derived_run_to_entry(reference: DerivedRunReference) -> McpDerivedRun:
    """Convert a DerivedRunReference to an McpDerivedRun."""
    return McpDerivedRun(
        run_id=reference.run_id,
        derivation_type=reference.derivation_type,
        round_start=reference.round_start,
        rounds_after_swap=reference.rounds_after_swap,
        rounds_after_resume=reference.rounds_after_resume,
        replaced_agent_id=reference.replaced_agent_id,
        replacement_model=reference.replacement_model,
        replacement_provider=reference.replacement_provider,
        imported_model=reference.imported_model,
        imported_provider=reference.imported_provider,
        source_b_run_id=reference.source_b_run_id,
        source_b_round_end=reference.source_b_round_end,
        created_at=reference.created_at,
        status=reference.status.value,
        current_round=reference.current_round,
        target_round_count=reference.target_round_count,
        total_messages=reference.total_messages,
        total_cost_usd=reference.total_cost_usd,
        labels=reference.labels,
        has_evaluation=reference.has_evaluation,
        headline_measurements=[
            McpHeadlineMeasurement(
                metric_name=measurement.metric_name,
                score=measurement.score,
                score_unit=measurement.score_unit,
                summary=measurement.summary,
            )
            for measurement in reference.headline_measurements
        ],
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
GlossoGen simulation platform. Browse and launch multi-agent simulations.

## Browsing runs

1. `list_scenarios` — see available scenarios, knobs files, metrics, \
and supported models.
2. `list_runs` — browse runs with optional filters (scenario, model, \
status, is_forked, labels). `labels` is AND-matched. Paginate with \
offset/limit.
3. `get_run_metadata` — inspect a single run's config, agents, and \
evaluation results without loading messages. Pass a full run_id \
(e.g. `veyru/1776801080`) or a unique prefix of it.
4. `list_derived_runs` — list every run derived from a parent run \
(replace-agent, resume-at-round, cross-run-replace-agent). Each entry \
carries derivation type, round boundaries, swapped/imported models, \
labels, and headline round_success scores. Pass a full run_id or prefix.
5. `get_run` — load messages (paginated). Add flags for extra sections:
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
- `list_runs` returns newest runs first. Each entry carries `labels` and \
`parent_run_id` (the timeline parent for derived runs, else null).
- `get_run_metadata` carries full lineage provenance: `parent_run_id` plus \
the structured `fork_source` / `replace_agent_source` / \
`resume_at_round_source` / `cross_run_replace_agent_source` (at most one set).
- `parent_run_id` reflects the run's registered timeline parent. Lineage \
grouping labels like `src=<run_id>` are separate orchestrator tags that may \
span an entire experiment family, so they can match more runs than \
`list_derived_runs` returns for the same parent.
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
    labels: list[str] | None = None,
) -> McpListRunsResult:
    """List simulation runs with filtering and pagination.

    ``labels`` filters with AND semantics: a run is kept only if every
    requested label is present in its label set.
    """
    all_runs = await _list_runs_for_active_group(scenario_filter=None)

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
    if labels is not None:
        filtered = [r for r in filtered if all(label in r.labels for label in labels)]

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
        replace_agent_source=_replace_agent_source_of(run=run),
        resume_at_round_source=_resume_at_round_source_of(run=run),
        cross_run_replace_agent_source=_cross_run_source_of(run=run),
        parent_run_id=timeline_parent_run_id(summary=run),
        labels=run.labels,
        evaluation=_load_evaluation_measurements(run_summary=run),
    )


async def _tool_list_derived_runs(run_id: str) -> McpListDerivedRunsResult:
    """List every run derived from a parent run, newest first."""
    parent = await _find_run_by_prefix(run_id_prefix=run_id)
    parent_scenario, parent_run_dir_name = parent.run_id.split("/", 1)

    ctx = get_run_context()
    references = await build_derived_run_references(
        pool=ctx.pool,
        runs_dir=ctx.runs_dir,
        group_id=ctx.group_id,
        parent_scenario=parent_scenario,
        parent_run_dir_name=parent_run_dir_name,
    )

    derived_runs = [_derived_run_to_entry(reference=reference) for reference in references]
    return McpListDerivedRunsResult(
        parent_run_id=parent.run_id,
        derived_runs=derived_runs,
        total=len(derived_runs),
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
            children=detail.children,
            labels=detail.labels,
            note=detail.note,
            round_endings=detail.round_endings,
            round_results=detail.round_results,
            round_injections=[i for i in detail.round_injections if i.agent_id == agent_id],
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
    ctx = get_run_context()

    launch_simulation(
        scenario_name=scenario_name,
        model=model,
        provider=provider,
        scenario_cls=scenario_cls,
        knobs=knobs,
        runs_dir=ctx.runs_dir,
        group_slug=ctx.group_slug,
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


def _resolve_thread_export_format(output_format: str | None) -> ThreadExportFormat | None:
    """Map the tool's ``anthropic``/``openai`` choice to the internal export format.

    ``None`` defers to the agent's own provider inside the orchestrator.
    """
    if output_format is None:
        return None
    if output_format == "anthropic":
        return "anthropic_messages"
    if output_format == "openai":
        return "openai_chat"
    raise ValueError(f"output_format must be 'anthropic' or 'openai', got {output_format!r}")


async def _tool_export_agent_thread(
    run_id: str,
    agent_id: str,
    cutoff_round: int | None = None,
    output_format: str | None = None,
    include_thinking: bool = False,
    flatten_tools: bool = False,
) -> ThreadExport:
    """Export one agent's reconstructed thread as a drop-in provider request body."""
    run_summary = await _find_run_by_prefix(run_id_prefix=run_id)
    return await export_agent_thread_from_run_dir(
        run_dir=Path(run_summary.run_dir),
        scenario_name=run_summary.scenario_name,
        agent_id=agent_id,
        cutoff_round=cutoff_round,
        output_format=_resolve_thread_export_format(output_format=output_format),
        include_thinking=include_thinking,
        flatten_tools=flatten_tools,
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
        "list_derived_runs",
        "List every run derived from a parent run: replace-agent, "
        "resume-at-round, and cross-run-replace-agent (with the parent as "
        "source A). Each entry carries the derivation type, round boundaries, "
        "swapped/imported models, labels, and headline round_success scores. "
        "Accepts a full run_id or a unique prefix.",
        _tool_list_derived_runs,
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
    (
        "export_agent_thread",
        "Export one agent's reconstructed conversation thread from a finished run as a "
        "drop-in provider-native API request body (Anthropic Messages or OpenAI Chat). "
        "Set cutoff_round=R to cut the history before round R (keeps rounds 1..R-1); omit "
        "for the full end-of-run thread. output_format defaults to the agent's own provider; "
        "pass 'anthropic' or 'openai' to override. The returned 'request' is ready to POST — "
        "append your own trailing user message (and max_tokens for Anthropic) and send it to "
        "the provider. Accepts a full run_id or a unique prefix.",
        _tool_export_agent_thread,
    ),
]


# ---------------------------------------------------------------------------
# Factory & mount
# ---------------------------------------------------------------------------


def _build_mcp_server(oauth_provider: GlossoGenOAuthProvider, issuer_url: str) -> FastMCP:
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
        "glossogen-runs-browser",
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
    oauth_provider: GlossoGenOAuthProvider,
    issuer_url: str,
) -> None:
    """Mount the MCP runs browser on the FastAPI app at /mcp.

    Wraps FastMCP's Starlette sub-app with :class:`McpRunContextMiddleware`,
    which primes the per-request :class:`RunContext` (runs_dir, pool,
    group_id, group_slug) from the OAuth token before each tool runs. The
    session manager is stored so the main app lifespan can start it (sub-app
    lifespans do not run when mounted inside FastAPI).
    """
    mcp = _build_mcp_server(oauth_provider=oauth_provider, issuer_url=issuer_url)
    starlette_app = mcp.streamable_http_app()
    wrapped = McpRunContextMiddleware(
        app=starlette_app,
        oauth_provider=oauth_provider,
        get_pool=lambda: app.state.db_pool,
        get_runs_dir=lambda: runs_dir,
    )
    app.mount("/mcp", wrapped)
    app.state.mcp_session_manager = mcp.session_manager
    logger.info("MCP runs browser mounted at /mcp")
