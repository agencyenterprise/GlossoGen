"""What a resumed ``read_notifications`` call returns to a leaderboard_leak agent."""

from typing import Literal

from pydantic import BaseModel


class LeaderboardLeakWake(BaseModel):
    """One wake: why it happened, any briefing, the messages received, and any notice.

    ``type`` is ``done`` once the session is over. ``messages`` holds each message
    the agent had not read, as ``sender: text``, prefixed by its channel when the
    agent has more than one. ``notice`` is the scenario's text when it released the
    agent from a wait.
    """

    type: Literal["wake", "done"]
    round: int
    wake_reasons: list[str]
    briefings: list[str]
    messages: list[str]
    notice: str | None
