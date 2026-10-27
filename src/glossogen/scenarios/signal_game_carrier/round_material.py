"""Every round's grids, song and channel noise, drawn from the seed.

The grids, the song and the channel noise each come from a generator of their own,
seeded from the seed and the round number, so a round reads the same in every run with
that seed however the rounds before it went.
"""

from typing import NamedTuple

from glossogen.scenarios.signal_game_carrier.boards import draw_grids
from glossogen.scenarios.signal_game_carrier.song import (
    SongShape,
    draw_channel_noise,
    draw_rng,
    draw_song,
)

NAMESPACE = "signal_game_carrier"
"""Names this scenario's draws, so another scenario on the same seed draws other songs."""


class RoundMaterial(NamedTuple):
    """What the world fixes for one round before anyone acts."""

    round_number: int
    grids: dict[str, list[list[str]]]
    song: list[int]
    channel_noise: list[int]


def generate_round_material(
    seed: int,
    round_count: int,
    shape: SongShape,
    channel_noise_sigma: float,
    grid_size: int,
    colour_count: int,
) -> list[RoundMaterial]:
    """Every round's material, in round order."""
    material: list[RoundMaterial] = []
    for round_number in range(1, round_count + 1):
        material.append(
            RoundMaterial(
                round_number=round_number,
                grids=draw_grids(
                    rng=draw_rng(
                        namespace=NAMESPACE, what="grids", seed=seed, round_number=round_number
                    ),
                    grid_size=grid_size,
                    colour_count=colour_count,
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
