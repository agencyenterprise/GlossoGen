"""Async event logger that writes simulation events as newline-delimited JSON to a file.

Publishes each logged event to an ``EventBus`` for real-time delivery to SSE
subscribers when a bus is provided at construction time. Optionally commits
meaningful state changes to a ``RunRepository`` for git-backed history.
"""

import asyncio
import logging
from pathlib import Path

import aiofiles
import orjson

from schmidt.event_bus import EventBus
from schmidt.models.event import (
    InjectionDelivered,
    MessageSent,
    RoundAdvanced,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
    ToolResultReceived,
)
from schmidt.run_repository import RunRepository

logger = logging.getLogger(__name__)

# Event types that do NOT trigger a git commit. These are high-volume events
# that don't affect forkable simulation state. They are still written to JSONL
# but only captured in git as part of the next meaningful event's diff.
# All other event types (including any new ones added by scenarios) are
# committed automatically.
_NON_COMMITTABLE_TYPES: frozenset[str] = frozenset(
    {
        "llm_response_received",
        "tool_call_invoked",
        "agent_connected",
    }
)


def _build_commit_message(event: SimulationEvent) -> str:
    """Build a structured git commit message for a simulation event."""
    event_type = event.event_type
    event_id = event.event_id
    timestamp = event.timestamp.isoformat()

    if isinstance(event, SimulationStarted):
        summary = f"{event_type}: {event.scenario_name} (run {event.run_id[:8]})"
    elif isinstance(event, MessageSent):
        msg = event.message
        summary = (
            f"{event_type}: {msg.sender_agent_id} -> {msg.channel_id} (round {event.round_number})"
        )
    elif isinstance(event, ToolResultReceived):
        summary = (
            f"{event_type}: {event.tool_name} by {event.agent_id} (round {event.round_number})"
        )
    elif isinstance(event, RoundAdvanced):
        summary = f"{event_type}: round {event.round_number} ({event.trigger})"
    elif isinstance(event, InjectionDelivered):
        summary = f"{event_type}: {event.agent_id} (round {event.round_number})"
    elif isinstance(event, SimulationEnded):
        summary = f"{event_type}: {event.reason.value}"
    else:
        summary = event_type

    metadata = f"event_id: {event_id}\ntimestamp: {timestamp}"
    if isinstance(event, MessageSent):
        metadata += f"\nmessage_id: {event.message.message_id}"
    return f"{summary}\n\n{metadata}"


class EventLogger:
    """Writes ``SimulationEvent`` objects as newline-delimited JSON (JSONL) to a binary file.

    When a ``RunRepository`` is provided, committable events also trigger a
    git commit capturing the updated JSONL and any workspace file changes.
    """

    def __init__(self, log_path: Path, event_bus: EventBus, repo: RunRepository | None) -> None:
        """Store the target log file path. The file is not opened until ``open()`` is called."""
        self._log_path = log_path
        self._file: aiofiles.threadpool.binary.AsyncBufferedIOBase | None = None
        self._event_bus = event_bus
        self._current_round = 1
        self._write_lock = asyncio.Lock()
        self._repo = repo

    @property
    def current_round(self) -> int:
        """The most recent round number, updated automatically when RoundAdvanced is logged."""
        return self._current_round

    def initialize_round_number(self, round_number: int) -> None:
        """Seed ``current_round`` from a resumed run's rewind state.

        On resume, the next ``RoundAdvanced`` is not logged until the game
        phase of the resumed round ends, so any tool-call events emitted in
        the meantime would otherwise be tagged with the default round
        number. Callers must invoke this once before the runtime starts so
        every event recorded after resume carries the correct round.
        """
        self._current_round = round_number

    async def open(self) -> None:
        """Create parent directories if needed and open the log file for writing.

        Truncates any existing file so each simulation run produces a clean log.
        """
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = await aiofiles.open(self._log_path, mode="wb")
        logger.info("Event log opened: %s", self._log_path)

    async def open_for_append(self) -> None:
        """Open the log file in append mode for resuming a simulation.

        Does not truncate the existing content. Raises ``FileNotFoundError``
        if the log file does not exist.
        """
        if not self._log_path.exists():
            raise FileNotFoundError(f"Cannot resume: log file not found at {self._log_path}")
        self._file = await aiofiles.open(self._log_path, mode="ab")
        logger.info("Event log opened for append (resume): %s", self._log_path)

    async def log(self, event: SimulationEvent) -> None:
        """Serialize ``event`` to JSON, write it as a single line, and flush.

        Also publishes the event to the event bus for live streaming.
        For committable event types, triggers a git commit when a
        ``RunRepository`` is configured.
        Raises ``RuntimeError`` if the logger has not been opened.
        """
        if self._file is None:
            raise RuntimeError("EventLogger is not open. Call open() first.")
        if isinstance(event, RoundAdvanced):
            self._current_round = event.round_number
        event_dict = event.model_dump(mode="json")
        data = orjson.dumps(event_dict) + b"\n"
        async with self._write_lock:
            await self._file.write(data)
            await self._file.flush()
            if self._repo is not None and event.event_type not in _NON_COMMITTABLE_TYPES:
                await self._commit_event(event=event)
        self._event_bus.publish(event=event_dict)

    async def _commit_event(self, event: SimulationEvent) -> None:
        """Commit the current JSONL state and any workspace files to git."""
        assert self._repo is not None
        message = _build_commit_message(event=event)
        try:
            await self._repo.commit(message=message, paths=None)
        except RuntimeError:
            logger.exception("Git commit failed for event %s", event.event_id)

    async def close(self) -> None:
        """Close the underlying file handle if it is open and reset internal state."""
        if self._file is not None:
            await self._file.close()
            self._file = None
            logger.info("Event log closed: %s", self._log_path)
