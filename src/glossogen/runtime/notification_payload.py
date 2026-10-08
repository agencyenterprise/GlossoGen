"""What a resumed ``read_notifications`` call hands the scenario, and the default rendering.

When a parked agent resumes, the runner asks the scenario to render the result
of its ``read_notifications`` call. The scenario reads the agent's queue through
a ``NotificationInbox`` and decides what to take: the default takes the oldest
notification and leaves the rest queued, reporting how many remain.
"""

import json
from typing import Any, NamedTuple

from glossogen.channel_router import ChannelRouter
from glossogen.runtime.activity_notification import (
    ActivityNotification,
    DoneNotification,
    NewMessagesNotification,
    NoActivityNotification,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason, is_stale_message_notice

NO_ACTIVITY_DETAIL = "No new messages."


class NotificationInbox:
    """A parked agent's notification queue, as the rendering of its wake sees it.

    Taking a new-messages notification records its channels as read. A scenario
    that delivers message bodies itself drains them through the runtime before
    taking notifications, so the notices it then takes are already stale and are
    skipped.
    """

    def __init__(self, session: AgentSession, channel_router: ChannelRouter) -> None:
        self._session = session
        self._channel_router = channel_router

    def take_next(self) -> ActivityNotification | None:
        """Remove and return the oldest notification still worth delivering, or None."""
        while True:
            notification = self._session.take_next_notification()
            if notification is None:
                return None
            if not isinstance(notification, NewMessagesNotification):
                return notification
            fresh = [
                channel_id
                for channel_id in notification.channels
                if self._channel_router.get_message_count(channel_id=channel_id)
                > self._session.get_last_seen_count(channel_id=channel_id)
            ]
            if not fresh:
                continue
            for channel_id in fresh:
                self._session.record_channel_read(
                    channel_id=channel_id,
                    message_count=self._channel_router.get_message_count(channel_id=channel_id),
                )
            return NewMessagesNotification(channels=fresh)

    def take_lifecycle(self) -> list[ActivityNotification]:
        """Remove and return every notification other than a new-messages notice.

        Leaves the notices and every read position alone, so a scenario that
        delivers message bodies itself loses none that arrive while it renders:
        their notice stays queued and their bodies stay unread.
        """
        return self._session.take_notifications(
            take=lambda notification: not isinstance(notification, NewMessagesNotification)
        )

    def remaining(self) -> int:
        """How many notifications are still queued and worth delivering."""
        return sum(
            1
            for notification in self._session.pending_notifications()
            if not is_stale_message_notice(
                notification=notification,
                session=self._session,
                channel_router=self._channel_router,
            )
        )


class Wake(NamedTuple):
    """Why a parked agent resumed, and access to what it was sent while parked.

    ``terminated`` is true once the run is over for this agent; the runner stops
    it at the end of the cycle that received the rendered result, whatever the
    rendering says.
    """

    wait_for: WaitFor
    reasons: list[WakeReason]
    waited_seconds: float
    inbox: NotificationInbox
    terminated: bool
    done_reason: str


def notification_payload(
    notification: ActivityNotification, pending_count: int, current_round: int
) -> dict[str, Any]:
    """Serialize a notification with queue depth and the current simulation round.

    ``pending_count`` tells the agent how many additional notifications are
    still queued after this one. ``current_round`` is the round the simulation
    is in at delivery time, so the agent can recognise that instructions seen on
    a channel before the current round are stale; each ``read_channel`` and
    ``send_message`` response carries the same field.
    """
    payload = notification.model_dump()
    payload["pending_count"] = pending_count
    payload["current_round"] = current_round
    return payload


def render_default_notification(wake: Wake, current_round: int) -> str:
    """The platform's rendering: the oldest queued notification, as JSON.

    A wake with nothing queued is either the end of the run, rendered as
    ``done``, or a timeout, rendered as ``no_activity``.
    """
    notification = wake.inbox.take_next()
    if notification is None:
        if wake.terminated:
            notification = DoneNotification(reason=wake.done_reason)
        else:
            notification = NoActivityNotification(detail=NO_ACTIVITY_DETAIL)
    return json.dumps(
        notification_payload(
            notification=notification,
            pending_count=wake.inbox.remaining(),
            current_round=current_round,
        )
    )


def render_parallel_rejection(current_round: int, pending_count: int) -> str:
    """The result of a ``read_notifications`` call issued alongside other tool calls."""
    return json.dumps(
        notification_payload(
            notification=NoActivityNotification(
                detail=(
                    "read_notifications cannot be issued in parallel with other tool "
                    "calls. Wait for your other tool calls to return, observe their "
                    "results, then call read_notifications by itself in the next turn."
                ),
            ),
            pending_count=pending_count,
            current_round=current_round,
        )
    )
