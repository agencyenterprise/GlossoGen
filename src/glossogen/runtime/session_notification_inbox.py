"""The runtime's ``NotificationInbox``: a parked agent's queue read through its session."""

from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.channel_router import ChannelRouter
from glossogen.runtime.wait_registry import is_stale_message_notice
from glossogen.scenario_contract.activity_notification import (
    ActivityNotification,
    NewMessagesNotification,
)
from glossogen.scenario_contract.notification_delivery import NotificationInbox


class SessionNotificationInbox(NotificationInbox):
    """A parked agent's notification queue, read from its session and the channel router.

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
