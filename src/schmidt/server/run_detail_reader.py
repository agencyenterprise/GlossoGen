"""Loads and parses a full JSONL simulation log into a RunDetailResponse."""

import logging
from pathlib import Path

import aiofiles
import orjson

from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.evaluation.log_reader import load_events
from schmidt.models.event import (
    AgentRegistered,
    LLMResponseReceived,
    MessageSent,
    RoundAdvanced,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
    ToolResultReceived,
)
from schmidt.runtime.mcp_tools import HIDDEN_TOOL_NAMES
from schmidt.server.response_models import (
    AgentDetail,
    ChannelMessage,
    DebugLogEntry,
    EvalMetricResponse,
    EvalReportResponse,
    ForkSource,
    ReasoningEntry,
    RunDetailResponse,
    ToolUseEntry,
)
from schmidt.stream_manifest import delete_manifest, read_manifest

logger = logging.getLogger(__name__)


async def _load_evaluation_report(report_path: Path) -> EvalReportResponse | None:
    """Load and parse an evaluation report JSON file, returning None if it does not exist."""
    if not report_path.exists():
        return None

    async with aiofiles.open(report_path, mode="rb") as f:
        raw = await f.read()

    report = EvaluationReport.model_validate(orjson.loads(raw))

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

    return EvalReportResponse(metrics=metrics)


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
    timestamp = None
    channel_ids: list[str] = []
    agents: list[AgentDetail] = []
    messages: list[ChannelMessage] = []
    reasoning: list[ReasoningEntry] = []
    tool_use: list[ToolUseEntry] = []
    total_messages = 0
    total_cost_usd = 0.0
    duration_seconds = 0.0
    status = None

    current_round = 0
    tool_use_by_call_id: dict[str, ToolUseEntry] = {}

    for event in events:
        if isinstance(event, SimulationStarted):
            run_id = event.run_id
            scenario_name = event.scenario_name
            scenario_description = event.scenario_description
            scenario_config = event.scenario_config
            timestamp = event.timestamp
            channel_ids = event.channel_ids

        elif isinstance(event, AgentRegistered):
            agents.append(
                AgentDetail(
                    agent_id=event.agent_id,
                    role_name=event.role_name,
                    channel_ids=event.channel_ids,
                    tool_names=event.tool_names,
                    model=event.model,
                    system_prompt=event.system_prompt,
                )
            )

        elif isinstance(event, RoundAdvanced):
            current_round = event.new_round_number

        elif isinstance(event, LLMResponseReceived):
            # Create reasoning entry for text content
            if event.text is not None and event.text.strip():
                total_messages += 1
                reasoning.append(
                    ReasoningEntry(
                        message_id=event.event_id,
                        sender_agent_id=event.agent_id,
                        text=event.text,
                        timestamp=event.timestamp,
                        turn_number=total_messages,
                        round_number=current_round,
                        channel_ids=[],
                    )
                )

            # Create separate tool use entries for non-builtin tools
            for tc in event.tool_calls:
                if tc.tool_name.endswith(tuple(HIDDEN_TOOL_NAMES)):
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
                    turn_number=total_messages,
                    round_number=current_round,
                )
                tool_use.append(tu_entry)
                tool_use_by_call_id[tc.call_id] = tu_entry

        elif isinstance(event, ToolResultReceived):
            matched = tool_use_by_call_id.get(event.call_id)
            if matched is not None:
                matched.result = event.result

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
                    turn_number=total_messages,
                    round_number=current_round,
                )
            )

        elif isinstance(event, SimulationEnded):
            status = event.reason
            total_cost_usd = event.total_cost_usd
            if timestamp is not None:
                duration_seconds = (event.timestamp - timestamp).total_seconds()

    _link_reasoning_to_channels(reasoning=reasoning, messages=messages)

    if timestamp is None:
        raise ValueError(f"No SimulationStarted event found in {log_path}")
    if status is None:
        run_dir = log_path.parent
        manifest = read_manifest(run_dir=run_dir)
        if manifest is not None:
            status = RunStatus.IN_PROGRESS
        else:
            delete_manifest(run_dir=run_dir)
            status = RunStatus.ERROR

    report_path = log_path.with_name(f"{scenario_name}_report.json")
    evaluation = await _load_evaluation_report(report_path=report_path)

    debug_log_path = log_path.with_name(f"{scenario_name}_debug.jsonl")
    debug_logs = await _load_debug_logs(debug_log_path=debug_log_path)

    fork_source = _read_fork_source(run_dir=log_path.parent)

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
        agents=agents,
        messages=messages,
        reasoning=reasoning,
        tool_use=tool_use,
        debug_logs=debug_logs,
        evaluation=evaluation,
        fork_source=fork_source,
    )


def _read_fork_source(run_dir: Path) -> ForkSource | None:
    """Read fork provenance from fork_manifest.json if it exists."""
    manifest_path = run_dir / "fork_manifest.json"
    if not manifest_path.exists():
        return None
    raw = orjson.loads(manifest_path.read_bytes())
    return ForkSource(
        source_run_id=raw["source_run_id"],
        target_message_id=raw["target_message_id"],
    )
