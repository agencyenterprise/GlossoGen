"""Each round's roles, secret, song and channel noise, as drawn from the seed."""

from glossogen.scenarios.carrier_song.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.carrier_song.round_material import generate_round_material
from glossogen.scenarios.carrier_song.secret_code import CODE_ALPHABET
from glossogen.scenarios.carrier_song.song import SongShape, mix

SHAPE = SongShape(length=24, motif_length=6, amplitude=5)


def test_the_same_seed_draws_the_same_rounds() -> None:
    first = generate_round_material(
        seed=42, round_count=4, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )
    second = generate_round_material(
        seed=42, round_count=4, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )
    other = generate_round_material(
        seed=7, round_count=4, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )

    assert first == second
    assert first != other


def test_a_round_reads_the_same_whatever_the_round_count() -> None:
    short = generate_round_material(
        seed=42, round_count=2, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )
    long = generate_round_material(
        seed=42, round_count=5, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )

    assert long[:2] == short


def test_the_song_loops_its_motif_within_the_amplitude() -> None:
    [material] = generate_round_material(
        seed=42, round_count=1, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )

    assert len(material.song) == SHAPE.length
    assert all(-SHAPE.amplitude <= value <= SHAPE.amplitude for value in material.song)
    motif = material.song[: SHAPE.motif_length]
    assert material.song == motif * (SHAPE.length // SHAPE.motif_length)


def test_the_roles_swap_every_round() -> None:
    rounds = generate_round_material(
        seed=42, round_count=4, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )

    assert [(r.sender_id, r.receiver_id) for r in rounds] == [
        (PLAYER_A, PLAYER_B),
        (PLAYER_B, PLAYER_A),
        (PLAYER_A, PLAYER_B),
        (PLAYER_B, PLAYER_A),
    ]


def test_secrets_are_codes_of_the_configured_length() -> None:
    rounds = generate_round_material(
        seed=42, round_count=50, shape=SHAPE, code_length=4, channel_noise_sigma=1.0
    )

    assert all(len(material.secret) == 4 for material in rounds)
    assert set("".join(material.secret for material in rounds)) <= set(CODE_ALPHABET)
    assert len({material.secret for material in rounds}) == len(rounds)


def test_no_channel_noise_at_sigma_zero() -> None:
    [material] = generate_round_material(
        seed=42, round_count=1, shape=SHAPE, code_length=6, channel_noise_sigma=0.0
    )

    assert material.channel_noise == [0] * SHAPE.length


def test_the_song_shape_and_noise_level_leave_the_secrets_alone() -> None:
    base = generate_round_material(
        seed=42, round_count=4, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )
    reshaped = generate_round_material(
        seed=42,
        round_count=4,
        shape=SongShape(length=32, motif_length=4, amplitude=3),
        code_length=6,
        channel_noise_sigma=2.5,
    )

    assert [r.secret for r in reshaped] == [r.secret for r in base]


def test_the_code_length_leaves_the_songs_and_channel_noise_alone() -> None:
    six = generate_round_material(
        seed=42, round_count=4, shape=SHAPE, code_length=6, channel_noise_sigma=1.0
    )
    four = generate_round_material(
        seed=42, round_count=4, shape=SHAPE, code_length=4, channel_noise_sigma=1.0
    )

    assert [(r.song, r.channel_noise) for r in four] == [(r.song, r.channel_noise) for r in six]


def test_mix_adds_tick_by_tick() -> None:
    assert mix(song=[1, 2, 3], noise=[0, -2, 2], channel_noise=[1, 0, -1]) == [2, 0, 4]
