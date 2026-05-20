"""Deterministic per-round target sampling for the codebreakers scenario.

Defines the fixed 30-item pool of everyday objects Alice signals each
round and provides a seeded sampler that returns the same target for the
same ``(seed, round_number)`` pair across runs and resumes.

A normalization helper validates a freetext guess against the pool with
case-insensitive matching.
"""

import random

REFERENT_POOL: tuple[str, ...] = (
    "apple",
    "banana",
    "bicycle",
    "book",
    "butter",
    "cat",
    "chair",
    "cloud",
    "coffee",
    "computer",
    "dog",
    "door",
    "elephant",
    "fish",
    "flower",
    "guitar",
    "hammer",
    "hat",
    "hill",
    "key",
    "lamp",
    "lion",
    "map",
    "mirror",
    "moon",
    "mountain",
    "ocean",
    "pencil",
    "piano",
    "rainbow",
)


_NORMALIZED_LOOKUP: dict[str, str] = {item.lower(): item for item in REFERENT_POOL}


class RoundTargetSampler:
    """Deterministic per-round target draw from ``REFERENT_POOL``.

    Each ``target_for_round(R)`` call returns a uniformly sampled item.
    Results are cached so a second call for the same round returns the
    same target, which keeps fork/resume reproducible without having to
    re-execute the RNG up to round R.
    """

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._cache: dict[int, str] = {}

    def target_for_round(self, round_number: int) -> str:
        """Return the deterministic target for ``round_number``."""
        if round_number in self._cache:
            return self._cache[round_number]
        per_round_rng = random.Random(hash((self._seed, round_number)))
        target = per_round_rng.choice(REFERENT_POOL)
        self._cache[round_number] = target
        return target

    def cache_target(self, round_number: int, target: str) -> None:
        """Force-cache a target (used by ``restore_state_from_events``)."""
        self._cache[round_number] = target


def normalize_guess(raw: str) -> str | None:
    """Return the canonical pool entry for ``raw`` (case-insensitive) or ``None``.

    Trims surrounding whitespace, lowercases, and looks up the exact pool
    entry. Returns ``None`` if the input does not name a pool item.
    """
    return _NORMALIZED_LOOKUP.get(raw.strip().lower())
