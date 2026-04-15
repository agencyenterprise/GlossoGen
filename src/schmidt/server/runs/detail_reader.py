"""Loads and parses a full JSONL simulation log into a RunDetailResponse."""

import logging
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import orjson

from schmidt.eval_manifest import read_eval_manifest
from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.evaluation.log_reader import load_events
from schmidt.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    MessageSent,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
    ToolResultReceived,
)
from schmidt.server.runs.models import (
    AgentDetail,
    ChannelMessage,
    DebugLogEntry,
    EvalCostResponse,
    EvalMetricResponse,
    EvalReportResponse,
    ForkSource,
    ReasoningEntry,
    RunDetailResponse,
    ToolUseEntry,
)
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.token_pricing import find_pricing

logger = logging.getLogger(__name__)


async def _load_evaluation_report(report_path: Path) -> EvalReportResponse | None:
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

    metrics = [
        EvalMetricResponse(
            evaluator_name=m.evaluator_name,
            verdict=m.verdict,
            score=m.score,
            evidence=m.evidence,
            per_agent=m.per_agent,
        )
        for m in report.metrics
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

    return EvalReportResponse(metrics=metrics, evaluation_cost=eval_cost)


async def _load_debug_logs(debug_log_path: Path) -> list[DebugLogEntry]:
    """Load debug log entries from a JSONL file, returning an empty list if it does not exist."""
    if not debug_log_path.exists():
        return []

    entries: list[DebugLogEntry] = []
    async with aiofiles.open(debug_log_path, mode="rb") as f:
        async for line in f:
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

    run_id = ""
    scenario_name = ""
    scenario_description = ""
    scenario_config: dict[str, object] = {}
    provider = "unknown"
    timestamp = None
    channel_ids: list[str] = []
    agents_by_id: dict[str, AgentDetail] = {}
    messages: list[ChannelMessage] = []
    reasoning: list[ReasoningEntry] = []
    tool_use: list[ToolUseEntry] = []
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

        elif isinstance(event, LLMResponseReceived):
            total_input_tokens += event.usage.input_tokens
            total_output_tokens += event.usage.output_tokens
            total_cache_read_tokens += event.usage.cache_read_input_tokens
            total_cache_write_tokens += event.usage.cache_creation_input_tokens

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

            # Create separate tool use entries for tool calls
            for tc in event.tool_calls:
                total_messages += 1
                tu_entry = ToolUseEntry(
                    message_id=f"{event.event_id}-{tc.call_id}",
                    sender_agent_id=event.agent_id,
                    tool_name=tc.tool_name,
                    call_id=tc.call_id,
                    arguments=tc.arguments,
                    result=None,
                    timestamp=event.timestamp,
                    round_number=event.round_number,
                )
                pending_result = pending_tool_results_by_call_id.pop(tc.call_id, None)
                if pending_result is not None:
                    tu_entry.result = pending_result.result
                    # Use the tool-result event time so tool entries are ordered by
                    # when each call actually completed.
                    tu_entry.timestamp = pending_result.timestamp
                tool_use.append(tu_entry)
                tool_use_by_call_id[tc.call_id] = tu_entry

        elif isinstance(event, ToolResultReceived):
            matched = tool_use_by_call_id.get(event.call_id)
            if matched is not None:
                matched.result = event.result
                # Use the tool-result event time so tool entries are ordered by
                # when each call actually completed.
                matched.timestamp = event.timestamp
            else:
                # Some runs log tool results before the parent LLM response block.
                pending_tool_results_by_call_id[event.call_id] = event

        elif isinstance(event, MessageSent):
            total_messages += 1
            msg = event.message
            messages.append(
                ChannelMessage(
                    message_id=msg.message_id,
                    channel_id=msg.channel_id,
                    sender_agent_id=msg.sender_agent_id,
                    text=msg.text,
                    timestamp=msg.timestamp,
                    round_number=event.round_number,
                    token_count=event.token_count,
                )
            )

        elif isinstance(event, SimulationEnded):
            status = event.reason
            total_cost_usd = event.total_cost_usd
            if timestamp is not None:
                duration_seconds = (event.timestamp - timestamp).total_seconds()

    agents = list(agents_by_id.values())

    # Compute cost from token usage when the simulation hasn't ended yet
    # (or when the ended event reported zero cost).
    if total_cost_usd <= 0 and total_input_tokens > 0:
        model = agents[0].model if agents else "unknown"
        pricing = find_pricing(model=model)
        if pricing is not None:
            non_cached_input = max(
                0,
                total_input_tokens - total_cache_read_tokens - total_cache_write_tokens,
            )
            total_cost_usd = (
                non_cached_input * pricing.input_per_mtok
                + total_output_tokens * pricing.output_per_mtok
                + total_cache_read_tokens * pricing.cache_read_per_mtok
                + total_cache_write_tokens * pricing.cache_write_per_mtok
            ) / 1_000_000

    _link_reasoning_to_channels(reasoning=reasoning, messages=messages)

    if timestamp is None:
        raise ValueError(f"No SimulationStarted event found in {log_path}")

    run_dir = log_path.parent

    if status is None:
        manifest = read_manifest(run_dir=run_dir)
        if manifest is not None:
            status = RunStatus.IN_PROGRESS
        else:
            delete_manifest(run_dir=run_dir)
            fork_path = run_dir / "fork_manifest.json"
            if fork_path.exists():
                status = RunStatus.STARTING
            else:
                status = RunStatus.ERROR
    report_path = log_path.with_name(f"{scenario_name}_report.json")
    evaluation = await _load_evaluation_report(report_path=report_path)
    eval_manifest = read_eval_manifest(run_dir=run_dir)
    evaluation_in_progress = eval_manifest is not None

    debug_log_path = log_path.with_name(f"{scenario_name}_debug.jsonl")
    debug_logs = await _load_debug_logs(debug_log_path=debug_log_path)

    fork_source = _read_fork_source(run_dir=run_dir)
    labels = await _read_labels_async(run_dir=run_dir)
    note = await _read_note(run_dir=run_dir)

    # For forked runs, the displayed start time is when the fork was created,
    # not when the original parent simulation started.
    if fork_source is not None:
        timestamp = fork_source.forked_at

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
        messages=messages,
        reasoning=reasoning,
        tool_use=tool_use,
        debug_logs=debug_logs,
        evaluation=evaluation,
        evaluation_in_progress=evaluation_in_progress,
        fork_source=fork_source,
        labels=labels,
        note=note,
    )


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
