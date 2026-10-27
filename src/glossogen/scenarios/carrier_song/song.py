"""The radio channel's material: a looped song, Gaussian channel noise, and the mix.

One song and one channel-noise sequence are drawn per round. Each draw gets a
generator of its own, seeded from the scenario's name, the kind of draw, the run's
seed and the round number, so a round reads the same in every run with that seed
however the rounds before it went, and changing one draw leaves the others alone.
"""

import random
from typing import NamedTuple


class SongShape(NamedTuple):
    """How a round's song is drawn: a motif of ``motif_length`` values within
    ``±amplitude``, looped to ``length`` ticks."""

    length: int
    motif_length: int
    amplitude: int


def draw_rng(namespace: str, what: str, seed: int, round_number: int) -> random.Random:
    """The generator for one kind of draw in one round of one scenario."""
    return random.Random(f"{namespace} {what} {seed} {round_number}")


def draw_song(rng: random.Random, shape: SongShape) -> list[int]:
    """A motif drawn from ``rng``, looped to the song's length."""
    motif = [rng.randint(-shape.amplitude, shape.amplitude) for _ in range(shape.motif_length)]
    return [motif[tick % shape.motif_length] for tick in range(shape.length)]


def draw_channel_noise(rng: random.Random, length: int, sigma: float) -> list[int]:
    """Gaussian noise of ``sigma``, rounded to whole numbers; all zeros when ``sigma`` is 0."""
    return [round(rng.gauss(mu=0.0, sigma=sigma)) for _ in range(length)]


def mix(song: list[int], noise: list[int], channel_noise: list[int]) -> list[int]:
    """What the channel carries: the song, the sender's noise and the hiss, tick by tick."""
    return [
        tone + added + hiss for tone, added, hiss in zip(song, noise, channel_noise, strict=True)
    ]
