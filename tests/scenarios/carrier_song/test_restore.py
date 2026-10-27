"""Restoring carrier_song's state from a run's events, as a fork or resume does."""

from glossogen.scenarios.carrier_song.events import (
    CarrierSongExecutorRan,
    CarrierSongRoundResolved,
    CarrierSongTransmitted,
)
from glossogen.scenarios.carrier_song.ids import DECODED_TRIGGER, PLAYER_A, PLAYER_B
from tests.scenarios.carrier_song.carrier_song_play import WRONG_CODE, build

PLACED = "def noise(song):\n    return [1] * len(song)\n"
SILENCE = [0] * 64


def test_restore_seeds_verdicts_and_placed_executors_but_not_an_open_round() -> None:
    scenario = build(overrides={"round_count": 3})
    events = [
        CarrierSongExecutorRan(
            round_number=1,
            agent_id=PLAYER_A,
            code=PLACED,
            written=True,
            accepted=True,
            noise=[1] * 64,
            clipped_ticks=0,
            error=None,
        ),
        CarrierSongExecutorRan(
            round_number=1,
            agent_id=PLAYER_A,
            code="def noise(song)\n",
            written=True,
            accepted=False,
            noise=None,
            clipped_ticks=0,
            error="SyntaxError",
        ),
        CarrierSongRoundResolved(
            round_number=1,
            sender_id=PLAYER_A,
            receiver_id=PLAYER_B,
            secret="2G48H8",
            decoded=WRONG_CODE,
            success=False,
            trigger=DECODED_TRIGGER,
        ),
        CarrierSongExecutorRan(
            round_number=2,
            agent_id=PLAYER_B,
            code=PLACED,
            written=False,
            accepted=True,
            noise=[1] * 64,
            clipped_ticks=0,
            error=None,
        ),
        CarrierSongTransmitted(
            round_number=2, sender_id=PLAYER_B, noise=SILENCE, recording=SILENCE
        ),
    ]

    scenario.restore_state_from_events(events=events)

    world = scenario.get_world()
    assert world.executor_of(agent_id=PLAYER_A) == PLACED
    assert world.executor_of(agent_id=PLAYER_B) is None
    outcome = world.outcome(round_number=1)
    assert outcome is not None
    assert outcome.decoded == WRONG_CODE
    assert not world.round_open
    assert not scenario.is_finished_early()


def test_a_restored_win_ends_the_run() -> None:
    scenario = build(overrides={"round_count": 3})
    scenario.restore_state_from_events(
        events=[
            CarrierSongRoundResolved(
                round_number=1,
                sender_id=PLAYER_A,
                receiver_id=PLAYER_B,
                secret="2G48H8",
                decoded="2G48H8",
                success=True,
                trigger=DECODED_TRIGGER,
            )
        ]
    )

    assert scenario.is_finished_early()
