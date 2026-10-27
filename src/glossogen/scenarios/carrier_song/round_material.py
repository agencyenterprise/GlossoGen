"""Every round's roles, secret, song and channel noise, drawn from the seed.

The draws depend on the seed and the round number only, so a round reads the same
in every run with that seed however the agents played the rounds before it.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.carrier_song.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.carrier_song.secret_code import draw_code


class RoundMaterial(NamedTuple):
    """What the world fixes for one round before anyone acts."""

    round_number: int
    sender_id: str
    receiver_id: str
    secret: str
    song: list[int]
    channel_noise: list[int]


class SongShape(NamedTuple):
    """How a round's song is drawn: a motif of ``motif_length`` values within
    ``±amplitude``, looped to ``length`` ticks."""

    length: int
    motif_length: int
    amplitude: int


def sender_of(round_number: int) -> str:
    """player_a sends in odd rounds, player_b in even ones."""
    if round_number % 2 == 1:
        return PLAYER_A
    return PLAYER_B


def receiver_of(round_number: int) -> str:
    """The player that does not send in ``round_number``."""
    if sender_of(round_number=round_number) == PLAYER_A:
        return PLAYER_B
    return PLAYER_A


def draw_song(rng: random.Random, shape: SongShape) -> list[int]:
    """A motif drawn from ``rng``, looped to the song's length."""
    motif = [rng.randint(-shape.amplitude, shape.amplitude) for _ in range(shape.motif_length)]
    return [motif[tick % shape.motif_length] for tick in range(shape.length)]


def draw_channel_noise(rng: random.Random, length: int, sigma: float) -> list[int]:
    """Gaussian noise of ``sigma``, rounded to whole numbers; all zeros when ``sigma`` is 0."""
    return [round(rng.gauss(mu=0.0, sigma=sigma)) for _ in range(length)]


def generate_round_material(
    seed: int, round_count: int, shape: SongShape, code_length: int, channel_noise_sigma: float
) -> list[RoundMaterial]:
    """Every round's material, in round order."""
    material: list[RoundMaterial] = []
    for round_number in range(1, round_count + 1):
        rng = random.Random(f"carrier_song round {seed} {round_number}")
        song = draw_song(rng=rng, shape=shape)
        material.append(
            RoundMaterial(
                round_number=round_number,
                sender_id=sender_of(round_number=round_number),
                receiver_id=receiver_of(round_number=round_number),
                secret=draw_code(rng=rng, length=code_length),
                song=song,
                channel_noise=draw_channel_noise(
                    rng=rng, length=shape.length, sigma=channel_noise_sigma
                ),
            )
        )
    return material


def mix(song: list[int], noise: list[int], channel_noise: list[int]) -> list[int]:
    """What the receiver hears: the three added tick by tick."""
    return [
        tone + added + hiss for tone, added, hiss in zip(song, noise, channel_noise, strict=True)
    ]
