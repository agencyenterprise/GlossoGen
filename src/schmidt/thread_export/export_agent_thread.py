"""Orchestrate exporting one agent's thread from a finished run into a provider request.

Reuses the protocol probe's reconstruction path — ``build_message_history`` with the
same exclusive ``cutoff_round`` semantics and ``build_full_system_prompt`` — then
serializes the result with ``provider_thread_serializer`` into a ``ThreadExport``.
``export_agent_thread_from_run_dir`` loads the JSONL itself; ``export_agent_thread``
takes already-loaded events for callers (the web server) that have them in hand.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from schmidt.evaluation.log_reader import extract_agent_configs, load_events
from schmidt.message_history_builder import build_message_history, resolve_history_timestamp
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.runners.communication_protocol import build_full_system_prompt
from schmidt.thread_export.provider_thread_serializer import to_anthropic_request, to_openai_request
from schmidt.thread_export.thread_export_models import ThreadExport, ThreadExportMeta
from schmidt.token_pricing import SELF_HOSTED_PROVIDER

logger = logging.getLogger(__name__)

ThreadExportFormat = Literal["anthropic_messages", "openai_chat"]


def default_format_for_provider(provider: str) -> ThreadExportFormat:
    """Pick the export format matching the provider the agent ran under.

    Anthropic agents serialize to the Anthropic Messages shape; every other
    provider (OpenAI and the OpenAI-compatible self-hosted backend) serializes
    to the OpenAI Chat shape.
    """
    if provider == "anthropic":
        return "anthropic_messages"
    return "openai_chat"


def _resolve_agent_config(agent_configs: list[AgentConfig], agent_id: str) -> AgentConfig:
    """Return the latest ``AgentConfig`` registered for ``agent_id``.

    Cross-run / in-run-swap runs register the same ``agent_id`` more than once;
    the last registration carries the model and system prompt the agent ended
    the run under, matching the protocol probe's dedup choice.
    """
    resolved: AgentConfig | None = None
    for config in agent_configs:
        if config.agent_id == agent_id:
            resolved = config
    if resolved is None:
        available = ", ".join(sorted({config.agent_id for config in agent_configs})) or "<none>"
        raise ValueError(f"No agent {agent_id!r} in run (available agent_ids: {available})")
    return resolved


def _rounds_covered_label(cutoff_round: int | None, events: list[SimulationEvent]) -> str:
    """Human-readable description of which rounds the exported history spans."""
    if cutoff_round is None:
        last_round = max((event.round_number for event in events), default=0)
        return f"1-{last_round}"
    if cutoff_round <= 1:
        return "none"
    return f"1-{cutoff_round - 1}"


def export_agent_thread(
    events: list[SimulationEvent],
    agent_configs: list[AgentConfig],
    run_id: str,
    agent_id: str,
    cutoff_round: int | None,
    output_format: ThreadExportFormat,
    include_thinking: bool,
    flatten_tools: bool,
) -> ThreadExport:
    """Reconstruct ``agent_id``'s thread and serialize it into a provider request body.

    ``cutoff_round`` is the same exclusive cutoff the protocol probe uses: ``R``
    keeps rounds ``1..R-1`` (pass ``R+1`` to capture the end of round R);
    ``None`` exports the full end-of-run thread.
    """
    agent_config = _resolve_agent_config(agent_configs=agent_configs, agent_id=agent_id)
    full_system_prompt = build_full_system_prompt(
        base_prompt=agent_config.system_prompt,
        role_name=agent_config.role_name,
    )
    history = build_message_history(
        events=events,
        agent_id=agent_id,
        system_prompt=full_system_prompt,
        target_timestamp=resolve_history_timestamp(events=events),
        cutoff_round=cutoff_round,
        tool_calls_only=False,
        channel_visibility={},
        split_parallel_tool_calls=False,
    )
    if not history:
        raise ValueError(
            f"Reconstructed history for agent {agent_id!r} is empty "
            f"(cutoff_round={cutoff_round}); nothing to export."
        )

    if output_format == "anthropic_messages":
        request = to_anthropic_request(
            messages=history,
            model=agent_config.model,
            include_thinking=include_thinking,
            flatten_tools=flatten_tools,
        )
    else:
        request = to_openai_request(
            messages=history,
            model=agent_config.model,
            include_thinking=include_thinking,
            flatten_tools=flatten_tools,
        )

    meta = ThreadExportMeta(
        run_id=run_id,
        agent_id=agent_id,
        role_name=agent_config.role_name,
        model=agent_config.model,
        provider=agent_config.provider,
        cutoff_round=cutoff_round,
        rounds_covered=_rounds_covered_label(cutoff_round=cutoff_round, events=events),
        num_messages=len(request.messages),
        format=output_format,
        thinking_included=include_thinking,
        tools_flattened=flatten_tools,
        exported_at=datetime.now(tz=timezone.utc),
    )
    logger.info(
        "Exported thread for agent %s: format=%s cutoff_round=%s messages=%d "
        "(self_hosted=%s, thinking=%s, flatten_tools=%s)",
        agent_id,
        output_format,
        cutoff_round,
        len(request.messages),
        agent_config.provider == SELF_HOSTED_PROVIDER,
        include_thinking,
        flatten_tools,
    )
    return ThreadExport(meta=meta, request=request)


async def export_agent_thread_from_run_dir(
    run_dir: Path,
    scenario_name: str,
    agent_id: str,
    cutoff_round: int | None,
    output_format: ThreadExportFormat | None,
    include_thinking: bool,
    flatten_tools: bool,
) -> ThreadExport:
    """Load a run's JSONL and export one agent's thread as a provider request.

    ``output_format=None`` defaults to the format matching the agent's own
    provider. ``run_id`` is derived as ``<scenario>/<run_dir_name>``.
    """
    log_path = run_dir / f"{scenario_name}.jsonl"
    events = await load_events(log_path=log_path)
    agent_configs = extract_agent_configs(events=events)
    agent_config = _resolve_agent_config(agent_configs=agent_configs, agent_id=agent_id)
    if output_format is None:
        resolved_format = default_format_for_provider(provider=agent_config.provider)
    else:
        resolved_format = output_format
    return export_agent_thread(
        events=events,
        agent_configs=agent_configs,
        run_id=f"{run_dir.parent.name}/{run_dir.name}",
        agent_id=agent_id,
        cutoff_round=cutoff_round,
        output_format=resolved_format,
        include_thinking=include_thinking,
        flatten_tools=flatten_tools,
    )
