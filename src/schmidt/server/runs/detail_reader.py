"""Loads and parses a full JSONL simulation log into a RunDetailResponse."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import orjson

from schmidt.eval_manifest import read_eval_manifest
from schmidt.evaluation.log_reader import load_events
from schmidt.evaluation.reports.evaluation_report import EvaluationReport
from schmidt.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    AgentSwappedMidRun,
    LLMResponseReceived,
    MessageSent,
    RoundEnded,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
    ToolCallInvoked,
    ToolResultReceived,
)
from schmidt.server.runs.models import (
    AgentObservationResponse,
    AgentRunCycleFailedEntry,
    AgentSwapEventDTO,
    CrossRunReplaceAgentSource,
    DebugLogEntry,
    EvalCostResponse,
    EvalReportResponse,
    ForkSource,
    MeasurementResponse,
    ReasoningEntry,
    ReplaceAgentSource,
    RoundEnding,
    RoundObservationResponse,
    RunDetailResponse,
    ToolUseEntry,
)
from schmidt.server.runs.run_detail_types import AgentDetail, ChannelMessage
from schmidt.server.runs.scenario_extension import SCENARIO_RUN_EXTENSIONS
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.token_pricing import TokenPricing, find_pricing

logger = logging.getLogger(__name__)


async def load_evaluation_report(report_path: Path) -> EvalReportResponse | None:
    """Load and parse an evaluation report JSON file, returning None if it does not exist."""
    if not report_path.exists():
        return None

    async with aiofiles.open(report_path, mode="rb") as f:
        raw_bytes = await f.read()

    raw = orjson.loads(raw_bytes)

    # Backfill for reports written before cost tracking was added.
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

    measurements = [
        MeasurementResponse(
            metric_name=m.metric_name,
            score=m.score,
            score_unit=m.score_unit,
            summary=m.summary,
            per_round=[
                RoundObservationResponse(
                    round_number=obs.round_number, value=obs.value, note=obs.note
                )
                for obs in m.per_round
            ],
            per_agent=[
                AgentObservationResponse(agent_id=obs.agent_id, value=obs.value, note=obs.note)
                for obs in m.per_agent
            ],
        )
        for m in report.measurements
    ]

    cost = report.evaluation_cost
    eval_cost = EvalCostResponse(
        input_tokens=cost.usage.input_tokens,
        output_tokens=cost.usage.output_tokens,
        cache_read_input_tokens=cost.usage.cache_read_input_tokens,
        cache_creation_input_tokens=cost.usage.cache_creation_input_tokens,
        estimated_cost_usd=cost.estimated_cost_usd,
        model=cost.model,
        provider_name=cost.provider_name,
    )

    return EvalReportResponse(measurements=measurements, evaluation_cost=eval_cost)


def _load_debug_logs_sync(debug_log_path: Path) -> list[DebugLogEntry]:
    """Parse debug JSONL synchronously; intended to be called via asyncio.to_thread."""
    entries: list[DebugLogEntry] = []
    with open(debug_log_path, mode="rb") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = orjson.loads(stripped)
                entries.append(
                    DebugLogEntry(
                        timestamp=raw["timestamp"],
                        logger_name=raw["logger"],
                        level=raw["level"],
                        message=raw["message"],
                    )
                )
            except (KeyError, orjson.JSONDecodeError):
                logger.exception("Skipping malformed debug log entry in %s", debug_log_path)
    return entries


async def load_debug_logs(debug_log_path: Path) -> list[DebugLogEntry]:
    """Load debug log entries from a JSONL file, returning an empty list if it does not exist."""
    if not debug_log_path.exists():
        return []
    return await asyncio.to_thread(_load_debug_logs_sync, debug_log_path)


def _link_reasoning_to_channels(
    reasoning: list[ReasoningEntry],
    messages: list[ChannelMessage],
) -> None:
    """Associate each reasoning entry with the channels of surrounding send_message calls.

    For each agent, walks their events in timestamp order and tags each reasoning
    entry with the channel of the previous send and the next send. This lets the
    frontend show only reasoning relevant to the selected channel.
    """
    agent_events: dict[str, list[ReasoningEntry | ChannelMessage]] = {}
    for r in reasoning:
        agent_events.setdefault(r.sender_agent_id, []).append(r)
    for m in messages:
        agent_events.setdefault(m.sender_agent_id, []).append(m)

    for agent_id in agent_events:
        items = sorted(agent_events[agent_id], key=lambda x: x.timestamp)

        prev_channel = ""
        pending_reasoning: list[ReasoningEntry] = []

        for item in items:
            if isinstance(item, ChannelMessage):
                for r in pending_reasoning:
                    channels = set()
                    if prev_channel:
                        channels.add(prev_channel)
                    channels.add(item.channel_id)
                    r.channel_ids = sorted(channels)
                pending_reasoning = []
                prev_channel = item.channel_id
            elif isinstance(item, ReasoningEntry):
                pending_reasoning.append(item)

        for r in pending_reasoning:
            if prev_channel:
                r.channel_ids = [prev_channel]


async def load_run_detail(log_path: Path) -> RunDetailResponse:
    """Parse all events from a JSONL log and assemble a RunDetailResponse."""
    events: list[SimulationEvent] = await load_events(log_path=log_path)

    run_dir = log_path.parent
    fork_source = _read_fork_source(run_dir=run_dir)
    replace_agent_source = _read_replace_agent_source(run_dir=run_dir)
    cross_run_replace_agent_source = _read_cross_run_replace_agent_source(run_dir=run_dir)

    run_id = ""
    scenario_name = ""
    scenario_description = ""
    scenario_config: dict[str, object] = {}
    provider = "unknown"
    timestamp = None
    channel_ids: list[str] = []
    agents_by_id: dict[str, AgentDetail] = {}
    agent_swap_events: list[AgentSwapEventDTO] = []
    messages: list[ChannelMessage] = []
    reasoning: list[ReasoningEntry] = []
    tool_use: list[ToolUseEntry] = []
    run_cycle_failures: list[AgentRunCycleFailedEntry] = []
    round_endings: list[RoundEnding] = []
    total_messages = 0
    total_cost_usd = 0.0
    duration_seconds = 0.0
    status = None

    tool_use_by_call_id: dict[str, ToolUseEntry] = {}
    pending_tool_results_by_call_id: dict[str, ToolResultReceived] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0
    pricing_by_agent: dict[str, TokenPricing | None] = {}
    cost_from_tokens = 0.0

    for event in events:
        if isinstance(event, SimulationStarted):
            run_id = event.run_id
            scenario_name = event.scenario_name
            scenario_description = event.scenario_description
            scenario_config = event.scenario_config
            provider = event.provider
            timestamp = event.timestamp
            channel_ids = event.channel_ids
        elif isinstance(event, AgentRegistered):
            agents_by_id[event.agent_id] = AgentDetail(
                agent_id=event.agent_id,
                role_name=event.role_name,
                channel_ids=event.channel_ids,
                tool_names=event.tool_names,
                model=event.model,
                provider=event.provider,
                system_prompt=event.system_prompt,
            )
            pricing_by_agent[event.agent_id] = find_pricing(model=event.model)

        elif isinstance(event, AgentSwappedMidRun):
            registered = agents_by_id.get(event.agent_id)
            agent_swap_events.append(
                AgentSwapEventDTO(
                    agent_id=event.agent_id,
                    round_number=event.round_number,
                    timestamp=event.timestamp,
                    new_model=event.new_model,
                    new_provider=event.new_provider,
                    system_prompt=registered.system_prompt if registered else "",
                )
            )
            pricing_by_agent[event.agent_id] = find_pricing(model=event.new_model)

        elif isinstance(event, ToolCallInvoked):
            total_messages += 1
            tu_entry = ToolUseEntry(
                message_id=f"{event.event_id}-{event.call_id}",
                sender_agent_id=event.agent_id,
                tool_name=event.tool_name,
                call_id=event.call_id,
                arguments=event.arguments,
                result=None,
                timestamp=event.timestamp,
                result_timestamp=None,
                round_number=event.round_number,
                result_round_number=None,
            )
            pending_result = pending_tool_results_by_call_id.pop(event.call_id, None)
            if pending_result is not None:
                tu_entry.result = pending_result.result
                tu_entry.result_timestamp = pending_result.timestamp
                tu_entry.result_round_number = pending_result.round_number
            tool_use.append(tu_entry)
            tool_use_by_call_id[event.call_id] = tu_entry

        elif isinstance(event, LLMResponseReceived):
            total_input_tokens += event.usage.input_tokens
            total_output_tokens += event.usage.output_tokens
            total_cache_read_tokens += event.usage.cache_read_input_tokens
            total_cache_write_tokens += event.usage.cache_creation_input_tokens

            event_pricing = pricing_by_agent.get(event.agent_id)
            if event_pricing is not None:
                non_cached_input = max(
                    0,
                    event.usage.input_tokens
                    - event.usage.cache_read_input_tokens
                    - event.usage.cache_creation_input_tokens,
                )
                cost_from_tokens += (
                    non_cached_input * event_pricing.input_per_mtok
                    + event.usage.output_tokens * event_pricing.output_per_mtok
                    + event.usage.cache_read_input_tokens
                    * event_pricing.cache_read_per_mtok
                    + event.usage.cache_creation_input_tokens
                    * event_pricing.cache_write_per_mtok
                ) / 1_000_000

            # Create reasoning entry for text content
            if event.text is not None and event.text.strip():
                total_messages += 1
                reasoning.append(
                    ReasoningEntry(
                        message_id=event.event_id,
                        sender_agent_id=event.agent_id,
                        text=event.text,
                        timestamp=event.timestamp,
                        round_number=event.round_number,
                        channel_ids=[],
                    )
                )

            # Fallback for runs predating ToolCallInvoked: create tool_use
            # entries from the LLMResponseReceived when none was created yet.
            for tc in event.tool_calls:
                if tc.call_id in tool_use_by_call_id:
                    continue
                total_messages += 1
                tu_entry = ToolUseEntry(
                    message_id=f"{event.event_id}-{tc.call_id}",
                    sender_agent_id=event.agent_id,
                    tool_name=tc.tool_name,
                    call_id=tc.call_id,
                    arguments=tc.arguments,
                    result=None,
                    timestamp=event.timestamp,
                    result_timestamp=None,
                    round_number=event.round_number,
                    result_round_number=None,
                )
                pending_result = pending_tool_results_by_call_id.pop(tc.call_id, None)
                if pending_result is not None:
                    tu_entry.result = pending_result.result
                    tu_entry.result_timestamp = pending_result.timestamp
                    tu_entry.result_round_number = pending_result.round_number
                tool_use.append(tu_entry)
                tool_use_by_call_id[tc.call_id] = tu_entry

        elif isinstance(event, ToolResultReceived):
            matched = tool_use_by_call_id.get(event.call_id)
            if matched is not None:
                matched.result = event.result
                matched.result_timestamp = event.timestamp
                matched.result_round_number = event.round_number
            else:
                # Some runs log tool results before the parent LLM response block.
                pending_tool_results_by_call_id[event.call_id] = event

        elif isinstance(event, AgentRunCycleFailed):
            run_cycle_failures.append(
                AgentRunCycleFailedEntry(
                    message_id=event.event_id,
                    agent_id=event.agent_id,
                    timestamp=event.timestamp,
                    round_number=event.round_number,
                    cycle=event.cycle,
                    error_type=event.error_type,
                    message=event.message,
                )
            )

        elif isinstance(event, MessageSent):
            total_messages += 1
            msg = event.message
            messages.append(
                ChannelMessage(
                    message_id=msg.message_id,
                    channel_id=msg.channel_id,
                    sender_agent_id=msg.sender_agent_id,
                    sender_display_name=msg.sender_display_name,
                    text=msg.text,
                    timestamp=msg.timestamp,
                    round_number=event.round_number,
                    token_count=event.token_count,
                )
            )

        elif isinstance(event, RoundEnded):
            round_endings.append(
                RoundEnding(
                    round_number=event.round_number,
                    trigger=event.trigger,
                    timestamp=event.timestamp,
                )
            )

        elif isinstance(event, SimulationEnded):
            status = event.reason
            total_cost_usd = event.total_cost_usd
            if timestamp is not None:
                duration_seconds = (event.timestamp - timestamp).total_seconds()

    agents = list(agents_by_id.values())

    # When the simulation hasn't logged a SimulationEnded yet (or it logged
    # zero cost), fall back to the per-agent token-based cost we accumulated
    # during the walk. For replace-agent / fork runs the inherited source
    # LLM events have empty `usage` (their token totals only existed in the
    # source's SimulationEnded, which sits past the rewind anchor), so they
    # contribute zero — only post-resume agents' costs are reflected.
    if total_cost_usd <= 0:
        total_cost_usd = cost_from_tokens

    _link_reasoning_to_channels(reasoning=reasoning, messages=messages)

    if timestamp is None:
        raise ValueError(f"No SimulationStarted event found in {log_path}")

    if status is None:
        manifest = read_manifest(run_dir=run_dir)
        if manifest is not None:
            status = RunStatus.IN_PROGRESS
        else:
            delete_manifest(run_dir=run_dir)
            fork_path = run_dir / "fork_manifest.json"
            replace_path = run_dir / "replace_manifest.json"
            if fork_path.exists() or replace_path.exists():
                status = RunStatus.STARTING
            else:
                status = RunStatus.ERROR
    report_path = log_path.with_name(f"{scenario_name}_report.json")
    evaluation = await load_evaluation_report(report_path=report_path)
    eval_manifest = read_eval_manifest(run_dir=run_dir)
    evaluation_in_progress = eval_manifest is not None
    has_eval_log_file = (run_dir / "eval_stdout.log").exists()

    extension = SCENARIO_RUN_EXTENSIONS.get(scenario_name)
    if extension is not None:
        scenario_extras = extension.build_extras(
            events=events, agents_by_id=agents_by_id, messages=messages
        )
    else:
        scenario_extras = None

    labels = await _read_labels_async(run_dir=run_dir)
    note = await _read_note(run_dir=run_dir)

    # For forked / replace-agent runs, the displayed start time is when
    # the derived run was created, not when the original parent started.
    if fork_source is not None:
        timestamp = fork_source.forked_at
    elif replace_agent_source is not None:
        timestamp = replace_agent_source.replaced_at
    elif cross_run_replace_agent_source is not None:
        timestamp = cross_run_replace_agent_source.replaced_at

    return RunDetailResponse(
        run_id=run_id,
        scenario_name=scenario_name,
        scenario_description=scenario_description,
        scenario_config=scenario_config,
        timestamp=timestamp,
        total_messages=total_messages,
        total_cost_usd=total_cost_usd,
        duration_seconds=duration_seconds,
        status=status,
        channel_ids=channel_ids,
        provider=provider,
        agents=agents,
        agent_swap_events=agent_swap_events,
        messages=messages,
        reasoning=reasoning,
        tool_use=tool_use,
        run_cycle_failures=run_cycle_failures,
        evaluation=evaluation,
        evaluation_in_progress=evaluation_in_progress,
        has_eval_log_file=has_eval_log_file,
        fork_source=fork_source,
        replace_agent_source=replace_agent_source,
        cross_run_replace_agent_source=cross_run_replace_agent_source,
        labels=labels,
        note=note,
        round_endings=round_endings,
        scenario_extras=scenario_extras,
    )


def debug_log_path_for(log_path: Path, scenario_name: str) -> Path:
    """Return the debug JSONL path corresponding to the main event log."""
    return log_path.with_name(f"{scenario_name}_debug.jsonl")


async def _read_note(run_dir: Path) -> str | None:
    """Read note.md from the run directory, returning None if it does not exist."""
    note_path = run_dir / "note.md"
    if not note_path.exists():
        return None
    async with aiofiles.open(note_path, mode="r") as f:
        return await f.read()


async def _read_labels_async(run_dir: Path) -> list[str]:
    """Read labels.json from the run directory, returning empty list if missing."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    try:
        async with aiofiles.open(labels_path, mode="rb") as f:
            raw_bytes = await f.read()
        result: list[str] = orjson.loads(raw_bytes)
        return result
    except Exception:
        logger.exception("Failed to read labels from %s", labels_path)
        return []


def _read_fork_source(run_dir: Path) -> ForkSource | None:
    """Read fork provenance from fork_manifest.json if it exists."""
    manifest_path = run_dir / "fork_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    forked_at = datetime.fromtimestamp(raw["forked_at"], tz=UTC)
    return ForkSource(
        source_run_id=raw["source_run_id"],
        target_message_id=raw["target_message_id"],
        forked_at=forked_at,
    )


def _read_replace_agent_source(run_dir: Path) -> ReplaceAgentSource | None:
    """Read replace-agent provenance from replace_manifest.json if it exists."""
    manifest_path = run_dir / "replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    target_event_id = raw.get("target_event_id") or raw.get("target_message_id", "")
    return ReplaceAgentSource(
        source_run_id=raw["source_run_id"],
        round_start=raw["round_start"],
        target_event_id=target_event_id,
        replaced_agent_id=raw["replaced_agent_id"],
        replacement_model=raw["replacement_model"],
        replacement_provider=raw["replacement_provider"],
        replaced_at=replaced_at,
    )


def _read_cross_run_replace_agent_source(
    run_dir: Path,
) -> CrossRunReplaceAgentSource | None:
    """Read cross-run provenance from cross_run_replace_manifest.json if it exists."""
    manifest_path = run_dir / "cross_run_replace_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    replaced_at = datetime.fromtimestamp(raw["replaced_at"], tz=UTC)
    return CrossRunReplaceAgentSource(
        source_a_run_id=raw["source_a_run_id"],
        source_b_run_id=raw["source_b_run_id"],
        round_start=raw["round_start"],
        source_b_round_end=raw["source_b_round_end"],
        target_event_id=raw["target_event_id"],
        replaced_agent_id=raw["replaced_agent_id"],
        imported_model=raw["imported_model"],
        imported_provider=raw["imported_provider"],
        replaced_at=replaced_at,
    )
