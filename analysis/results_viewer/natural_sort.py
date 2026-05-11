"""Natural-sort key for mixed alpha/numeric strings (so ``q2`` sorts before ``q10``)."""

import re


def natural_sort_key(text: str) -> list[object]:
    """Sort key that orders mixed alpha/numeric strings in human-natural order.

    Splits ``text`` into runs of digits and non-digits, casting digit
    runs to ``int`` so e.g. ``q2`` sorts before ``q10`` and ``budget=2``
    sorts before ``budget=10``.
    """
    parts: list[object] = []
    for chunk in re.split(r"(\d+)", text):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(chunk)
    return parts
