"""Top-level orchestrator that wires together a scenario's agents, channels, tools,
and turn loop, then executes the simulation to completion.

Supports resuming a simulation from a checkpoint saved during a previous run
that ended with an error. On resume, channel messages, notebook entries, and
shared document contents are reconstructed from the event log, and the scenario's
internal state is restored from the last ``CheckpointSaved`` event.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from schmidt.agent_runner import AgentRunner
from schmidt.channel_router import ChannelRouter
from schmidt.checkpoint_loader import ResumeState
from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.llm.prompt_builder import PromptBuilder
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    AgentRegistered,
    CheckpointSaved,
    GroundTruthSnapshot,
    RoundStateAdvanced,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
    StateObservationSent,
    TurnAssigned,
)
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.scenario_protocol import SimulationScenario
from schmidt.simulation_state_protocol import SimulationStateProtocol
from schmidt.tools.builtin_notebook import (
    READ_NOTEBOOK_SPEC,
    WRITE_NOTEBOOK_SPEC,
    create_notebook_executors,
)
from schmidt.tools.builtin_pass_turn import PASS_TURN_SPEC, create_pass_turn_executor
from schmidt.tools.builtin_send_message import SEND_MESSAGE_SPEC, create_send_message_executor
from schmidt.tools.builtin_shared_documents import (
    LIST_DOCUMENTS_SPEC,
    READ_DOCUMENT_SPEC,
    WRITE_DOCUMENT_SPEC,
    create_shared_document_executors,
)
from schmidt.tools.builtin_think import THINK_SPEC, create_think_executor
from schmidt.tools.document_store import DocumentStore
from schmidt.tools.notebook_store import NotebookStore
from schmidt.tools.tool_executor import ToolExecutor
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class SimulationHub:
    """Orchestrates a single simulation run.

    Connects a scenario definition with the LLM provider, tool registry, and event
    logger. The ``run`` method sets up channels, registers tools, spawns agent tasks,
    and drives the turn loop until the scenario signals completion. Supports
    resuming from a checkpoint via the ``resume_state`` parameter.
    """

    def __init__(
        self,
        scenario: SimulationScenario,
        agents: list[AgentConfig],
        agent_providers: dict[str, LLMProvider],
        tool_registry: ToolRegistry,
        event_logger: EventLogger,
        resume_state: ResumeState | None,
        event_bus: EventBus,
    ) -> None:
        self._scenario = scenario
        self._agents = agents
        self._agent_providers = agent_providers
        self._tool_registry = tool_registry
        self._event_logger = event_logger
        self._resume_state = resume_state
        self._event_bus = event_bus

    async def run(self) -> None:
        """Execute the full simulation lifecycle.

        Sets up the channel router and prompt builder from the scenario.
        Registers built-in tools (send_message, pass_turn) and scenario-specific
        tools, creates an AgentRunner per agent, then enters the turn loop.
        Each turn asks the scenario for the next agent to act, wakes that agent,
        and waits for it to finish. After each turn, reports whether the agent
        sent any messages via ``last_turn_passed`` in SimulationState, enabling
        the scenario to track rotation progress. Logs simulation start, agent
        registrations, turn assignments, and simulation end events. Cancels all
        agent tasks on exit.

        When ``resume_state`` is provided, restores channel messages, notebooks,
        shared documents, and scenario state from the checkpoint, then continues
        the turn loop from the saved position.
        """
        agents = self._agents
        channels = self._scenario.get_channels()
        resuming = self._resume_state is not None

        logger.info(
            "Setting up simulation: scenario=%s, agents=%d, channels=%d, resuming=%s",
            self._scenario.name(),
            len(agents),
            len(channels),
            resuming,
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

        # Register built-in pass_turn tool
        pass_executor = create_pass_turn_executor(event_logger=self._event_logger)
        self._tool_registry.register(spec=PASS_TURN_SPEC, executor=pass_executor)

        # Register built-in think tool for private reasoning capture
        round_tracker = [0]
        think_executor = create_think_executor(
            event_logger=self._event_logger,
            round_number_getter=lambda: round_tracker[0],
        )
        self._tool_registry.register(spec=THINK_SPEC, executor=think_executor)

        # Create notebook store and register tools
        notebook_store = NotebookStore()
        notebook_executors = create_notebook_executors(
            event_logger=self._event_logger,
            round_number_getter=lambda: round_tracker[0],
            store=notebook_store,
        )
        self._tool_registry.register(
            spec=WRITE_NOTEBOOK_SPEC, executor=notebook_executors.write_executor
        )
        self._tool_registry.register(
            spec=READ_NOTEBOOK_SPEC, executor=notebook_executors.read_executor
        )

        # Create document store and register tools (when scenario defines documents)
        shared_doc_configs = self._scenario.get_shared_documents()
        document_store: DocumentStore | None = None
        if shared_doc_configs:
            document_store = DocumentStore(configs=shared_doc_configs)
            doc_executors = create_shared_document_executors(
                store=document_store,
                event_logger=self._event_logger,
                round_number_getter=lambda: round_tracker[0],
            )
            self._tool_registry.register(
                spec=LIST_DOCUMENTS_SPEC, executor=doc_executors.list_executor
            )
            self._tool_registry.register(
                spec=READ_DOCUMENT_SPEC, executor=doc_executors.read_executor
            )
            self._tool_registry.register(
                spec=WRITE_DOCUMENT_SPEC, executor=doc_executors.write_executor
            )
            logger.info(
                "Registered shared document tools for %d document(s)",
                len(shared_doc_configs),
            )

        # Register scenario-specific tools
        self._scenario.register_tools(registry=self._tool_registry)

        tool_executor = ToolExecutor(registry=self._tool_registry)

        if resuming:
            await self._event_logger.open_for_append()
        else:
            await self._event_logger.open()

        # Restore state from checkpoint or initialize fresh
        if resuming:
            rs = self._resume_state
            assert rs is not None
            turn_number = rs.turn_number
            current_round = rs.round_number
            last_turn_passed = rs.last_turn_passed
            round_tracker[0] = current_round

            self._scenario.restore_from_checkpoint(checkpoint=rs.scenario_checkpoint)

            _restore_channel_messages(
                channel_router=channel_router,
                messages_by_channel=rs.messages_by_channel,
            )
            notebook_store.restore(entries_by_agent=rs.notebook_entries)
            if document_store is not None:
                document_store.restore(contents=rs.shared_document_contents)

            logger.info(
                "Resumed from checkpoint: turn=%d, round=%d",
                turn_number,
                current_round,
            )

        else:
            turn_number = 0
            current_round = 0
            last_turn_passed = False

        # Log simulation start and agent registrations (always, including on resume)
        await self._event_logger.log(
            event=SimulationStarted(
                scenario_name=self._scenario.name(),
                scenario_description=self._scenario.scenario_description(),
                channel_ids=[ch.channel_id for ch in channels],
                scenario_config=self._scenario.get_scenario_config(),
            )
        )

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
                event_bus=self._event_bus,
            )

            runners[agent.agent_id] = runner
            wake_events[agent.agent_id] = wake
            turn_queues[agent.agent_id] = queue
            done_events[agent.agent_id] = done

        if resuming:
            rs = self._resume_state
            assert rs is not None
            for agent_id, last_round in rs.last_injected_rounds.items():
                if agent_id in runners:
                    runners[agent_id].set_last_injected_round(round_number=last_round)

        # Spawn agent tasks
        tasks: dict[str, asyncio.Task[None]] = {}
        for agent_id, runner in runners.items():
            task = asyncio.create_task(runner.run())
            task.add_done_callback(_make_agent_failure_callback(agent_id=agent_id))
            tasks[agent_id] = task
        logger.info("Spawned %d agent tasks: %s", len(tasks), list(tasks.keys()))

        run_status = RunStatus.SCENARIO_COMPLETE
        is_stateful = isinstance(self._scenario, SimulationStateProtocol)
        try:
            while True:
                state = SimulationState(
                    turn_number=turn_number,
                    messages_by_channel=channel_router.get_all_messages(),
                    active_agent_ids=[a.agent_id for a in agents],
                    last_turn_passed=last_turn_passed,
                )

                decision = await self._scenario.decide_next_turn(state=state)
                if decision is None:
                    logger.info("Scenario signaled completion after %d turns", turn_number)
                    break

                if decision.round_number > current_round:
                    if is_stateful:
                        await self._handle_round_transition(
                            scenario=self._scenario,  # type: ignore[arg-type]
                            agents=agents,
                            round_number=decision.round_number,
                        )
                    current_round = decision.round_number
                    round_tracker[0] = current_round

                turn_number += 1
                logger.debug("Dispatching turn %d to agent %s", turn_number, decision.agent_id)

                await self._event_logger.log(
                    event=TurnAssigned(
                        agent_id=decision.agent_id,
                        turn_number=turn_number,
                        round_number=decision.round_number,
                    )
                )

                # Save checkpoint after TurnAssigned so the log is consistent on resume
                await self._save_checkpoint(
                    turn_number=turn_number,
                    round_number=current_round,
                    last_turn_passed=last_turn_passed,
                    runners=runners,
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

                # Record turn outcome for the next decide_next_turn call
                runner = runners[agent_id]
                summary = runner.last_turn_summary
                last_turn_passed = len(summary.messages_sent) == 0

                # Log turn progress
                if summary.messages_sent:
                    msgs = ", ".join(summary.messages_sent)
                else:
                    msgs = "no messages"
                if summary.tools_called:
                    tools_used = ", ".join(summary.tools_called)
                else:
                    tools_used = "none"
                logger.info(
                    "[Turn %d] %s | tools: %s | sent: %s",
                    turn_number,
                    agent_id,
                    tools_used,
                    msgs,
                )

        except Exception:
            logger.exception("Simulation failed during turn loop")
            run_status = RunStatus.ERROR
            raise

        finally:
            # Cancel all agent tasks and wait for them to finish
            logger.debug("Cancelling %d agent tasks", len(tasks))
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

            if self._event_logger.is_open:
                total_msg = sum(len(msgs) for msgs in channel_router.get_all_messages().values())
                await self._event_logger.log(
                    event=SimulationEnded(
                        reason=run_status,
                        total_messages=total_msg,
                        total_turns=turn_number,
                    )
                )
                await self._event_logger.close()

    async def _save_checkpoint(
        self,
        turn_number: int,
        round_number: int,
        last_turn_passed: bool,
        runners: dict[str, AgentRunner],
    ) -> None:
        """Save a checkpoint event capturing the full simulation state at this turn boundary."""
        last_injected_rounds: dict[str, int] = {}
        for agent_id, runner in runners.items():
            last_injected_rounds[agent_id] = runner.last_injected_round

        await self._event_logger.log(
            event=CheckpointSaved(
                turn_number=turn_number,
                round_number=round_number,
                last_turn_passed=last_turn_passed,
                scenario_state=self._scenario.get_checkpoint(),
                last_injected_rounds=last_injected_rounds,
            )
        )

    async def _handle_round_transition(
        self,
        scenario: SimulationStateProtocol,
        agents: list[AgentConfig],
        round_number: int,
    ) -> None:
        """Advance world state between rounds for stateful scenarios.

        Calls ``advance_round`` on the state protocol, logs the transition report
        and ground truth snapshot, then logs a filtered observation for each agent.
        """
        logger.info("Advancing world state for round %d", round_number)

        report = scenario.advance_round(round_number=round_number)
        await self._event_logger.log(
            event=RoundStateAdvanced(
                round_number=round_number,
                transition_report=report.model_dump(mode="json"),
            )
        )

        ground_truth = scenario.get_ground_truth()
        await self._event_logger.log(
            event=GroundTruthSnapshot(
                round_number=round_number,
                state=ground_truth,
            )
        )

        for agent in agents:
            observation = scenario.get_agent_observation(agent_id=agent.agent_id)
            await self._event_logger.log(
                event=StateObservationSent(
                    agent_id=agent.agent_id,
                    round_number=round_number,
                    observation=observation,
                )
            )


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


def _restore_channel_messages(
    channel_router: ChannelRouter,
    messages_by_channel: dict[str, list[Any]],
) -> None:
    """Replay saved messages into the channel router to rebuild conversation history."""
    total = 0
    for _channel_id, messages in messages_by_channel.items():
        for msg in messages:
            channel_router.append_message(message=msg)
            total += 1
    logger.info("Restored %d channel messages across %d channels", total, len(messages_by_channel))
