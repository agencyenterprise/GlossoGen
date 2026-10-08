"""Agents parked in ``read_notifications`` and the conditions that resume them.

The runner answers a ``read_notifications`` call by registering the agent here
and awaiting the wait. While parked, the agent makes no model request.

Every wake condition is evaluated against the agent's notification queue, never
against an edge signal that could have fired before the wait was registered.
Registration therefore checks the conditions first and resumes at once if any
already holds, which rules out a lost wake-up between the agent's last tool
result and its wait. After that, the session's notification listener
re-evaluates the wait each time a notification is queued.

Each registered wait resumes at most once, with the reasons that held when it
was first found satisfied; a notification queued after that is left for the
rendering to deliver.
"""

import asyncio
import itertools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from glossogen.channel_router import ChannelRouter
from glossogen.runtime.activity_notification import (
    ActivityNotification,
    NewInfoNotification,
    NewMessagesNotification,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.wait_for import WaitFor

logger = logging.getLogger(__name__)

DEFAULT_ANY_TIMEOUT_SECONDS = 120.0
"""How long ``wait_for='any'`` waits by default when the call gives no ``timeout_s``."""

CancelTimer = Callable[[], None]
ScheduleWaitTimeout = Callable[[str, float, Callable[[], None]], CancelTimer]
"""Arm a timer for ``agent_id`` that runs ``fire`` after ``timeout_s``; returns a cancel.

The scenario supplies it, so a scenario that simulates time can count virtual
seconds, and a test can fire the timer itself instead of waiting.
"""

AgentTransition = Callable[[str], None]
"""Told the agent id when that agent parks or resumes."""


class WakeReason(str, Enum):
    """Why a parked agent was resumed. A wake can carry several."""

    NEW_NOTIFICATION = "new_notification"
    NEW_MESSAGE = "new_message"
    NEXT_ROUND = "next_round"
    DONE = "done"
    TIMEOUT = "timeout"


class WakeSignal(NamedTuple):
    """The reasons a wait resumed and how long the agent was parked."""

    reasons: list[WakeReason]
    waited_seconds: float


@dataclass
class RegisteredWait:
    """One parked agent: what it waits for, its deadline and the future the runner awaits."""

    wait_id: str
    agent_id: str
    wait_for: WaitFor
    deadline_s: float | None
    registered_at: float
    future: asyncio.Future[WakeSignal]
    cancel_timer: CancelTimer | None
    parked: bool
    """True from ``on_park`` until ``on_resume``, so the two hooks always pair."""

    @property
    def resumed(self) -> bool:
        """True once a wake signal has been delivered or the wait was cancelled."""
        return self.future.done()


def is_stale_message_notice(
    notification: ActivityNotification,
    session: AgentSession,
    channel_router: ChannelRouter,
) -> bool:
    """True for a new-messages notice whose every channel the agent has already read."""
    if not isinstance(notification, NewMessagesNotification):
        return False
    return all(
        channel_router.get_message_count(channel_id=channel_id)
        <= session.get_last_seen_count(channel_id=channel_id)
        for channel_id in notification.channels
    )


def wait_deadline(
    wait_for: WaitFor, timeout_s: float | None, default_any_timeout_s: float | None
) -> float | None:
    """The seconds after which a wait times out, or None for no deadline.

    An explicit ``timeout_s`` wins. Otherwise ``any`` uses the scenario's
    ``default_any_timeout_s``, and the other kinds have no deadline.
    """
    if timeout_s is not None:
        return timeout_s
    if wait_for is WaitFor.ANY:
        return default_any_timeout_s
    return None


class WaitRegistry:
    """Registers waits, evaluates their conditions, and resumes each at most once."""

    def __init__(
        self,
        channel_router: ChannelRouter,
        session_for: Callable[[str], AgentSession],
        schedule_wait_timeout: ScheduleWaitTimeout,
        clock: Callable[[], float],
        on_park: AgentTransition,
        on_resume: AgentTransition,
    ) -> None:
        """``session_for`` resolves an agent's current session, which an in-run swap
        replaces. ``on_park`` runs once a wait is installed and nothing satisfies it
        yet; ``on_resume`` runs as such a wait resumes. A wait satisfied at
        registration never parks, so neither runs for it.
        """
        self._channel_router = channel_router
        self._session_for = session_for
        self._schedule_wait_timeout = schedule_wait_timeout
        self._clock = clock
        self._on_park = on_park
        self._on_resume = on_resume
        self._waits_by_agent: dict[str, RegisteredWait] = {}
        self._wait_ids = itertools.count(1)

    def register(
        self, agent_id: str, wait_for: WaitFor, deadline_s: float | None
    ) -> RegisteredWait:
        """Park ``agent_id`` until a condition of ``wait_for`` holds or ``deadline_s`` passes.

        The conditions are checked before the wait is installed; one that already
        holds resumes the returned wait immediately. An agent may hold one pending
        wait at a time.
        """
        existing = self._waits_by_agent.get(agent_id)
        if existing is not None and not existing.resumed:
            raise ValueError(f"Agent '{agent_id}' already has a pending wait {existing.wait_id}")
        wait = RegisteredWait(
            wait_id=f"wait-{next(self._wait_ids)}",
            agent_id=agent_id,
            wait_for=wait_for,
            deadline_s=deadline_s,
            registered_at=self._clock(),
            future=asyncio.get_running_loop().create_future(),
            cancel_timer=None,
            parked=False,
        )
        self._waits_by_agent[agent_id] = wait
        reasons = self._satisfied_reasons(wait=wait)
        if reasons:
            self._resume(wait=wait, reasons=reasons)
            return wait
        self._session_for(agent_id).set_notification_listener(
            listener=lambda: self._publish_to(wait=wait)
        )
        # The timer is armed before the scenario hears of the park: a scenario
        # clock may advance once an agent parks, and the deadline has to be on
        # the clock before that. A clock that fires the timer from inside the
        # arming call resumes the wait at once, and then nothing parked.
        if deadline_s is not None:
            cancel_timer = self._schedule_wait_timeout(
                agent_id,
                deadline_s,
                lambda: self._resume(wait=wait, reasons=[WakeReason.TIMEOUT]),
            )
            if wait.future.done():
                return wait
            wait.cancel_timer = cancel_timer
        wait.parked = True
        self._on_park(agent_id)
        return wait

    def pending_wait(self, agent_id: str) -> RegisteredWait | None:
        """The agent's wait that has not resumed yet, or None when it is not parked."""
        wait = self._waits_by_agent.get(agent_id)
        if wait is None or wait.resumed:
            return None
        return wait

    def cancel(self, wait: RegisteredWait) -> None:
        """Drop ``wait`` without a wake signal, as when its runner is cancelled.

        Removes its listener and timer, and tells the scenario the agent is no
        longer parked if it was.
        """
        if self._waits_by_agent.get(wait.agent_id) is wait:
            del self._waits_by_agent[wait.agent_id]
        self._detach(wait=wait)
        if not wait.future.done():
            wait.future.cancel()
        self._unpark(wait=wait)

    def _publish_to(self, wait: RegisteredWait) -> None:
        """Resume ``wait`` if any of its conditions holds now."""
        if wait.resumed:
            return
        reasons = self._satisfied_reasons(wait=wait)
        if reasons:
            self._resume(wait=wait, reasons=reasons)

    def _satisfied_reasons(self, wait: RegisteredWait) -> list[WakeReason]:
        """Every wake condition that holds for ``wait`` right now.

        New-message notices for channels the agent has already read are dropped
        from the queue first: they announce nothing the agent has not seen.
        """
        session = self._session_for(wait.agent_id)
        session.discard_notifications(
            discard=lambda notification: is_stale_message_notice(
                notification=notification,
                session=session,
                channel_router=self._channel_router,
            )
        )
        queued = session.pending_notifications()
        reasons: list[WakeReason] = []
        if session.terminated:
            reasons.append(WakeReason.DONE)
        has_injection = any(
            isinstance(notification, NewInfoNotification) and notification.kind == "injection"
            for notification in queued
        )
        has_message = any(
            isinstance(notification, NewMessagesNotification) for notification in queued
        )
        if wait.wait_for is WaitFor.ANY and queued:
            reasons.append(WakeReason.NEW_NOTIFICATION)
        if wait.wait_for is WaitFor.MESSAGE and has_message:
            reasons.append(WakeReason.NEW_MESSAGE)
        if wait.wait_for is not WaitFor.ANY and has_injection:
            reasons.append(WakeReason.NEXT_ROUND)
        return reasons

    def _resume(self, wait: RegisteredWait, reasons: list[WakeReason]) -> None:
        """Deliver the wake signal once; later calls for the same wait are no-ops."""
        if wait.future.done():
            return
        self._detach(wait=wait)
        self._waits_by_agent.pop(wait.agent_id, None)
        signal = WakeSignal(reasons=reasons, waited_seconds=self._clock() - wait.registered_at)
        wait.future.set_result(signal)
        self._unpark(wait=wait)
        logger.info(
            "Agent %s wait %s (%s) resumed after %.1fs: %s",
            wait.agent_id,
            wait.wait_id,
            wait.wait_for.value,
            signal.waited_seconds,
            [reason.value for reason in reasons],
        )

    def _unpark(self, wait: RegisteredWait) -> None:
        """Run ``on_resume`` once for a wait that parked."""
        if wait.parked:
            wait.parked = False
            self._on_resume(wait.agent_id)

    def _detach(self, wait: RegisteredWait) -> None:
        """Remove the listener and timer a pending wait installed."""
        self._session_for(wait.agent_id).set_notification_listener(listener=None)
        if wait.cancel_timer is not None:
            wait.cancel_timer()
            wait.cancel_timer = None
