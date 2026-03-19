"""Supervisor that launches the MCP server, game clock, and agent runners.

Wires everything together but does not control turn order — agents act
autonomously via MCP tools.
"""

import asyncio
import logging
from collections.abc import Callable

import httpx

from schmidt.event_logger import EventLogger
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    AgentConnected,
    AgentRegistered,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
)
from schmidt.runners.agent_runner_base import AgentRunner
from schmidt.runtime.agent_session import AgentSession
from schmidt.runtime.game_clock import GameClock
from schmidt.runtime.mcp_server import start_mcp_server
from schmidt.runtime.simulation_state import SimulationRuntime
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

MCP_SERVER_HOST = "127.0.0.1"
MCP_SERVER_PATH = "/mcp"


def _mcp_server_url(port: int) -> str:
    """Build the full MCP server URL for the given port."""
    return f"http://{MCP_SERVER_HOST}:{port}{MCP_SERVER_PATH}"


BASE_TOOL_NAMES = [
    "check_messages",
    "read_channel",
    "send_message",
    "list_channels",
    "get_channel_members",
]


class AutonomousSupervisor:
    """Launches the MCP server, game clock, and agent runners for a simulation."""

    def __init__(
        self,
        scenario: SimulationScenario,
        agent_configs: list[AgentConfig],
        event_logger: EventLogger,
        mcp_server_port: int,
        runner_factory: Callable[[], AgentRunner],
    ) -> None:
        self._scenario = scenario
        self._agent_configs = agent_configs
        self._event_logger = event_logger
        self._mcp_server_port = mcp_server_port
        self._runner_factory = runner_factory
        self._runtime: SimulationRuntime | None = None

    async def run(self) -> None:
        """Execute the full simulation lifecycle."""
        await self._event_logger.open()

        try:
            await self._run_simulation()
        except Exception:
            logger.exception("Simulation failed")
            total = self._count_total_messages()
            await self._event_logger.log(
                event=SimulationEnded(
                    reason=RunStatus.ERROR,
                    total_messages=total,
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
        for attempt in range(max_attempts):
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
            delay_min, delay_max = self._scenario.get_agent_reaction_delay_range(
                agent_id=config.agent_id,
            )
            agent_sessions[config.agent_id] = AgentSession(
                agent_id=config.agent_id,
                reaction_delay_min=delay_min,
                reaction_delay_max=delay_max,
            )

        # Build the simulation runtime (shared state) and store for error-path access.
        runtime = SimulationRuntime(
            scenario=self._scenario,
            channels=channels,
            event_logger=self._event_logger,
            agent_sessions=agent_sessions,
        )
        self._runtime = runtime

        # Build and wire the game clock.
        game_clock = GameClock(
            scenario=self._scenario,
            agent_sessions=agent_sessions,
            event_logger=self._event_logger,
            max_rounds=self._scenario.get_round_count(),
            max_round_duration_seconds=self._scenario.get_max_round_duration_seconds(),
        )
        runtime.add_on_message_callback(callback=game_clock.on_message_sent)

        # Log simulation start and agent registration.
        await self._event_logger.log(
            event=SimulationStarted(
                scenario_name=self._scenario.name(),
                scenario_description=self._scenario.scenario_description(),
                channel_ids=[ch.channel_id for ch in channels],
            )
        )
        for config in self._agent_configs:
            all_tool_names = BASE_TOOL_NAMES + config.tool_names
            await self._event_logger.log(
                event=AgentRegistered(
                    agent_id=config.agent_id,
                    role_name=config.role_name,
                    system_prompt=config.system_prompt,
                    channel_ids=config.channel_ids,
                    tool_names=all_tool_names,
                    model=config.model,
                )
            )

        mcp_server_url = _mcp_server_url(port=self._mcp_server_port)

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

        # Launch one agent runner per agent as concurrent tasks.
        agent_tasks = []
        for config in self._agent_configs:
            runner = self._runner_factory()
            task = asyncio.create_task(
                runner.start(
                    agent_config=config,
                    mcp_server_url=mcp_server_url,
                    event_logger=self._event_logger,
                ),
                name=f"agent-{config.agent_id}",
            )
            agent_tasks.append(task)
            await self._event_logger.log(
                event=AgentConnected(
                    agent_id=config.agent_id,
                    role_name=config.role_name,
                    model=config.model,
                )
            )
            logger.info("Launched agent %s (%s)", config.agent_id, config.role_name)

        # Run the game clock until termination.
        game_clock_task = asyncio.create_task(
            game_clock.run(),
            name="game-clock",
        )

        termination_status = await game_clock_task
        logger.info("Game clock finished: %s", termination_status.value)

        # Broadcast done to all agents.
        runtime.broadcast_done(reason=termination_status.value)

        # Wait for agent tasks to finish (they should exit after receiving done).
        for task in agent_tasks:
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
            )
        )
        logger.info("Simulation complete. Total messages: %d", total_messages)
