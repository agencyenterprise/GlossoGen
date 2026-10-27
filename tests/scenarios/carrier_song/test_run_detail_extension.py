"""The per-round data carrier_song adds to the run-detail API for the round panel."""

from pathlib import Path

import pytest

from glossogen.models.event import SimulationEvent
from glossogen.scenarios.carrier_song.events import (
    CarrierSongExecutorRan,
    CarrierSongRoundResolved,
    CarrierSongRoundStarted,
    CarrierSongTransmitted,
)
from glossogen.scenarios.carrier_song.ids import DECODED_TRIGGER, PLAYER_A, PLAYER_B
from glossogen.scenarios.carrier_song.run_detail_extension import (
    CarrierSongRunDetailExtension,
    build_case_summaries,
)
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.carrier_song.carrier_song_play import (
    BIT_EXECUTOR,
    ONE_ROUND,
    WRONG_CODE,
    bit_noise,
    build,
    call,
    material_of,
    play,
    read,
    submit_decoding,
    wait_for_next_round,
    write_executor,
)

pytestmark = pytest.mark.xdist_group("carrier_song")

SONG = [1, 2, 3, 4]
HISS = [0, 1, 0, -1]


def started(round_number: int, sender: str, receiver: str) -> CarrierSongRoundStarted:
    return CarrierSongRoundStarted(
        round_number=round_number,
        sender_id=sender,
        receiver_id=receiver,
        secret="ABC123",
        song=SONG,
        channel_noise=HISS,
    )


def ran(
    round_number: int, code: str, written: bool, noise: list[int] | None
) -> CarrierSongExecutorRan:
    return CarrierSongExecutorRan(
        round_number=round_number,
        agent_id=PLAYER_A,
        code=code,
        written=written,
        accepted=noise is not None,
        noise=noise,
        clipped_ticks=0,
        error=None,
    )


async def test_a_played_round_carries_its_song_noise_recording_and_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    [material] = material_of(scenario=scenario)
    code = BIT_EXECUTOR.format(secret=material.secret)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            write_executor(code=code),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: [
            read(),
            read(),
            call(tool_name="read_received"),
            submit_decoding(secret=WRONG_CODE),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    extras = CarrierSongRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )

    [summary] = extras.cases
    noise = bit_noise(secret=material.secret, length=len(material.song))
    assert summary.round_number == 1
    assert (summary.sender_id, summary.receiver_id) == (PLAYER_A, PLAYER_B)
    assert summary.secret == material.secret
    assert summary.song == material.song
    assert summary.channel_noise == material.channel_noise
    assert summary.noise == noise
    assert summary.recording == [
        tone + added + hiss
        for tone, added, hiss in zip(material.song, noise, material.channel_noise, strict=True)
    ]
    assert summary.executor_code == code
    assert (summary.decoded, summary.success) == (WRONG_CODE, False)


def test_the_executor_credited_is_the_last_accepted_before_the_transmission() -> None:
    events: list[SimulationEvent] = [
        started(round_number=3, sender=PLAYER_A, receiver=PLAYER_B),
        ran(round_number=3, code="in place", written=False, noise=[1, 1, 1, 1]),
        ran(round_number=3, code="broken", written=True, noise=None),
        ran(round_number=3, code="rewritten", written=True, noise=[2, 2, 2, 2]),
        CarrierSongTransmitted(
            round_number=3, sender_id=PLAYER_A, noise=[2, 2, 2, 2], recording=[3, 5, 5, 5]
        ),
        CarrierSongRoundResolved(
            round_number=3,
            sender_id=PLAYER_A,
            receiver_id=PLAYER_B,
            secret="ABC123",
            decoded="ABC123",
            success=True,
            trigger=DECODED_TRIGGER,
        ),
    ]

    [summary] = build_case_summaries(events=events)

    assert summary.executor_code == "rewritten"
    assert summary.noise == [2, 2, 2, 2]
    assert summary.success is True


def test_a_round_never_transmitted_has_no_noise_recording_or_executor() -> None:
    events: list[SimulationEvent] = [
        started(round_number=1, sender=PLAYER_A, receiver=PLAYER_B),
        ran(round_number=1, code="in place", written=True, noise=[1, 1, 1, 1]),
        CarrierSongRoundResolved(
            round_number=1,
            sender_id=PLAYER_A,
            receiver_id=PLAYER_B,
            secret="ABC123",
            decoded=None,
            success=False,
            trigger="all_agents_waiting",
        ),
        started(round_number=2, sender=PLAYER_B, receiver=PLAYER_A),
    ]

    first, second = build_case_summaries(events=events)

    assert (first.noise, first.recording, first.executor_code) == (None, None, None)
    assert (first.decoded, first.success) == (None, False)
    assert (second.round_number, second.decoded, second.success) == (2, None, None)
