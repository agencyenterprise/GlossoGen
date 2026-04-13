"""Pydantic models for notifications delivered to agents via their inbox queues.

Each notification type represents a distinct event the agent should react to.
Notifications are returned by the ``read_notifications`` MCP tool.
"""

from enum import Enum
from typing import Annotated, Union

from pydantic import BaseModel, Discriminator


class NotificationType(str, Enum):
    """Discriminator for the kind of activity notification."""

    NEW_MESSAGES = "new_messages"
    NEW_INFO = "new_info"
    DONE = "done"


class NewMessagesNotification(BaseModel):
    """One or more new messages appeared in channels the agent belongs to."""

    type: NotificationType = NotificationType.NEW_MESSAGES
    channels: list[str]


class NewInfoNotification(BaseModel):
    """New information delivered to the agent (rendered from a scenario injection)."""

    type: NotificationType = NotificationType.NEW_INFO
    text: str


class DoneNotification(BaseModel):
    """The simulation has ended. The agent should stop."""

    type: NotificationType = NotificationType.DONE
    reason: str


ActivityNotification = Annotated[
    Union[NewMessagesNotification, NewInfoNotification, DoneNotification],
    Discriminator("type"),
]
