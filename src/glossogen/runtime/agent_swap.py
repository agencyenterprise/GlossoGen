"""Mid-run agent swap mechanics.

Implements the heavy lifting for the in-run scheduler's ``swap_agent``
intervention: cancel the existing runner task for an agent, build a
filtered seed history from the live event log, install per-channel
visibility for the swapped-in agent, replace the ``AgentSession``,
and spawn a fresh runner via the supplied factory. The supervisor
provides an ``AgentSwapResources`` bundle and delegates the swap
through ``execute_agent_swap``.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from glossogen.channel_router import compute_per_channel_join_index
from glossogen.evaluation.log_reader import load_events
from glossogen.message_history_builder import build_message_history
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import AgentRegistered, AgentSwappedMidRun
from glossogen.resume_context_writer import write_swap_resume_context_file
from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runners.communication_protocol import build_full_system_prompt
from glossogen.runtime.activity_notification import DoneNotification, NewMessagesNotification
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scheduled_events import ChannelVisibility, ChannelVisibilityNone, SwapAgent
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.token_pricing import SELF_HOSTED_PROVIDER

logger = logging.getLogger(__name__)


SWAP_RUNNER_GRACE_SECONDS = 5.0


class AgentSwapResources(NamedTuple):
    """Bundle of references the agent-swap implementation needs.

    The supervisor instantiates this once and passes it through to
    ``execute_agent_swap`` for each scheduled swap. Keeping the
    dependencies in one struct keeps the swap signature stable as the
    supervisor evolves.
    """

    runtime: SimulationRuntime
    runner_factory: Callable[[], AgentRunner]
    runner_tasks: dict[str, asyncio.Task[Any]]
    log_path: Path
    run_dir: Path
    mcp_server_url: str
    cost_tracker: dict[str, float]


async def execute_agent_swap(
    spec: SwapAgent,
    resources: AgentSwapResources,
) -> None:
    """Perform a mid-run swap of the agent identified by ``spec.agent_id``.

    Drains the existing runner via ``DoneNotification`` (force-cancels
    after a grace period if the runner does not exit cleanly), rebuilds
    the new agent's seed message history from the live JSONL with
    ``tool_calls_only=True`` and per-channel visibility from
    ``spec.channel_visibility``, applies the resulting
    ``member_join_index`` values to the channel router, replaces the
    ``AgentSession`` and ``AgentConfig`` on the runtime, spawns a fresh
    runner task, wakes the new agent, and emits ``AgentSwappedMidRun``.
    """
    runtime = resources.runtime
    event_logger = runtime.event_logger
    agent_id = spec.agent_id

    old_task = resources.runner_tasks.get(agent_id)
    if old_task is None:
        raise ValueError(f"No active runner task for agent_id={agent_id!r}")
    old_session = runtime.agent_sessions.get(agent_id)
    if old_session is None:
        raise ValueError(f"No active session for agent_id={agent_id!r}")
    old_config = runtime.get_agent_config(agent_id=agent_id)

    await _drain_old_runner(agent_id=agent_id, old_session=old_session, old_task=old_task)

    # Channels the world has globally disabled (e.g. veyru postmortem after a
    # set_postmortem swap event) get forced to ``ChannelVisibilityNone`` for
    # the swapped-in agent. Without this, the new agent would inherit the
    # predecessor's full visibility on a channel the simulation considers
    # closed and would receive wake-up notifications for the channel's
    # historical messages.
    disabled_channels = runtime.scenario.get_world().get_globally_disabled_channels()
    effective_channel_visibility: dict[str, ChannelVisibility] = {**spec.channel_visibility}
    for channel_id in disabled_channels:
        effective_channel_visibility[channel_id] = ChannelVisibilityNone()
    effective_spec = (
        spec
        if not disabled_channels
        else spec.model_copy(update={"channel_visibility": effective_channel_visibility})
    )

    seed_history_config = await _build_seed_history(
        spec=effective_spec,
        log_path=resources.log_path,
    )

    _install_channel_visibility(spec=effective_spec, runtime=runtime)

    new_session = AgentSession(agent_id=agent_id)
    runtime.replace_agent_session(agent_id=agent_id, session=new_session)

    new_config = AgentConfig(
        agent_id=old_config.agent_id,
        role_name=old_config.role_name,
        system_prompt=seed_history_config.system_prompt,
        channel_ids=old_config.channel_ids,
        tool_names=old_config.tool_names,
        model=spec.model,
        provider=spec.provider,
        max_tokens=old_config.max_tokens,
        compaction=old_config.compaction,
        initial_message_history=seed_history_config.history,
    )
    runtime.update_agent_config(agent_id=agent_id, config=new_config)

    write_swap_resume_context_file(
        run_dir=resources.run_dir,
        agent_id=agent_id,
        round_number=spec.at_round,
        history=seed_history_config.history,
    )

    runner = resources.runner_factory()
    new_task = asyncio.create_task(
        runner.start(
            agent_config=new_config,
            mcp_server_url=resources.mcp_server_url,
            runtime=runtime,
            cost_tracker=resources.cost_tracker,
        ),
        name=f"agent-{agent_id}-swapped-r{spec.at_round}",
    )
    resources.runner_tasks[agent_id] = new_task

    # Wake the new agent on every channel it can still read (excluding
    # globally disabled ones). Skipping disabled channels prevents the
    # spurious "you have new messages in #postmortem" alert that would
    # otherwise hand the swapped-in agent a window into pre-disable
    # history.
    agent_channels = [
        channel_id
        for channel_id in runtime.channel_router.get_agent_channel_ids(agent_id=agent_id)
        if channel_id not in disabled_channels
    ]
    new_session.push_notification(
        notification=NewMessagesNotification(channels=agent_channels),
    )

    # Notify the world so its injection-builder can suppress prior-round
    # context (e.g. veyru's PREVIOUS VEYRU RESULT block) for the swapped-in
    # agent's first round.
    runtime.scenario.get_world().on_agent_swapped_mid_run(
        agent_id=agent_id,
        round_number=spec.at_round,
    )

    await event_logger.log(
        event=AgentSwappedMidRun(
            agent_id=agent_id,
            new_model=spec.model,
            new_provider=spec.provider,
            channel_visibility=effective_channel_visibility,
            round_number=spec.at_round,
        )
    )
    logger.info(
        "Agent %s swapped at round %d to %s/%s",
        agent_id,
        spec.at_round,
        spec.provider,
        spec.model,
    )


async def _drain_old_runner(
    agent_id: str,
    old_session: AgentSession,
    old_task: asyncio.Task[Any],
) -> None:
    """Push DoneNotification, wait for graceful exit, force-cancel on timeout."""
    old_session.push_notification(notification=DoneNotification(reason="agent_swap"))
    try:
        await asyncio.wait_for(old_task, timeout=SWAP_RUNNER_GRACE_SECONDS)
        return
    except asyncio.TimeoutError:
        logger.warning(
            "Old runner for %s did not exit in %.1fs; cancelling forcefully",
            agent_id,
            SWAP_RUNNER_GRACE_SECONDS,
        )
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Old runner for %s raised on shutdown", agent_id)
        return

    old_task.cancel()
    try:
        await old_task
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Old runner for %s raised after cancellation", agent_id)


class _SeedHistory(NamedTuple):
    history: list[Any]
    system_prompt: str


async def _build_seed_history(
    spec: SwapAgent,
    log_path: Path,
) -> _SeedHistory:
    """Build the new agent's filtered pydantic-ai message history from JSONL.

    Uses ``cutoff_round=spec.at_round`` so tool calls from rounds <
    ``at_round`` are kept and any LLM cycle straddling the swap
    boundary drops its post-cutoff text/thinking via the existing
    ``tool_calls_only`` and per-tool-call cutoff filters.
    """
    events = await load_events(log_path=log_path)
    last_registration = next(
        (
            ev
            for ev in reversed(events)
            if isinstance(ev, AgentRegistered) and ev.agent_id == spec.agent_id
        ),
        None,
    )
    if last_registration is None:
        raise ValueError(f"No AgentRegistered event for agent_id={spec.agent_id!r}")
    base_prompt = (
        spec.system_prompt if spec.system_prompt is not None else last_registration.system_prompt
    )
    system_prompt = build_full_system_prompt(
        base_prompt=base_prompt,
        role_name=last_registration.role_name,
    )
    history = build_message_history(
        events=events,
        agent_id=spec.agent_id,
        system_prompt=system_prompt,
        target_timestamp=events[-1].timestamp,
        cutoff_round=spec.at_round,
        tool_calls_only=True,
        channel_visibility=spec.channel_visibility,
        split_parallel_tool_calls=spec.provider == SELF_HOSTED_PROVIDER,
    )
    return _SeedHistory(history=history, system_prompt=system_prompt)


def _install_channel_visibility(
    spec: SwapAgent,
    runtime: SimulationRuntime,
) -> None:
    """Translate the swap's per-channel visibility into ``member_join_index`` values."""
    current_counts: dict[str, int] = {}
    for channel_id in spec.channel_visibility:
        try:
            current_counts[channel_id] = runtime.channel_router.get_message_count(
                channel_id=channel_id,
            )
        except KeyError:
            current_counts[channel_id] = 0
    per_channel = compute_per_channel_join_index(
        channel_visibility=spec.channel_visibility,
        current_channel_message_counts=current_counts,
        channel_message_count_at_round_start=runtime.channel_message_count_at_round_start,
    )
    runtime.channel_router.apply_replacement_visibility(
        agent_id=spec.agent_id,
        per_channel_join_index=per_channel,
    )
    logger.debug(
        "Applied per-channel join indices for %s: %s",
        spec.agent_id,
        per_channel,
    )
