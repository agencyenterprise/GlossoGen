"""What a resumed ``read_notifications`` call returns to a dead_drop agent."""

from typing import Literal

from pydantic import BaseModel


class DeadDropWake(BaseModel):
    """One wake: why it happened, the briefings and messages it brought, and any notice.

    ``type`` is ``done`` once the session is over. ``messages`` carries the chat
    messages received under ``channel_mode=chat``; with no channel the rendered
    package leaves the field out. ``notice`` is the scenario's text when it released
    the agent from a wait.
    """

    type: Literal["wake", "done"]
    round: int
    wake_reasons: list[str]
    briefings: list[str]
    messages: list[str]
    notice: str | None
