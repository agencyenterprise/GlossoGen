"""Shannon entropy of a message's character distribution.

A model-free, deterministic measure of within-message symbol diversity: the
Shannon entropy of the character frequencies, in bits per character. Pure
repetition collapses toward 0 (a single repeated character is 0 bits); diverse
text approaches the log2 of the alphabet size. Shared by the ``message_entropy``
metric and the veyru spreadsheet exporters.
"""

import math
from collections import Counter


def character_entropy_bits(text: str) -> float:
    """Return the Shannon entropy of ``text``'s character distribution in bits/char.

    Computes ``-Σ p(c)·log2 p(c)`` over the character frequencies. Returns ``nan``
    for empty text (no characters to score), so callers can drop it like the other
    per-message scores rather than serialize a misleading 0.
    """
    if not text:
        return math.nan
    counts = Counter(text)
    total = len(text)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())
