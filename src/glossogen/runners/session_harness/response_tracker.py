"""Which response each ``read_notifications`` call came from, and when that response ended.

A ``read_notifications`` call issued beside other tool calls must not park. The
CLI runs a tool as soon as its block has streamed, before the rest of the
response is known, so the handler waits for the response to complete and then
counts its tool calls. The CLI writes a tool-use block to its output before it
asks this process to run that tool, so the runner always records the block
first; the handler takes the next recorded ``read_notifications`` call, waiting
for it if the runner has not read that far yet.

A call the handler never sees, because the CLI refused its arguments against the
schema, still gets a result. The runner reports that result, and the tracker
skips that call, so the next handler is not matched to it.

A response the turn left open, because its stream ended without completing it,
is abandoned when the turn ends. A handler waiting on it is released with that
verdict rather than left waiting, and does not park: the model never received
the response, so nothing would read the wake.
"""

import asyncio
from enum import Enum
from typing import NamedTuple


class WaitCallVerdict(Enum):
    """What a ``read_notifications`` handler does once its response is settled."""

    PARK = "park"
    SHARES_RESPONSE = "shares_response"
    RESPONSE_ABANDONED = "response_abandoned"


class _WaitCall(NamedTuple):
    message_id: str
    call_id: str


class ResponseTracker:
    """Records responses and their tool calls as the runner reads them."""

    def __init__(self) -> None:
        self._tool_use_counts: dict[str, int] = {}
        self._completed: dict[str, asyncio.Event] = {}
        self._wait_calls: asyncio.Queue[_WaitCall] = asyncio.Queue()
        self._finished_calls: set[str] = set()
        self._abandoned: set[str] = set()

    def response_started(self, message_id: str) -> None:
        """Open a response."""
        self._tool_use_counts.setdefault(message_id, 0)
        self._completion_event(message_id=message_id)

    def tool_used(self, message_id: str, call_id: str, is_wait: bool) -> None:
        """Count a tool call in ``message_id``; a wait call is queued for its handler."""
        self._tool_use_counts[message_id] = self._tool_use_counts.get(message_id, 0) + 1
        if is_wait:
            self._wait_calls.put_nowait(_WaitCall(message_id=message_id, call_id=call_id))

    def response_completed(self, message_id: str) -> None:
        """Close a response, releasing any handler waiting on it."""
        self._completion_event(message_id=message_id).set()

    def response_abandoned(self, message_id: str) -> None:
        """Close a response that never completed, releasing its handler without parking it."""
        self._abandoned.add(message_id)
        self._completion_event(message_id=message_id).set()

    def call_finished(self, call_id: str) -> None:
        """Record that ``call_id`` has its result, so no handler is matched to it later."""
        self._finished_calls.add(call_id)

    async def next_wait_call_verdict(self) -> WaitCallVerdict:
        """Wait for the next unanswered wait call's response to settle, then say what to do."""
        wait_call = await self._wait_calls.get()
        while wait_call.call_id in self._finished_calls:
            wait_call = await self._wait_calls.get()
        await self._completion_event(message_id=wait_call.message_id).wait()
        if wait_call.message_id in self._abandoned:
            return WaitCallVerdict.RESPONSE_ABANDONED
        if self._tool_use_counts[wait_call.message_id] > 1:
            return WaitCallVerdict.SHARES_RESPONSE
        return WaitCallVerdict.PARK

    def _completion_event(self, message_id: str) -> asyncio.Event:
        event = self._completed.get(message_id)
        if event is None:
            event = asyncio.Event()
            self._completed[message_id] = event
        return event
