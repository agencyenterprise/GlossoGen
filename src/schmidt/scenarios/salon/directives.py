"""Directive catalogue and per-round selection for the Salon scenario.

Directives are neutral ``DIR_XX`` labels, not natural-language phrases,
so agents cannot lean on English-language priors when encoding them.
The per-round sequence is drawn uniformly at random from the full
directive set using a seeded RNG, so independent runs with the same
seed reproduce the same sequence.
"""

import random


def build_directive_ids(directive_space_size: int) -> list[str]:
    """Return the full directive catalogue for a given space size.

    Each directive is a neutral ``DIR_01``, ``DIR_02``, ... label so that
    no natural-language semantics leaks from the id itself.
    """
    return [f"DIR_{i:02d}" for i in range(1, directive_space_size + 1)]


def build_directive_sequence(
    seed: int,
    round_count: int,
    directive_space_size: int,
) -> list[str]:
    """Return a seeded per-round directive sequence of length ``round_count``.

    Each round's directive is drawn uniformly at random (with replacement)
    from the full directive catalogue, so repeats are possible and must be
    handled by the agents themselves.
    """
    rng = random.Random(seed)
    directives = build_directive_ids(directive_space_size=directive_space_size)
    return [rng.choice(directives) for _ in range(round_count)]
