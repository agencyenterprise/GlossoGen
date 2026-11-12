"""What a scenario reads about agents parked in ``read_notifications``.

The runtime's wait registry parks the agents and resumes them; a scenario sees
each parked agent's ``ParkedWait`` and the ``WakeReason`` values a resume carries.
"""

from enum import Enum
from typing import NamedTuple

from glossogen.models.wait_for import WaitFor

DEFAULT_ANY_TIMEOUT_SECONDS = 120.0
"""How long ``wait_for='any'`` waits by default when the call gives no ``timeout_s``."""


class WakeReason(str, Enum):
    """Why a parked agent was resumed. A wake can carry several."""

    NEW_NOTIFICATION = "new_notification"
    NEW_MESSAGE = "new_message"
    NEXT_ROUND = "next_round"
    DONE = "done"
    TIMEOUT = "timeout"
    RELEASED = "released"


class ParkedWait(NamedTuple):
    """What a parked agent waits for, and its deadline in seconds, or None for none."""

    wait_for: WaitFor
    deadline_s: float | None
