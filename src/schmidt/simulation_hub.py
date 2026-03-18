"""Top-level orchestrator that wires together a scenario's agents, channels, tools,
and turn loop, then executes the simulation to completion."""

import asyncio
import logging
from collections.abc import Callable

from schmidt.agent_runner import AgentRunner
from schmidt.channel_router import ChannelRouter
from schmidt.event_logger import EventLogger
from schmidt.llm.prompt_builder import PromptBuilder
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    AgentRegistered,
    EndReason,
    SimulationEnded,
    SimulationStarted,
    TurnAssigned,
)
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.scenario_protocol import SimulationScenario
from schmidt.tools.builtin_send_message import SEND_MESSAGE_SPEC, create_send_message_executor
from schmidt.tools.tool_executor import ToolExecutor
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class SimulationHub:
    """Orchestrates a single simulation run.

    Connects a scenario definition with the LLM provider, tool registry, and event
    logger. The ``run`` method sets up channels, registers tools, spawns agent tasks,
    and drives the turn loop until the scenario signals completion.
    """

    def __init__(
        self,
        scenario: SimulationScenario,
        agents: list[AgentConfig],
        agent_providers: dict[str, LLMProvider],
        tool_registry: ToolRegistry,
        event_logger: EventLogger,
    ) -> None:
        self._scenario = scenario
        self._agents = agents
        self._agent_providers = agent_providers
        self._tool_registry = tool_registry
        self._event_logger = event_logger

    async def run(self) -> None:
        """Execute the full simulation lifecycle.

        Sets up the channel router and prompt builder from the scenario.
        Registers built-in and scenario-specific tools, creates an AgentRunner
        per agent, then enters the turn loop. Each turn asks the scenario for the
        next agent to act, wakes that agent, and waits for it to finish before
        proceeding. Logs simulation start, agent registrations, turn assignments,
        and simulation end events. Cancels all agent tasks on exit.
        """
        agents = self._agents
        channels = self._scenario.get_channels()
        logger.info(
            "Setting up simulation: scenario=%s, agents=%d, channels=%d",
            self._scenario.name(),
            len(agents),
            len(channels),
        )

        channel_router = ChannelRouter(channels=channels)
        prompt_builder = PromptBuilder(
            scenario=self._scenario,
            channel_router=channel_router,
        )

        # Register built-in send_message tool
        send_executor = create_send_message_executor(
            channel_router=channel_router,
            event_logger=self._event_logger,
        )
        self._tool_registry.register(spec=SEND_MESSAGE_SPEC, executor=send_executor)

        # Register scenario-specific tools
        self._scenario.register_tools(registry=self._tool_registry)

        tool_executor = ToolExecutor(registry=self._tool_registry)

        await self._event_logger.open()

        # Log simulation start
        await self._event_logger.log(
            event=SimulationStarted(
                scenario_name=self._scenario.name(),
                scenario_description=self._scenario.scenario_description(),
                channel_ids=[ch.channel_id for ch in channels],
            )
        )

        # Log agent registrations
        for agent in agents:
            await self._event_logger.log(
                event=AgentRegistered(
                    agent_id=agent.agent_id,
                    role_name=agent.role_name,
                    system_prompt=agent.system_prompt,
                    channel_ids=agent.channel_ids,
                    tool_names=agent.tool_names,
                    model=agent.model,
                )
            )

        # Create per-agent async primitives and runners
        runners: dict[str, AgentRunner] = {}
        wake_events: dict[str, asyncio.Event] = {}
        turn_queues: dict[str, asyncio.Queue[TurnDecision]] = {}
        done_events: dict[str, asyncio.Event] = {}

        for agent in agents:
            wake = asyncio.Event()
            queue: asyncio.Queue[TurnDecision] = asyncio.Queue()
            done = asyncio.Event()

            runner = AgentRunner(
                config=agent,
                llm_provider=self._agent_providers[agent.agent_id],
                prompt_builder=prompt_builder,
                scenario=self._scenario,
                tool_registry=self._tool_registry,
                tool_executor=tool_executor,
                event_logger=self._event_logger,
                wake_event=wake,
                turn_queue=queue,
                done_event=done,
            )

            runners[agent.agent_id] = runner
            wake_events[agent.agent_id] = wake
            turn_queues[agent.agent_id] = queue
            done_events[agent.agent_id] = done

        # Spawn agent tasks
        tasks: dict[str, asyncio.Task[None]] = {}
        for agent_id, runner in runners.items():
            task = asyncio.create_task(runner.run())
            task.add_done_callback(_make_agent_failure_callback(agent_id=agent_id))
            tasks[agent_id] = task
        logger.info("Spawned %d agent tasks: %s", len(tasks), list(tasks.keys()))

        turn_number = 0
        end_reason = EndReason.SCENARIO_COMPLETE
        try:
            while True:
                state = SimulationState(
                    turn_number=turn_number,
                    messages_by_channel=channel_router.get_all_messages(),
                    active_agent_ids=[a.agent_id for a in agents],
                )

                decision = await self._scenario.decide_next_turn(state=state)
                if decision is None:
                    logger.info("Scenario signaled completion after %d turns", turn_number)
                    break

                turn_number += 1
                logger.debug("Dispatching turn %d to agent %s", turn_number, decision.agent_id)

                await self._event_logger.log(
                    event=TurnAssigned(
                        agent_id=decision.agent_id,
                        turn_number=turn_number,
                        channel_id=decision.channel_id,
                        round_number=decision.round_number,
                    )
                )

                # Check if agent task is still alive
                agent_id = decision.agent_id
                agent_task = tasks[agent_id]
                if agent_task.done():
                    exc = agent_task.exception()
                    raise RuntimeError(
                        f"Agent task '{agent_id}' failed before turn {turn_number}"
                    ) from exc

                # Wake the target agent
                done_events[agent_id].clear()
                await turn_queues[agent_id].put(decision)
                wake_events[agent_id].set()

                # Wait for agent done OR agent task crash
                await _wait_for_agent(
                    done_event=done_events[agent_id],
                    agent_task=agent_task,
                    agent_id=agent_id,
                )

                # Log turn progress
                runner = runners[agent_id]
                summary = runner.last_turn_summary
                if summary.messages_sent:
                    msgs = ", ".join(summary.messages_sent)
                else:
                    msgs = "no messages"
                if summary.tools_called:
                    tools_used = ", ".join(summary.tools_called)
                else:
                    tools_used = "none"
                logger.info(
                    "[Turn %d] %s -> %s | tools: %s | sent: %s",
                    turn_number,
                    agent_id,
                    decision.channel_id,
                    tools_used,
                    msgs,
                )

        except Exception:
            logger.exception("Simulation failed during turn loop")
            end_reason = EndReason.ERROR
            raise

        finally:
            # Cancel all agent tasks and wait for them to finish
            logger.debug("Cancelling %d agent tasks", len(tasks))
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

            if self._event_logger.is_open:
                await self._event_logger.log(
                    event=SimulationEnded(
                        reason=end_reason,
                        total_turns=turn_number,
                    )
                )
                await self._event_logger.close()


async def _wait_for_agent(
    done_event: asyncio.Event,
    agent_task: asyncio.Task[None],
    agent_id: str,
) -> None:
    """Wait for the agent to signal completion or detect a mid-turn crash.

    Races the done_event against the agent task itself. If the task finishes
    before the done_event is set, the agent crashed mid-turn.
    """
    done_future = asyncio.ensure_future(done_event.wait())
    finished, _pending = await asyncio.wait(
        [done_future, agent_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if agent_task in finished:
        # Agent crashed mid-turn; cancel the done_future we created
        done_future.cancel()
        if agent_task.cancelled():
            raise RuntimeError(f"Agent task '{agent_id}' was cancelled during its turn")
        exc = agent_task.exception()
        if exc is not None:
            raise RuntimeError(f"Agent task '{agent_id}' crashed during its turn") from exc
        raise RuntimeError(f"Agent task '{agent_id}' exited unexpectedly during its turn")

    # Normal completion — cancel only our done_future wrapper, never the agent task
    done_future.cancel()


def _make_agent_failure_callback(agent_id: str) -> Callable[[asyncio.Task[None]], None]:
    """Return a done-callback that logs unhandled agent task exceptions."""

    def _on_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.exception(
                "Agent task '%s' failed with unhandled exception",
                agent_id,
                exc_info=exc,
            )

    return _on_done
