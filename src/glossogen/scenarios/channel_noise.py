"""Per-character channel-noise corruption shared by scenarios with a noisy channel.

Defines the noise replacement mode (what a dropped character becomes on the
wire) and the deterministic per-character corruption applied to outgoing
messages. Scenarios own the channel-membership gating and the seeded RNG; this
module owns only the character-level transform so the behavior stays identical
across every scenario that exposes a ``channel_noise_level`` knob.
"""

import random
import string
from enum import Enum

_NOISE_ALPHABET = string.ascii_letters


class NoiseReplacementMode(str, Enum):
    """How a dropped character is rendered on a noisy channel.

    ``MASK`` replaces each dropped character with the underscore marker ``_``,
    so the receiver sees exactly where loss occurred (an erasure channel).
    ``RANDOM_LETTER`` replaces each dropped character with a different random
    ASCII letter, leaving no marker, so the corruption is indistinguishable
    from the original text (a substitution channel).
    """

    MASK = "mask"
    RANDOM_LETTER = "random_letter"


def apply_character_noise(
    *,
    text: str,
    noise_level: float,
    mode: NoiseReplacementMode,
    rng: random.Random,
) -> str:
    """Corrupt ``text`` by replacing each character with probability ``noise_level``.

    Returns ``text`` unchanged when ``noise_level`` is ``0.0``. Sampling draws
    from ``rng`` so the caller controls run reproducibility via its seeded RNG.
    """
    if noise_level == 0.0:
        return text
    return "".join(
        _corrupt_character(ch=ch, noise_level=noise_level, mode=mode, rng=rng) for ch in text
    )


def _corrupt_character(
    *,
    ch: str,
    noise_level: float,
    mode: NoiseReplacementMode,
    rng: random.Random,
) -> str:
    """Return the on-wire character for ``ch``: itself, or a corruption marker."""
    if rng.random() >= noise_level:
        return ch
    if mode == NoiseReplacementMode.RANDOM_LETTER:
        return _random_other_letter(original=ch, rng=rng)
    return "_"


def _random_other_letter(*, original: str, rng: random.Random) -> str:
    """Return a random ASCII letter different from ``original``."""
    alphabet = [c for c in _NOISE_ALPHABET if c != original]
    return rng.choice(alphabet)
