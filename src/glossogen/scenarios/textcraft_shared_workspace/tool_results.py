"""What textcraft's ``send_message`` and ``read_notifications`` return to an agent."""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.mcp_responses import SendReceipt
from glossogen.runtime.activity_notification import NotificationType


class WorkspaceSendResult(SendReceipt):
    """The receipt of a message, with the sender's current view of the workspace.

    ``status`` is ``SENT`` or ``REJECTED``, never ``CONFLICT``: a send here is
    never held for unread messages. ``workspace`` carries the depot, the
    changes since the sender last looked, and the messages it had not seen, so
    a send refreshes the sender's view; it is None when nothing was sent.
    """

    detail: str
    token_count: int
    current_round: int
    workspace: str | None


class LifecycleEntry(BaseModel):
    """One notification drained from the agent's queue when it resumed."""

    type: NotificationType
    text: str | None
    reason: str | None


class WorkspaceWake(BaseModel):
    """What a resumed ``read_notifications`` call returns.

    ``type`` is ``wake``, or ``done`` once the run is over; never ``no_activity``,
    so history cleanup never mistakes it for an empty poll.
    ``lifecycle`` carries briefings and the end of the run; ``workspace`` the
    depot and every message that arrived while the agent was parked.
    """

    type: Literal["wake", "done"]
    wake_reasons: list[str]
    round: int
    waited_seconds: float
    workspace: str | None
    lifecycle: list[LifecycleEntry]
