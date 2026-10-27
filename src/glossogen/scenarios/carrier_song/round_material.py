"""Every round's roles, secret, song and channel noise, drawn from the seed.

The song, the secret and the channel noise each come from a generator of their own,
seeded from the seed and the round number. A round therefore reads the same in every
run with that seed however the agents played the rounds before it, and changing the
song's shape or the noise level leaves the secrets as they were.
"""

from typing import NamedTuple

from glossogen.scenarios.carrier_song.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.carrier_song.secret_code import draw_code
from glossogen.scenarios.carrier_song.song import SongShape, draw_channel_noise, draw_rng, draw_song

NAMESPACE = "carrier_song"
"""Names this scenario's draws, so another scenario on the same seed draws other songs."""


class RoundMaterial(NamedTuple):
    """What the world fixes for one round before anyone acts."""

    round_number: int
    sender_id: str
    receiver_id: str
    secret: str
    song: list[int]
    channel_noise: list[int]


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
                    rng=draw_rng(
                        namespace=NAMESPACE, what="secret", seed=seed, round_number=round_number
                    ),
                    length=code_length,
                ),
                song=draw_song(
                    rng=draw_rng(
                        namespace=NAMESPACE, what="song", seed=seed, round_number=round_number
                    ),
                    shape=shape,
                ),
                channel_noise=draw_channel_noise(
                    rng=draw_rng(
                        namespace=NAMESPACE,
                        what="channel noise",
                        seed=seed,
                        round_number=round_number,
                    ),
                    length=shape.length,
                    sigma=channel_noise_sigma,
                ),
            )
        )
    return material
