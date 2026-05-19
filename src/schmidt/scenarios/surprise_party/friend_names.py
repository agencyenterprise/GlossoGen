"""Deterministic friend name pool for the rotating Friend slot.

Each round of a surprise_party simulation pulls one name from the seeded
shuffle of ``FRIEND_NAME_POOL`` so the chat history shows a different
visitor in the Friend seat each round. The pool excludes ``Alice`` and
``Chris`` so the persistent agents' display names never collide with a
fresh friend's name.
"""

import random

FRIEND_NAME_POOL: tuple[str, ...] = (
    "Mary",
    "Bob",
    "Carol",
    "Dave",
    "Eve",
    "Frank",
    "Grace",
    "Henry",
    "Iris",
    "Jack",
    "Kate",
    "Liam",
    "Mia",
    "Noah",
    "Olive",
    "Peter",
    "Quinn",
    "Ruby",
    "Sam",
    "Tara",
    "Uma",
    "Victor",
    "Wendy",
    "Xavier",
    "Yara",
    "Zane",
    "Amber",
    "Blake",
    "Clara",
    "Diego",
)


def build_friend_name_order(seed: int) -> tuple[str, ...]:
    """Return a deterministic shuffle of ``FRIEND_NAME_POOL`` for this seed.

    Caller indexes ``order[round_number - 1]`` to get the friend name for a
    given round.
    """
    rng = random.Random(seed)
    names = list(FRIEND_NAME_POOL)
    rng.shuffle(names)
    return tuple(names)
