"""``SessionSeatRunner``: drives one seat through an agent CLI's session.

The harnesses that run a seat inside another agent's own loop (Claude Code,
Codex) each provide a ``SeatSession`` and share this runner. A cycle sends one
prompt, the platform's initial prompt first and its continuation prompt after,
and reads the session until the CLI ends the turn. What the session reports
becomes the same events a pydantic-ai seat logs, so the event log, history
reconstruction, exports and metrics read such a seat the way they read any
other: one ``LLMResponseReceived`` per response with that response's own usage,
a ``ToolCallInvoked`` per call and a ``ToolResultReceived`` per result.

A turn the CLI reports as failed is logged as ``AgentRunCycleFailed`` and the
next cycle continues the same session. A session that raised is closed and
reopened on the same session, or started over with the initial prompt when
the CLI never reported one. A session that cannot reopen, or that raises on
``MAX_CONSECUTIVE_SESSION_FAILURES`` cycles in a row, ends the seat's run with
that error. Once a ``read_notifications`` wake ends the run for the seat, the
turn is interrupted rather than left to make one more model call, and the
runner stops.

The CLI compacts its context on its own schedule, so the seat's ``compaction``
setting does not apply; a seat that enables it is warned about at start.

However a turn ends, every response it started is logged, so each logged call
has the response that issued it. A call left without a result is logged as the
history rebuilder expects: it drops calls that never returned.
"""

import logging
from typing import NamedTuple

from glossogen.event_logger import EventLogger
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import (
    AgentRunCycleFailed,
    ContextCompacted,
    HarnessSessionBound,
    LLMResponseReceived,
    StopReason,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.thinking_part_record import ThinkingPartRecord
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.runners.agent_cost_accumulator import AgentCostAccumulator
from glossogen.runners.agent_run_result import AgentRunResult
from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runners.communication_protocol import build_full_system_prompt, runner_prompts_for
from glossogen.runners.harness_protocol import RunnerBuildContext
from glossogen.runners.read_notifications_tool import RunTermination
from glossogen.runners.session_harness.response_tracker import ResponseTracker
from glossogen.runners.session_harness.seat_session import (
    CompactionBoundary,
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    SeatOptions,
    SeatSession,
    SeatSessionFactory,
    SessionItem,
    SessionStarted,
    TextChunk,
    ThinkingChunk,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.runners.session_harness.seat_tools import build_seat_tools
from glossogen.runtime.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

TOOL_USE_STOP_REASON = "tool_use"
MAX_CONSECUTIVE_SESSION_FAILURES = 3
"""Cycles in a row a session may raise on before the seat stops. Both CLIs retry a
failed model request themselves, so a session that keeps raising is not one a
restart will mend."""


class SessionKeptFailing(RuntimeError):
    """A seat's session raised on too many cycles in a row."""


class _ResponseDraft:
    """One response's blocks, collected until the response completes."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.thinking: list[ThinkingPartRecord] = []
        self.tool_calls: list[ToolCallRequest] = []


class _OpenSession(NamedTuple):
    """A connected session and the tracker its tools consult."""

    session: SeatSession
    tracker: ResponseTracker


class SessionSeatRunner(AgentRunner):
    """Runs one seat through a session built by ``session_factory``.

    ``harness_name`` is the harness the seat runs under, as its session-bound
    and compaction events record it.
    """

    def __init__(
        self,
        context: RunnerBuildContext,
        session_factory: SeatSessionFactory,
        harness_name: str,
    ) -> None:
        self._context = context
        self._session_factory = session_factory
        self._harness_name = harness_name

    async def start(
        self,
        agent_config: AgentConfig,
        runtime: SimulationRuntime,
        cost_tracker: dict[str, float],
    ) -> AgentRunResult:
        """Run the seat until a wake ends the run for it or ``max_turns`` cycles have run."""
        if agent_config.initial_message_history is not None:
            raise ValueError(
                f"{self._harness_name} starts every seat fresh and cannot take "
                f"the reconstructed history given for {agent_config.agent_id}"
            )
        seat = _SeatRun(
            context=self._context,
            session_factory=self._session_factory,
            harness_name=self._harness_name,
            agent_config=agent_config,
            runtime=runtime,
            cost=AgentCostAccumulator(
                agent_id=agent_config.agent_id,
                model=agent_config.model,
                provider=agent_config.provider,
                event_bus=self._context.event_bus,
                cost_tracker=cost_tracker,
            ),
        )
        return await seat.run()


class _SeatRun:
    """The state of one seat's run: its session, its calls in flight, and its totals."""

    def __init__(
        self,
        context: RunnerBuildContext,
        session_factory: SeatSessionFactory,
        harness_name: str,
        agent_config: AgentConfig,
        runtime: SimulationRuntime,
        cost: AgentCostAccumulator,
    ) -> None:
        self._context = context
        self._session_factory = session_factory
        self._harness_name = harness_name
        self._config = agent_config
        self._runtime = runtime
        self._cost = cost
        self._termination = RunTermination()
        self._drafts: dict[str, _ResponseDraft] = {}
        self._calls: dict[str, ToolCallRequest] = {}
        self._session_id: str | None = None
        prompts = runner_prompts_for(
            role_name=agent_config.role_name,
            replacement=runtime.scenario.runner_prompts(agent_id=agent_config.agent_id),
        )
        self._initial_prompt = prompts.initial
        self._continuation_prompt = prompts.continuation
        self._system_prompt = build_full_system_prompt(
            base_prompt=agent_config.system_prompt, prompts=prompts
        )

    @property
    def _agent_id(self) -> str:
        return self._config.agent_id

    @property
    def _event_logger(self) -> EventLogger:
        return self._runtime.event_logger

    async def run(self) -> AgentRunResult:
        """Cycle until the run ends for the seat, then close its session."""
        logger.info(
            "Starting %s seat %s (%s) model=%s max_turns=%d",
            self._harness_name,
            self._agent_id,
            self._config.role_name,
            self._config.model,
            self._context.max_turns,
        )
        if self._config.compaction.enabled:
            logger.warning(
                "Agent %s enables compaction, which %s does not apply: the CLI compacts "
                "on its own schedule",
                self._agent_id,
                self._harness_name,
            )
        turns = 0
        opened: _OpenSession | None = None
        try:
            opened = await self._open()
            consecutive_failures = 0
            while turns < self._context.max_turns and not self._termination.is_set:
                cycle_tracker = opened.tracker
                try:
                    await self._run_cycle(
                        opened=opened, prompt=self._next_prompt(), cycle=turns + 1
                    )
                    consecutive_failures = 0
                except Exception as exc:
                    logger.exception("Agent %s cycle %d raised", self._agent_id, turns + 1)
                    await self._log_cycle_failure(
                        cycle=turns + 1, error_type=type(exc).__name__, message=str(exc)
                    )
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_SESSION_FAILURES:
                        raise SessionKeptFailing(
                            f"the {self._harness_name} session of {self._agent_id} raised on "
                            f"{consecutive_failures} cycles in a row"
                        ) from exc
                    if not self._termination.is_set:
                        await self._close(session=opened.session)
                        opened = await self._open()
                finally:
                    await self._close_open_responses(tracker=cycle_tracker)
                turns += 1
            if turns >= self._context.max_turns:
                logger.warning("Agent %s hit max_turns limit (%d)", self._agent_id, turns)
        finally:
            self._runtime.scenario.on_agent_retired(agent_id=self._agent_id)
            if opened is not None:
                await self._close(session=opened.session)
        logger.info(
            "Agent %s finished. Total turns: %d, total cost: $%.4f",
            self._agent_id,
            turns,
            self._cost.cumulative_cost_usd,
        )
        return AgentRunResult(
            agent_id=self._agent_id,
            total_cost_usd=self._cost.cumulative_cost_usd,
            total_turns=turns,
        )

    def _next_prompt(self) -> str:
        """The initial prompt until the CLI has reported a session, the continuation after."""
        if self._session_id is None:
            return self._initial_prompt
        return self._continuation_prompt

    async def _close(self, session: SeatSession) -> None:
        """Close a session; a failure to close is logged and does not stop the seat."""
        try:
            await session.close()
        except Exception:
            logger.exception("Agent %s session failed to close", self._agent_id)

    async def _close_open_responses(self, tracker: ResponseTracker) -> None:
        """Log every response the turn left open, so each logged call keeps its parent.

        Such a response never reported its usage, so it is logged with none, and
        a ``read_notifications`` handler waiting on it is released. Calls still
        waiting on a result are forgotten: the rebuilder drops a call that never
        returned.
        """
        for message_id in list(self._drafts):
            tracker.response_abandoned(message_id=message_id)
            await self._complete_response(
                completed=ResponseCompleted(
                    message_id=message_id,
                    stop_reason=TOOL_USE_STOP_REASON,
                    usage=TokenUsage(
                        input_tokens=0,
                        output_tokens=0,
                        cache_read_input_tokens=0,
                        cache_creation_input_tokens=0,
                    ),
                )
            )
        self._calls.clear()

    async def _bind_session(self, session_id: str) -> None:
        """Record the session the seat is on, once per change."""
        if session_id == self._session_id:
            return
        self._session_id = session_id
        await self._event_logger.log(
            event=HarnessSessionBound(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                harness=self._harness_name,
                session_id=session_id,
            )
        )

    async def _open(self) -> _OpenSession:
        """Connect a session, continuing the seat's transcript when it has one."""
        tracker = ResponseTracker()
        session = self._session_factory()
        await session.connect(
            options=SeatOptions(
                model=self._config.model,
                system_prompt=self._system_prompt,
                tools=build_seat_tools(
                    runtime=self._runtime,
                    agent_id=self._agent_id,
                    termination=self._termination,
                    tracker=tracker,
                ),
                max_output_tokens=self._config.max_tokens,
                seat_dir=self._context.run_dir / "harness" / self._agent_id,
                resume_session_id=self._session_id,
            )
        )
        return _OpenSession(session=session, tracker=tracker)

    async def _run_cycle(self, opened: _OpenSession, prompt: str, cycle: int) -> None:
        """Send one prompt and log everything the session reports until the turn ends."""
        await opened.session.send(prompt=prompt)
        async for item in opened.session.items():
            if isinstance(item, CycleEnded):
                await self._end_cycle(ended=item, cycle=cycle)
                return
            await self._handle(item=item, opened=opened)
        raise RuntimeError("the session stopped reporting before the turn ended")

    async def _handle(self, item: SessionItem, opened: _OpenSession) -> None:
        """Record one thing the session reported."""
        if isinstance(item, SessionStarted):
            await self._bind_session(session_id=item.session_id)
        elif isinstance(item, ResponseStarted):
            self._runtime.scenario.on_model_request_started(agent_id=self._agent_id)
            opened.tracker.response_started(message_id=item.message_id)
            self._drafts[item.message_id] = _ResponseDraft()
        elif isinstance(item, TextChunk):
            self._draft(message_id=item.message_id).texts.append(item.text)
        elif isinstance(item, ThinkingChunk):
            self._draft(message_id=item.message_id).thinking.append(
                ThinkingPartRecord(
                    content=item.thinking,
                    id=None,
                    signature=item.signature,
                    provider_name=item.provider_name,
                )
            )
        elif isinstance(item, ToolUseChunk):
            await self._record_tool_use(chunk=item, tracker=opened.tracker)
        elif isinstance(item, ResponseCompleted):
            opened.tracker.response_completed(message_id=item.message_id)
            await self._complete_response(completed=item)
        elif isinstance(item, ToolResultChunk):
            opened.tracker.call_finished(call_id=item.call_id)
            await self._record_tool_result(result=item, session=opened.session)
        elif isinstance(item, CompactionBoundary):
            await self._event_logger.log(
                event=ContextCompacted(
                    agent_id=self._agent_id,
                    round_number=self._runtime.current_round,
                    provider_name=self._harness_name,
                    summary_char_count=0,
                    summary_text="",
                    provider_details=item.details,
                )
            )

    def _draft(self, message_id: str) -> _ResponseDraft:
        draft = self._drafts.get(message_id)
        if draft is None:
            draft = _ResponseDraft()
            self._drafts[message_id] = draft
        return draft

    async def _record_tool_use(self, chunk: ToolUseChunk, tracker: ResponseTracker) -> None:
        call = ToolCallRequest(
            call_id=chunk.call_id, tool_name=chunk.tool_name, arguments=chunk.arguments
        )
        self._draft(message_id=chunk.message_id).tool_calls.append(call)
        self._calls[chunk.call_id] = call
        tracker.tool_used(
            message_id=chunk.message_id,
            call_id=chunk.call_id,
            is_wait=chunk.tool_name == READ_NOTIFICATIONS_TOOL_NAME,
        )
        await self._event_logger.log(
            event=ToolCallInvoked(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                call_id=call.call_id,
                tool_name=call.tool_name,
                arguments=call.arguments,
            )
        )

    async def _complete_response(self, completed: ResponseCompleted) -> None:
        """Log the response with its own usage, price it, and pass it through the gate."""
        draft = self._drafts.pop(completed.message_id, _ResponseDraft())
        stop_reason = StopReason.END_TURN
        if completed.stop_reason == TOOL_USE_STOP_REASON:
            stop_reason = StopReason.TOOL_USE
        text: str | None = None
        if draft.texts:
            text = "\n".join(draft.texts)
        thinking: str | None = None
        if draft.thinking:
            thinking = "\n".join(part.content for part in draft.thinking)
        await self._event_logger.log(
            event=LLMResponseReceived(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                thinking=thinking,
                thinking_parts=draft.thinking,
                text=text,
                tool_calls=draft.tool_calls,
                stop_reason=stop_reason,
                usage=completed.usage,
            )
        )
        usage = completed.usage
        self._cost.add_usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
            cache_write_tokens=usage.cache_creation_input_tokens,
        )
        await self._runtime.scenario.gate_model_response(
            agent_id=self._agent_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

    async def _record_tool_result(self, result: ToolResultChunk, session: SeatSession) -> None:
        """Log a result; a wait that ended the run interrupts the turn."""
        call = self._calls.pop(result.call_id, None)
        if call is None:
            logger.warning(
                "Agent %s got a result for unknown call %s", self._agent_id, result.call_id
            )
            return
        await self._event_logger.log(
            event=ToolResultReceived(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                tool_name=call.tool_name,
                call_id=call.call_id,
                arguments=call.arguments,
                result=result.content,
            )
        )
        if call.tool_name == READ_NOTIFICATIONS_TOOL_NAME and self._termination.is_set:
            await session.interrupt()

    async def _end_cycle(self, ended: CycleEnded, cycle: int) -> None:
        """Record the session the seat is on, and a failed turn unless the run had ended."""
        await self._bind_session(session_id=ended.session_id)
        logger.info(
            "Agent %s cycle %d ended; the CLI reports $%s for it",
            self._agent_id,
            cycle,
            ended.reported_cost_usd,
        )
        if ended.is_error and not self._termination.is_set:
            await self._log_cycle_failure(
                cycle=cycle, error_type="CycleEndedWithError", message=ended.error_text
            )

    async def _log_cycle_failure(self, cycle: int, error_type: str, message: str) -> None:
        await self._event_logger.log(
            event=AgentRunCycleFailed(
                agent_id=self._agent_id,
                round_number=self._runtime.current_round,
                cycle=cycle,
                error_type=error_type,
                message=message,
            )
        )
