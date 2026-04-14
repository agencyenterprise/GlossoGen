"""Word lists for the telephone scenario.

Defines 10 base word lists of increasing length (3–17 items) and generates
40 rounds by repeating them across 4 shuffled epochs. Repetition forces
agents to develop compressed encoding patterns for recurring vocabulary.
Epoch 1 introduces lists in order; epochs 2–4 shuffle them so agents
encounter familiar word sets in unpredictable sequence.
"""

from typing import NamedTuple


class WordList(NamedTuple):
    """A word list assigned to a single round of the telephone game."""

    round_number: int
    items: list[str]


class _BaseList(NamedTuple):
    """Template for a word list, before round_number assignment."""

    items: list[str]


_BASE_LISTS: list[_BaseList] = [
    # 0: 3 items
    _BaseList(items=["apple", "chair", "river"]),
    # 1: 4 items
    _BaseList(items=["hammer", "cloud", "penguin", "blanket"]),
    # 2: 5 items
    _BaseList(items=["guitar", "volcano", "sandwich", "telescope", "candle"]),
    # 3: 5 items
    _BaseList(items=["elephant", "microscope", "cinnamon", "lighthouse", "parachute"]),
    # 4: 6 items (recycled)
    _BaseList(items=["penguin", "lighthouse", "volcano", "candle", "guitar", "elephant"]),
    # 5: 7 items (recycled)
    _BaseList(
        items=["blanket", "telescope", "river", "hammer", "parachute", "microscope", "cinnamon"],
    ),
    # 6: 7 items (recycled)
    _BaseList(items=["chair", "sandwich", "cloud", "apple", "penguin", "lighthouse", "volcano"]),
    # 7: 8 items (recycled)
    _BaseList(
        items=[
            "telescope",
            "elephant",
            "cinnamon",
            "guitar",
            "blanket",
            "hammer",
            "river",
            "candle",
        ],
    ),
    # 8: 9 items (recycled)
    _BaseList(
        items=[
            "parachute",
            "microscope",
            "sandwich",
            "cloud",
            "apple",
            "chair",
            "penguin",
            "lighthouse",
            "volcano",
        ],
    ),
    # 9: 17 items (all vocabulary)
    _BaseList(
        items=[
            "apple",
            "blanket",
            "candle",
            "chair",
            "cinnamon",
            "cloud",
            "elephant",
            "guitar",
            "hammer",
            "lighthouse",
            "microscope",
            "parachute",
            "penguin",
            "river",
            "sandwich",
            "telescope",
            "volcano",
        ],
    ),
]

# Four epochs, each a permutation of the 10 base lists.
# Epoch 1 introduces lists in designed order (short first, then longer).
# Epochs 2-4 shuffle so agents encounter familiar lists unpredictably.
_EPOCH_ORDERS: list[list[int]] = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [3, 7, 0, 5, 9, 1, 8, 4, 2, 6],
    [6, 2, 8, 0, 4, 9, 3, 1, 7, 5],
    [9, 5, 4, 8, 1, 6, 0, 3, 2, 7],
]

WORD_LISTS: list[WordList] = []
for _epoch_idx, _epoch in enumerate(_EPOCH_ORDERS):
    for _pos, _base_idx in enumerate(_epoch):
        _base = _BASE_LISTS[_base_idx]
        WORD_LISTS.append(
            WordList(
                round_number=_epoch_idx * 10 + _pos + 1,
                items=list(_base.items),
            )
        )
