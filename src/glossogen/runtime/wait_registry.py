"""Suspended agents and the conditions that resume them.

An agent on the ``workspace_action`` protocol ends a turn by calling
``wait_for_message`` or ``finish``. The runner does not execute that call: it
registers the agent here, parks the agent's coroutine, and resumes it with a wake
signal once a condition holds. While parked, the agent makes no model request.

Every wake condition is evaluated against the runtime's own state (channel
message counts against the agent's read cursor, the session's notification
queue), never against an edge signal that could have fired before the wait was
registered. Registration therefore checks the
conditions first and resumes at once if any already holds, which is what rules
out a lost wake-up between an agent's last observation and its wait.

Publishers call ``publish_channel_message`` and the session-level notification
listener after the corresponding state has changed.
Each registered wait resumes at most once; concurrent publishes for the same wait
collapse into one wake signal carrying every reason that held.
"""

import asyncio
import itertools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

from glossogen.channel_router import ChannelRouter
from glossogen.models.interaction_protocol import WaitKind
from glossogen.runtime.agent_session import AgentSession

logger = logging.getLogger(__name__)

CancelTimer = Callable[[], None]
ScheduleTimer = Callable[[float, Callable[[], None]], CancelTimer]
"""Schedule ``callback`` after a delay in seconds; returns a function that cancels it.

Injected so tests drive deadlines explicitly instead of waiting for real time.
"""

AgentTransition = Callable[[str], None]
"""Told the agent id when that agent parks or resumes; see ``WaitRegistry``."""


class WakeReason(str, Enum):
    """Why a suspended agent was resumed. A wake can carry several."""

    NEW_PUBLIC_MESSAGE = "new_public_message"
    LIFECYCLE = "lifecycle"
    DEADLINE = "deadline"


class WakeSignal(NamedTuple):
    """The reasons a wait resumed and how long the agent was parked."""

    reasons: list[WakeReason]
    waited_seconds: float


@dataclass
class RegisteredWait:
    """One parked agent: its conditions, deadline and the future the runner awaits."""

    wait_id: str
    agent_id: str
    round_id: int
    kind: WaitKind
    deadline_s: float | None
    implicit: bool
    registered_at: float
    future: asyncio.Future[WakeSignal]
    cancel_timer: CancelTimer | None = field(default=None)

    @property
    def resumed(self) -> bool:
        """True once a wake signal has been delivered or the wait was cancelled."""
        return self.future.done()


def asyncio_timer(delay_seconds: float, callback: Callable[[], None]) -> CancelTimer:
    """Schedule ``callback`` on the running loop after ``delay_seconds``."""
    handle = asyncio.get_running_loop().call_later(delay_seconds, callback)
    return handle.cancel


class WaitRegistry:
    """Registers waits, evaluates their conditions, and resumes each at most once."""

    def __init__(
        self,
        channel_router: ChannelRouter,
        agent_sessions: dict[str, AgentSession],
        current_round: Callable[[], int],
        schedule_timer: ScheduleTimer,
        clock: Callable[[], float],
        on_park: AgentTransition | None,
        on_resume: AgentTransition | None,
    ) -> None:
        """``on_park`` runs once a wait is installed and nothing holds yet, after its
        deadline timer; ``on_resume`` runs as a wait resumes. A virtual clock uses
        them to know which agents can still act.
        """
        self._on_park = on_park
        self._on_resume = on_resume
        self._channel_router = channel_router
        self._agent_sessions = agent_sessions
        self._current_round = current_round
        self._schedule_timer = schedule_timer
        self._clock = clock
        self._waits_by_agent: dict[str, RegisteredWait] = {}
        self._wait_ids = itertools.count(1)

    def register(
        self,
        agent_id: str,
        round_id: int,
        kind: WaitKind,
        deadline_s: float | None,
        implicit: bool,
    ) -> RegisteredWait:
        """Park ``agent_id`` until a condition of ``kind`` holds.

        Lifecycle notifications resume every wait. A ``message`` wait also
        resumes when a channel the agent belongs to holds a message, from someone
        else and visible to the agent, past the agent's read cursor.

        The conditions are checked before the wait is installed; one that already
        holds resumes the returned wait immediately, so a state change that landed
        between the agent's last observation and this call is not missed. An
        agent may hold one pending wait at a time.
        """
        session = self._agent_sessions[agent_id]
        existing = self._waits_by_agent.get(agent_id)
        if existing is not None and not existing.resumed:
            raise ValueError(f"Agent '{agent_id}' already has a pending wait {existing.wait_id}")
        loop = asyncio.get_running_loop()
        wait = RegisteredWait(
            wait_id=f"wait-{next(self._wait_ids)}",
            agent_id=agent_id,
            round_id=round_id,
            kind=kind,
            deadline_s=deadline_s,
            implicit=implicit,
            registered_at=self._clock(),
            future=loop.create_future(),
        )
        self._waits_by_agent[agent_id] = wait
        reasons = self._satisfied_reasons(wait=wait)
        if reasons:
            self._resume(wait=wait, reasons=reasons)
            return wait
        session.set_notification_listener(listener=lambda: self._publish_to(wait=wait))
        if deadline_s is not None:
            wait.cancel_timer = self._schedule_timer(
                deadline_s,
                lambda: self._resume(wait=wait, reasons=[WakeReason.DEADLINE]),
            )
        if self._on_park is not None:
            self._on_park(agent_id)
        return wait

    def pending_wait(self, agent_id: str) -> RegisteredWait | None:
        """The agent's wait that has not resumed yet, or None when it is not parked."""
        wait = self._waits_by_agent.get(agent_id)
        if wait is None or wait.resumed:
            return None
        return wait

    async def wait_for_resume(self, wait: RegisteredWait) -> WakeSignal:
        """Block the caller until ``wait`` has been resumed."""
        return await wait.future

    def cancel(self, agent_id: str) -> None:
        """Drop the agent's pending wait without a wake signal (runner shutdown)."""
        wait = self._waits_by_agent.pop(agent_id, None)
        if wait is None:
            return
        self._detach(wait=wait)
        if not wait.future.done():
            wait.future.cancel()

    def publish_channel_message(self, channel_id: str) -> None:
        """Re-evaluate every wait whose agent belongs to ``channel_id``."""
        for wait in list(self._waits_by_agent.values()):
            if channel_id in self._channel_router.get_agent_channel_ids(agent_id=wait.agent_id):
                self._publish_to(wait=wait)

    def _publish_to(self, wait: RegisteredWait) -> None:
        """Resume ``wait`` if any of its conditions holds now."""
        if wait.resumed:
            return
        reasons = self._satisfied_reasons(wait=wait)
        if reasons:
            self._resume(wait=wait, reasons=reasons)

    def _satisfied_reasons(self, wait: RegisteredWait) -> list[WakeReason]:
        """Every wake condition that holds for ``wait`` right now, in declaration order."""
        session = self._agent_sessions[wait.agent_id]
        reasons: list[WakeReason] = []
        same_round = self._current_round() == wait.round_id
        if same_round and wait.kind == "message":
            for channel_id in self._channel_router.get_agent_channel_ids(agent_id=wait.agent_id):
                if self._has_unread_from_others(session=session, channel_id=channel_id):
                    reasons.append(WakeReason.NEW_PUBLIC_MESSAGE)
                    break
        if session.has_pending_notifications() or session.terminated:
            reasons.append(WakeReason.LIFECYCLE)
        return reasons

    def _has_unread_from_others(self, session: AgentSession, channel_id: str) -> bool:
        """True when messages past the agent's read cursor include one it did not send."""
        history = self._channel_router.get_history(channel_id=channel_id)
        unread = history[session.get_last_seen_count(channel_id=channel_id) :]
        return any(
            message.sender_agent_id != session.agent_id and message.visible_to(session.agent_id)
            for message in unread
        )

    def _resume(self, wait: RegisteredWait, reasons: list[WakeReason]) -> None:
        """Deliver the wake signal once; later calls for the same wait are no-ops."""
        if wait.future.done():
            return
        self._detach(wait=wait)
        self._waits_by_agent.pop(wait.agent_id, None)
        signal = WakeSignal(reasons=reasons, waited_seconds=self._clock() - wait.registered_at)
        wait.future.set_result(signal)
        if self._on_resume is not None:
            self._on_resume(wait.agent_id)
        logger.info(
            "Agent %s wait %s resumed after %.1fs: %s",
            wait.agent_id,
            wait.wait_id,
            signal.waited_seconds,
            [reason.value for reason in reasons],
        )

    def _detach(self, wait: RegisteredWait) -> None:
        """Remove the listener and timer a pending wait installed."""
        self._agent_sessions[wait.agent_id].set_notification_listener(listener=None)
        if wait.cancel_timer is not None:
            wait.cancel_timer()
            wait.cancel_timer = None


def monotonic_clock() -> float:
    """The registry's default clock."""
    return time.monotonic()
