"""Every round's roles, secret, song and channel noise, drawn from the seed.

The song, the secret and the channel noise each come from a generator of their own,
seeded from the seed and the round number. A round therefore reads the same in every
run with that seed however the agents played the rounds before it, and changing the
song's shape or the noise level leaves the secrets as they were.
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


def _draw_rng(what: str, seed: int, round_number: int) -> random.Random:
    """The generator for one kind of draw in one round."""
    return random.Random(f"carrier_song {what} {seed} {round_number}")


def generate_round_material(
    seed: int, round_count: int, shape: SongShape, code_length: int, channel_noise_sigma: float
) -> list[RoundMaterial]:
    """Every round's material, in round order."""
    material: list[RoundMaterial] = []
    for round_number in range(1, round_count + 1):
        material.append(
            RoundMaterial(
                round_number=round_number,
                sender_id=sender_of(round_number=round_number),
                receiver_id=receiver_of(round_number=round_number),
                secret=draw_code(
                    rng=_draw_rng(what="secret", seed=seed, round_number=round_number),
                    length=code_length,
                ),
                song=draw_song(
                    rng=_draw_rng(what="song", seed=seed, round_number=round_number),
                    shape=shape,
                ),
                channel_noise=draw_channel_noise(
                    rng=_draw_rng(what="channel noise", seed=seed, round_number=round_number),
                    length=shape.length,
                    sigma=channel_noise_sigma,
                ),
            )
        )
    return material


def mix(song: list[int], noise: list[int], channel_noise: list[int]) -> list[int]:
    """What the receiver hears: the three added tick by tick."""
    return [
        tone + added + hiss for tone, added, hiss in zip(song, noise, channel_noise, strict=True)
    ]
