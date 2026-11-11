"""What a ``read_notifications`` call waits for before it returns."""

from enum import Enum


class WaitFor(str, Enum):
    """The condition that resumes an agent parked in ``read_notifications``.

    ``ANY`` resumes on the next notification of any kind, or after a default
    timeout. ``MESSAGE`` resumes on a teammate's message or the next injection.
    ``NEXT_ROUND`` is the agent declaring it has finished: it resumes on the next
    injection, which is the next round's briefing or a postmortem briefing. A
    ``done`` notification resumes every kind, and so does an explicit timeout.
    """

    ANY = "any"
    MESSAGE = "message"
    NEXT_ROUND = "next_round"
