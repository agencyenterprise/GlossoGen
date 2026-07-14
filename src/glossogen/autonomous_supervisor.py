"""Supervisor that launches the MCP server, game clock, and agent runners.

Wires everything together but does not control turn order — agents act
autonomously via MCP tools.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import TypeAdapter

from glossogen.channel_router import compute_per_channel_join_index
from glossogen.db.run_registry import update_run_status_standalone
from glossogen.event_logger import EventLogger
from glossogen.message_rewind import RewindState
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import (
    AgentConnected,
    AgentRegistered,
    CaseInjectedMidRun,
    PostmortemDisabledMidRun,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
)
from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runtime.activity_notification import NewMessagesNotification
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.agent_swap import AgentSwapResources, execute_agent_swap
from glossogen.runtime.game_clock import GameClock
from glossogen.runtime.mcp_server import start_mcp_server
from glossogen.runtime.mcp_tools import BASE_TOOL_NAMES
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.scheduled_events import ScheduledEvent, SwapAgent
from glossogen.runtime.scheduler import RoundBoundaryScheduler
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

MCP_SERVER_HOST = "127.0.0.1"
MCP_SERVER_PATH = "/mcp"


def _mcp_server_url(port: int) -> str:
    """Build the full MCP server URL for the given port."""
    return f"http://{MCP_SERVER_HOST}:{port}{MCP_SERVER_PATH}"


class AutonomousSupervisor:
    """Launches the MCP server, game clock, and agent runners for a simulation."""

    def __init__(
        self,
        scenario: SimulationScenario,
        agent_configs: list[AgentConfig],
        event_logger: EventLogger,
        mcp_server_port: int,
        runner_factory: Callable[[], AgentRunner],
        resume_state: RewindState | None,
        run_id: str,
        provider: str,
        log_path: Path,
    ) -> None:
        self._scenario = scenario
        self._agent_configs = agent_configs
        self._event_logger = event_logger
        self._mcp_server_port = mcp_server_port
        self._runner_factory = runner_factory
        self._resume_state = resume_state
        self._run_id = run_id
        self._provider = provider
        self._log_path = log_path
        self._runtime: SimulationRuntime | None = None
        scheduled_events_raw_obj = scenario.get_scenario_config().get("scheduled_events", [])
        if isinstance(scheduled_events_raw_obj, list):
            scheduled_events_raw: list[Any] = list(cast(list[Any], scheduled_events_raw_obj))
        else:
            scheduled_events_raw = []
        scheduled = self._parse_scheduled_events(raw=scheduled_events_raw)
        already_fired_rounds: frozenset[int] = (
            resume_state.rounds_with_fired_scheduler_events
            if resume_state is not None
            else frozenset()
        )
        self._scheduler = RoundBoundaryScheduler(
            events=scheduled,
            already_fired_rounds=already_fired_rounds,
        )
        self._runner_tasks: dict[str, asyncio.Task[Any]] = {}
        self._cost_tracker: dict[str, float] = {}
        self._mcp_server_url = ""

    @staticmethod
    def _parse_scheduled_events(raw: list[Any]) -> list[ScheduledEvent]:
        """Validate and coerce raw schedule entries from scenario_config.

        ``scenario_config`` is a JSON-friendly dict produced by knob
        merging; the schedule entries arrive as plain dicts that must be
        re-validated through the discriminated ``ScheduledEvent`` union
        before the runtime can use them.
        """
        if not raw:
            return []
        adapter: TypeAdapter[list[ScheduledEvent]] = TypeAdapter(list[ScheduledEvent])
        return adapter.validate_python(raw)

    async def perform_agent_swap(self, spec: SwapAgent) -> None:
        """Scheduler-invoked hook: swap one agent for a fresh runner."""
        if self._runtime is None:
            raise RuntimeError("Runtime not initialised; cannot swap agents")
        resources = AgentSwapResources(
            runtime=self._runtime,
            runner_factory=self._runner_factory,
            runner_tasks=self._runner_tasks,
            log_path=self._log_path,
            run_dir=self._log_path.parent,
            mcp_server_url=self._mcp_server_url,
            cost_tracker=self._cost_tracker,
        )
        await execute_agent_swap(spec=spec, resources=resources)

    def _make_round_boundary_hook(
        self,
        runtime: SimulationRuntime,
    ) -> Callable[[int], Any] | None:
        """Build the round-boundary callback the game clock invokes per round.

        Returns ``None`` when no scheduled events are configured so the
        game clock skips the call. Otherwise the callback (1) snapshots
        per-channel message counts at round-start so subsequent
        ``ChannelVisibilityFromRound`` lookups resolve correctly and
        (2) dispatches any scheduled events for the round.
        """

        async def _hook(round_number: int) -> None:
            runtime.snapshot_round_start(round_number=round_number)
            await self._scheduler.dispatch(round_number=round_number, ops=self)

        if self._scheduler.empty:
            # Still snapshot per round even without scheduled events so
            # downstream tooling can rely on the field always being populated.
            async def _snapshot_only(round_number: int) -> None:
                runtime.snapshot_round_start(round_number=round_number)

            return _snapshot_only
        return _hook

    async def set_postmortem_enabled(self, round_number: int, enabled: bool) -> None:
        """Scheduler-invoked hook: toggle postmortem mid-run.

        Only ``enabled=False`` is supported (validated upstream by
        ``SetPostmortem``). Calls the world's ``disable_postmortem_globally``
        (declared on ``ScenarioWorld``) and emits ``PostmortemDisabledMidRun``.
        """
        if enabled:
            raise ValueError("Re-enabling postmortem mid-run is not supported")
        world = self._scenario.get_world()
        world.disable_postmortem_globally()
        await self._event_logger.log(event=PostmortemDisabledMidRun(round_number=round_number))
        logger.info("Postmortem disabled mid-run at round %d", round_number)

    async def inject_case_payload(self, round_number: int, payload: dict[str, Any]) -> None:
        """Scheduler-invoked hook: hand ``payload`` to the scenario to override the case.

        Delegates payload decoding + world-state mutation to the scenario's
        ``inject_case_payload`` (scenarios without an implementation raise
        ``NotImplementedError``). After the scenario succeeds, emits a core
        ``CaseInjectedMidRun`` event with the raw payload so resume-state
        reconstruction skips re-firing this boundary on subsequent resumes.
        """
        await self._scenario.inject_case_payload(round_number=round_number, payload=payload)
        await self._event_logger.log(
            event=CaseInjectedMidRun(round_number=round_number, scenario_payload=payload)
        )
        logger.info("Case injected mid-run at round %d", round_number)

    async def run(self) -> None:
        """Execute the full simulation lifecycle."""
        if self._resume_state is not None:
            await self._event_logger.open_for_append()
        else:
            await self._event_logger.open()

        try:
            await self._run_simulation()
        except Exception:
            logger.exception("Simulation failed")
            total = self._count_total_messages()
            current_round = self._runtime.current_round if self._runtime is not None else 1
            await self._event_logger.log(
                event=SimulationEnded(
                    reason=RunStatus.ERROR,
                    total_messages=total,
                    total_cost_usd=0.0,
                    round_number=current_round,
                )
            )
            raise
        finally:
            await self._event_logger.close()

    def _count_total_messages(self) -> int:
        """Count all messages across all channels, or 0 if runtime is not initialized."""
        if self._runtime is None:
            return 0
        all_messages = self._runtime.channel_router.get_all_messages()
        return sum(len(msgs) for msgs in all_messages.values())

    @staticmethod
    async def _wait_for_mcp_server(
        mcp_task: asyncio.Task[None],
        port: int,
    ) -> None:
        """Wait until the MCP server is accepting connections or detect startup failure."""
        max_attempts = 10
        for _attempt in range(max_attempts):
            if mcp_task.done():
                if mcp_task.cancelled():
                    raise RuntimeError("MCP server task was cancelled during startup")
                exc = mcp_task.exception()
                if exc is not None:
                    raise RuntimeError(f"MCP server failed to start: {exc}") from exc
                raise RuntimeError("MCP server task exited unexpectedly")

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        _mcp_server_url(port=port),
                        timeout=1.0,
                    )
                    if response.status_code < 500:
                        logger.info("MCP server ready on port %d", port)
                        return
            except httpx.ConnectError:
                logger.debug(
                    "MCP server not yet accepting connections on port %d",
                    port,
                    exc_info=True,
                )

            await asyncio.sleep(0.3)

        raise RuntimeError(
            f"MCP server did not become ready on port {port} after {max_attempts} attempts"
        )

    async def _run_simulation(self) -> None:
        """Core simulation logic."""
        channels = self._scenario.get_channels()

        # Build per-agent sessions with reaction delay config.
        agent_sessions: dict[str, AgentSession] = {}
        for config in self._agent_configs:
            agent_sessions[config.agent_id] = AgentSession(agent_id=config.agent_id)

        # Build per-agent tool allowlists from scenario-specific tool_names.
        agent_tool_allowlists: dict[str, frozenset[str]] = {
            config.agent_id: frozenset(config.tool_names) for config in self._agent_configs
        }

        # Build the world context (needs sessions and logger, not the runtime).
        world_context = WorldContext(
            agent_sessions=agent_sessions,
            event_logger=self._event_logger,
        )

        # Build the simulation runtime (shared state) and store for error-path access.
        # Anchor elapsed-time reporting: a fresh run starts now; a resumed run
        # reuses the original run's start so elapsed values stay continuous.
        if self._resume_state is not None:
            simulation_start_time = self._resume_state.simulation_start_time
        else:
            simulation_start_time = datetime.now(tz=UTC)

        runtime = SimulationRuntime(
            scenario=self._scenario,
            channels=channels,
            event_logger=self._event_logger,
            agent_sessions=agent_sessions,
            agent_tool_allowlists=agent_tool_allowlists,
            world_context=world_context,
            agent_configs=self._agent_configs,
            simulation_start_time=simulation_start_time,
        )
        self._runtime = runtime

        # Give the scenario a runtime handle so its MCP tool executors can
        # emit custom events (e.g. judge verdicts) and read the active round.
        self._scenario.bind_runtime(runtime=runtime)

        # Restore channel messages and agent read positions when resuming.
        resuming = self._resume_state is not None
        start_round = 1
        if self._resume_state is not None:
            runtime.channel_router.restore_messages(
                messages_by_channel=self._resume_state.messages_by_channel,
            )
            replaced_ids = self._resume_state.replaced_agent_ids
            visibility_map = self._resume_state.replaced_agent_channel_visibility
            round_snapshots = self._resume_state.channel_message_count_at_round_start
            runtime.seed_round_snapshots(snapshots=round_snapshots)
            # The source run may have channels the resumed world doesn't carry
            # (e.g. ``postmortem`` dropped via ``postmortem_disabled_at_start``).
            # Skip those — they have no message-count in the new router.
            current_counts: dict[str, int] = {
                channel_id: runtime.channel_router.get_message_count(channel_id=channel_id)
                for channel_id in self._resume_state.messages_by_channel
                if runtime.channel_router.channel_exists(channel_id=channel_id)
            }
            for agent_id in replaced_ids:
                # Translate per-channel visibility into concrete join indices and
                # apply them to the replaced agent. Channels not declared keep
                # whatever join_index they had on resume.
                per_channel = compute_per_channel_join_index(
                    channel_visibility=visibility_map.get(agent_id, {}),
                    current_channel_message_counts=current_counts,
                    channel_message_count_at_round_start=round_snapshots,
                )
                runtime.channel_router.apply_replacement_visibility(
                    agent_id=agent_id,
                    per_channel_join_index=per_channel,
                )
            for agent_id, session in agent_sessions.items():
                has_history = bool(self._resume_state.agent_message_histories.get(agent_id))
                was_replaced = agent_id in replaced_ids
                # Mark channels as seen for agents that either had prior
                # conversation history (plain --resume) or whose channel view
                # was just wiped (replace-agent). Agents in neither bucket —
                # e.g. all agents on a fork — should see restored messages as
                # new so they don't silently skip them on resume.
                if has_history or was_replaced:
                    for ch_id in runtime.channel_router.get_agent_channel_ids(
                        agent_id=agent_id,
                    ):
                        session.set_last_seen_count(
                            channel_id=ch_id,
                            count=runtime.channel_router.get_message_count(
                                channel_id=ch_id,
                            ),
                        )
            start_round = self._resume_state.round_number
            runtime.seed_last_injected_rounds(
                injected_rounds=self._resume_state.injected_rounds,
            )
            runtime.set_current_round(round_number=start_round)
            logger.info(
                "Resumed autonomous simulation at round %d",
                self._resume_state.round_number,
            )

        # Build and wire the game clock. The boundary hook is None when no
        # scheduled events are configured, so the per-round overhead is a
        # single None check.
        round_boundary_hook = self._make_round_boundary_hook(runtime=runtime)
        game_clock = GameClock(
            scenario=self._scenario,
            agent_sessions=agent_sessions,
            runtime=runtime,
            world_context=world_context,
            max_rounds=self._scenario.get_round_count(),
            max_round_duration_seconds=self._scenario.get_max_round_duration_seconds(),
            start_round=start_round,
            resuming=resuming,
            on_round_boundary=round_boundary_hook,
        )
        runtime.add_on_message_callback(callback=game_clock.on_message_sent)

        # Log simulation start (skip on resume — the forked JSONL already
        # contains it).  Agent registration is always logged so that
        # resumed/forked runs record the current model even if it differs
        # from the source run.
        if self._resume_state is None:
            await self._event_logger.log(
                event=SimulationStarted(
                    run_id=self._run_id,
                    scenario_name=self._scenario.name(),
                    scenario_description=self._scenario.scenario_description(),
                    channel_ids=[ch.channel_id for ch in channels],
                    scenario_config=self._scenario.get_scenario_config(),
                    provider=self._provider,
                    round_number=0,
                    timestamp=simulation_start_time,
                )
            )
        for config in self._agent_configs:
            all_tool_names = [*BASE_TOOL_NAMES, *config.tool_names]
            await self._event_logger.log(
                event=AgentRegistered(
                    agent_id=config.agent_id,
                    role_name=config.role_name,
                    system_prompt=config.system_prompt,
                    channel_ids=config.channel_ids,
                    tool_names=all_tool_names,
                    model=config.model,
                    provider=config.provider,
                    max_tokens=config.max_tokens,
                    round_number=0,
                )
            )

        mcp_server_url = _mcp_server_url(port=self._mcp_server_port)
        self._mcp_server_url = mcp_server_url

        # Start MCP server as a background task.
        mcp_task = asyncio.create_task(
            start_mcp_server(runtime=runtime, port=self._mcp_server_port),
            name="mcp-server",
        )

        # Wait for the MCP server to become ready or detect a startup failure.
        await self._wait_for_mcp_server(
            mcp_task=mcp_task,
            port=self._mcp_server_port,
        )

        # For resumed runs, inject the reconstructed message history so each
        # agent starts with proper multi-turn context of what happened.
        if self._resume_state is not None:
            for config in self._agent_configs:
                history = self._resume_state.agent_message_histories.get(config.agent_id)
                if history:
                    config.initial_message_history = history

        # Log the initial round and deliver injections BEFORE launching agents
        # so no events are recorded with round_number=0.
        await game_clock.start_initial_round()

        # Launch one agent runner per agent as concurrent tasks. ``cost_tracker``
        # is updated by each runner after every cycle so the supervisor can
        # still recover the agent's last known cost if its task gets cancelled
        # on shutdown before it can return an AgentRunResult.
        for config in self._agent_configs:
            runner = self._runner_factory()
            task = asyncio.create_task(
                runner.start(
                    agent_config=config,
                    mcp_server_url=mcp_server_url,
                    runtime=runtime,
                    cost_tracker=self._cost_tracker,
                ),
                name=f"agent-{config.agent_id}",
            )
            self._runner_tasks[config.agent_id] = task
            await self._event_logger.log(
                event=AgentConnected(
                    agent_id=config.agent_id,
                    role_name=config.role_name,
                    model=config.model,
                    round_number=runtime.current_round,
                )
            )
            logger.info("Launched agent %s (%s)", config.agent_id, config.role_name)

        # On resume, fire any scheduled events bucketed at round_start that
        # did not yet execute in the source, then deliver round_start's
        # injections so they land in the post-swap sessions (matching the
        # boundary-hook → deliver_injections order in _advance_round).
        # The scheduler's pre-seeded _fired_rounds set protects against
        # double-firing for rounds whose events already ran in the source.
        await game_clock.dispatch_resume_boundary_events()
        await game_clock.deliver_initial_round_injections()

        # Start the world simulation task.
        world = self._scenario.get_world()
        world_task = asyncio.create_task(
            world.run(context=world_context),
            name="world",
        )

        # Push wake-up notifications for resumed runs so agents respond immediately
        # instead of blocking on read_notifications() until the next round advances.
        if self._resume_state is not None:
            for agent_id, session in agent_sessions.items():
                agent_channel_ids = runtime.channel_router.get_agent_channel_ids(
                    agent_id=agent_id,
                )
                session.push_notification(
                    notification=NewMessagesNotification(channels=agent_channel_ids),
                )
            logger.info("Pushed wake-up notifications to %d agents", len(agent_sessions))

        # Run the game clock polling loop until termination.
        game_clock_task = asyncio.create_task(
            game_clock.run(),
            name="game-clock",
        )

        termination_status = await game_clock_task
        logger.info("Game clock finished: %s", termination_status.value)

        # Broadcast done to all agents.
        runtime.broadcast_done(reason=termination_status.value)

        # Wait for each agent task to finish. We don't consume the returned
        # AgentRunResult for cost — cost_tracker is the source of truth so
        # that cancelled agents still contribute their last recorded value.
        # Snapshot the task list because mid-run swaps may have replaced
        # entries; we wait on whichever runner is currently active per agent.
        for task in list(self._runner_tasks.values()):
            try:
                await asyncio.wait_for(task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Agent task %s did not finish in 30s, cancelling", task.get_name())
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            except Exception:
                logger.exception("Agent task %s failed", task.get_name())

        total_cost_usd = sum(self._cost_tracker.values())

        # Stop the world simulation.
        logger.info("Stopping world simulation")
        world_task.cancel()
        try:
            await world_task
        except asyncio.CancelledError:
            pass

        # Stop the MCP server.
        logger.info("Stopping MCP server")
        mcp_task.cancel()
        try:
            await mcp_task
        except asyncio.CancelledError:
            pass

        total_messages = self._count_total_messages()
        await self._event_logger.log(
            event=SimulationEnded(
                reason=termination_status,
                total_messages=total_messages,
                total_cost_usd=total_cost_usd,
                round_number=runtime.current_round,
            )
        )
        logger.info(
            "Simulation complete. Total messages: %d, total cost: $%.4f",
            total_messages,
            total_cost_usd,
        )

        run_dir_name = self._log_path.parent.name
        try:
            await update_run_status_standalone(
                scenario=self._scenario.name(),
                run_dir_name=run_dir_name,
                status=termination_status.value,
            )
        except Exception:
            logger.exception(
                "Failed to update runs.status to %s for %s/%s",
                termination_status.value,
                self._scenario.name(),
                run_dir_name,
            )
