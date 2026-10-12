"""A ``SeatSession`` whose turns are written by the test, for a seat on ``SessionSeatRunner``.

It plays the same scripts as the scripted pydantic-ai model, one turn per model
response, and runs each tool call through the handler the runner served, so the
tools, the runtime and the event log are real. It reports items the way the CLI
does: a tool's handler starts as soon as its block is reported and runs
concurrently with the rest of the response, and the response completes before
the tool's result is reported.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from typing import NamedTuple

from glossogen.models.event_base import TokenUsage
from glossogen.runners.agent_tools import ToolOutcome, serialize_tool_result
from glossogen.runners.session_harness.seat_session import (
    CycleEnded,
    ResponseCompleted,
    ResponseStarted,
    SeatOptions,
    SessionItem,
    SessionStarted,
    TextChunk,
    ToolResultChunk,
    ToolUseChunk,
)
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn

SCRIPTED_USAGE = TokenUsage(
    input_tokens=100,
    output_tokens=10,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
)
"""What every scripted response reports using, so a test can check the sums."""


class ParallelToolTurn(NamedTuple):
    """One response issuing several tool calls at once."""

    calls: tuple[ToolTurn, ...]


class SessionCrash(NamedTuple):
    """The session raises, as a CLI process that died would.

    With ``mid_response`` set, it dies after streaming that call's block and
    before the response completes or the call runs.
    """

    reason: str
    mid_response: ToolTurn | None


class FailedTurn(NamedTuple):
    """The CLI ends the turn as failed with ``error_text``, as after a request it gave up on."""

    error_text: str


class ScriptedSessionCrashed(RuntimeError):
    """Raised by a scripted session playing a ``SessionCrash`` turn."""


SeatTurn = ScriptedTurn | ParallelToolTurn | SessionCrash | FailedTurn


class ScriptedSeatSession:
    """Plays a turn source against the tools the runner connects with."""

    def __init__(self, take_turn: Callable[[], SeatTurn], session_id: str) -> None:
        self._take_turn = take_turn
        self._session_id = session_id
        self._options: SeatOptions | None = None
        self._interrupted = False
        self._responses = 0
        self._calls = 0
        self.prompts: list[str] = []
        self.connections: list[SeatOptions] = []

    async def connect(self, options: SeatOptions) -> None:
        """Record the options; the tools they carry are what each call runs."""
        self._options = options
        self.connections.append(options)

    async def send(self, prompt: str) -> None:
        """Record the prompt; the turn is played as ``items`` is read."""
        self.prompts.append(prompt)
        self._interrupted = False

    async def items(self) -> AsyncIterator[SessionItem]:
        """Play turns until one ends with text, or the turn is interrupted."""
        yield SessionStarted(session_id=self._session_id)
        while True:
            turn = self._take_turn()
            if isinstance(turn, FailedTurn):
                yield CycleEnded(
                    session_id=self._session_id,
                    is_error=True,
                    error_text=turn.error_text,
                    reported_cost_usd=None,
                )
                return
            if isinstance(turn, SessionCrash):
                if turn.mid_response is not None:
                    message_id = self._next_message_id()
                    yield ResponseStarted(message_id=message_id)
                    yield ToolUseChunk(
                        message_id=message_id,
                        call_id=self._next_call_id(),
                        tool_name=turn.mid_response.tool_name,
                        arguments=dict(turn.mid_response.args),
                    )
                raise ScriptedSessionCrashed(turn.reason)
            message_id = self._next_message_id()
            yield ResponseStarted(message_id=message_id)
            if isinstance(turn, SayTurn):
                yield TextChunk(message_id=message_id, text=turn.text)
                yield ResponseCompleted(
                    message_id=message_id, stop_reason="end_turn", usage=SCRIPTED_USAGE
                )
                yield self._cycle_ended(is_error=False)
                return
            calls = _calls_in(turn=turn)
            running: list[tuple[str, asyncio.Task[ToolOutcome]]] = []
            for call in calls:
                call_id = self._next_call_id()
                yield ToolUseChunk(
                    message_id=message_id,
                    call_id=call_id,
                    tool_name=call.tool_name,
                    arguments=dict(call.args),
                )
                running.append((call_id, asyncio.create_task(self._run_tool(call=call))))
            yield ResponseCompleted(
                message_id=message_id, stop_reason="tool_use", usage=SCRIPTED_USAGE
            )
            for call_id, task in running:
                outcome = await task
                yield ToolResultChunk(
                    call_id=call_id,
                    content=serialize_tool_result(content=outcome.content),
                )
            if self._interrupted:
                yield self._cycle_ended(is_error=True)
                return

    async def interrupt(self) -> None:
        """End the turn after the results already reported."""
        self._interrupted = True

    async def close(self) -> None:
        """Nothing to release."""
        self._options = None

    async def _run_tool(self, call: ToolTurn) -> ToolOutcome:
        if self._options is None:
            raise RuntimeError("the scripted seat session is not connected")
        for seat_tool in self._options.tools:
            if seat_tool.name == call.tool_name:
                return await seat_tool.handler(dict(call.args))
        return ToolOutcome(content=f"No such tool: {call.tool_name}", is_error=True)

    def _cycle_ended(self, is_error: bool) -> CycleEnded:
        error_text = ""
        if is_error:
            error_text = "interrupted"
        return CycleEnded(
            session_id=self._session_id,
            is_error=is_error,
            error_text=error_text,
            reported_cost_usd=None,
        )

    def _next_message_id(self) -> str:
        self._responses += 1
        return f"{self._session_id}-msg-{self._responses}"

    def _next_call_id(self) -> str:
        self._calls += 1
        return f"{self._session_id}-call-{self._calls}"


def _calls_in(turn: ToolTurn | ParallelToolTurn) -> Sequence[ToolTurn]:
    if isinstance(turn, ToolTurn):
        return (turn,)
    return turn.calls
