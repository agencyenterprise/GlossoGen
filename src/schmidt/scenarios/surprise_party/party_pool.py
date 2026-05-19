"""Seeded ``(where, when)`` draw for the surprise_party scenario.

Two fixed pools of plausible venues and times. The scenario draws one of
each at construction time using ``knobs.seed`` so the same seed always
yields the same party — Alice receives this fixed info as her round-1
injection and must transmit it across every round.
"""

import random
from typing import NamedTuple


class PartyDraw(NamedTuple):
    """Ground-truth surprise party details."""

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


def draw_party(seed: int) -> PartyDraw:
    """Pick a deterministic ``(where, when)`` pair for this seed."""
    rng = random.Random(seed)
    where = rng.choice(_VENUE_POOL)
    when = rng.choice(_TIME_POOL)
    return PartyDraw(where=where, when=when)
