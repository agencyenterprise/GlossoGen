"""Seeded ``(where, when)`` draws for the surprise_party scenario.

Two fixed pools of plausible venues and times. The scenario draws one
``(where, when)`` per "party era" — the initial draw at construction time
and a fresh draw every time Chris uncovers the current party. Each new
draw avoids reusing the previously active ``(where, when)`` pair.
"""

import random
from typing import NamedTuple


class PartyDraw(NamedTuple):
    """Ground-truth surprise party details for one era of the simulation."""

    where: str
    when: str


_VENUE_POOL: tuple[str, ...] = (
    "the rooftop bar on Main Street",
    "Luigi's pizza place",
    "the bowling alley downtown",
    "Maya's apartment",
    "the lakeside cabin",
    "the karaoke lounge",
    "the back room at The Anchor pub",
    "the community garden pavilion",
    "the art gallery on 5th",
    "the jazz club basement",
    "the riverside park gazebo",
    "the dim sum place on Oak",
)

_TIME_POOL: tuple[str, ...] = (
    "Friday 7pm",
    "Saturday 6pm",
    "Saturday 8pm",
    "Sunday afternoon at 2pm",
    "Friday night at 9pm",
    "Saturday at noon",
    "Thursday at 7:30pm",
    "Saturday afternoon at 3pm",
    "Sunday evening at 6pm",
    "Friday at 8pm",
    "Saturday morning at 11am",
    "Sunday brunch at 11am",
)


class PartyRng:
    """Deterministic source of ``(where, when)`` draws.

    Wraps a seeded ``random.Random``. The first call to
    ``draw_distinct_from`` returns the initial draw; subsequent calls
    are guaranteed to produce a ``(where, when)`` pair that differs from
    the supplied ``previous`` draw, so a new party never accidentally
    matches the one Chris just decoded.
    """

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def draw_distinct_from(self, previous: PartyDraw | None) -> PartyDraw:
        """Draw a new ``(where, when)``; if non-None, must differ from ``previous``."""
        for _ in range(64):
            candidate = PartyDraw(
                where=self._rng.choice(_VENUE_POOL),
                when=self._rng.choice(_TIME_POOL),
            )
            if previous is None or candidate != previous:
                return candidate
        raise RuntimeError(
            "Could not draw a distinct party after 64 attempts — "
            "venue / time pools are too small or the RNG is exhausted."
        )
