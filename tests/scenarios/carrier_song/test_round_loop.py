"""The round loop through the real runner, tools and game clock, with scripted players."""

import json
from pathlib import Path

import pytest

from glossogen.models.event import RunStatus, SimulationEnded
from glossogen.runtime.round_end_trigger import RoundEndTrigger
from glossogen.scenarios.carrier_song.events import (
    CarrierSongDecodingSubmitted,
    CarrierSongExecutorRan,
    CarrierSongRoundResolved,
    CarrierSongRoundStarted,
    CarrierSongTransmitted,
)
from glossogen.scenarios.carrier_song.ids import DECODED_TRIGGER, PLAYER_A, PLAYER_B
from glossogen.scenarios.carrier_song.round_material import mix
from glossogen.testing.scenario_runtime import assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
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
    results_for,
    run_python,
    submit_decoding,
    wait_for_next_round,
    write_executor,
)

pytestmark = pytest.mark.xdist_group("carrier_song")

LIST_FILES = "import json, os\nprint(json.dumps(sorted(os.listdir('.'))))\n"


def resolved(result: SimulationResult) -> CarrierSongRoundResolved:
    [outcome] = result.of_type(event_type=CarrierSongRoundResolved)
    return outcome


def receiver_script(decoding: str) -> list[ScriptedTurn]:
    """Brief, wait for the transmission, read it, decode, wait for the next round."""
    return [
        read(),
        read(),
        call(tool_name="read_received"),
        submit_decoding(secret=decoding),
        wait_for_next_round(),
    ]


async def test_a_decoding_equal_to_the_secret_scores_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    [material] = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            call(tool_name="read_song"),
            write_executor(code=BIT_EXECUTOR.format(secret=material.secret)),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: receiver_script(decoding=material.secret),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=1)
    outcome = resolved(result=result)
    assert outcome.success
    assert outcome.trigger == DECODED_TRIGGER
    noise = bit_noise(secret=material.secret, length=len(material.song))
    [transmitted] = result.of_type(event_type=CarrierSongTransmitted)
    assert transmitted.noise == noise
    assert transmitted.recording == mix(
        song=material.song, noise=noise, channel_noise=material.channel_noise
    )
    [received] = results_for(result=result, agent_id=PLAYER_B, tool_name="read_received")
    assert " ".join(str(value) for value in transmitted.recording) in received
    waits = results_for(result=result, agent_id=PLAYER_B, tool_name="read_notifications")
    assert "Your partner has ended its turn." in waits[1]


async def test_a_sender_with_no_executor_plays_silence_and_a_wrong_decoding_loses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    [material] = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), call(tool_name="end_round"), wait_for_next_round()],
        PLAYER_B: receiver_script(decoding=WRONG_CODE),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [transmitted] = result.of_type(event_type=CarrierSongTransmitted)
    assert transmitted.noise == [0] * len(material.song)
    outcome = resolved(result=result)
    assert not outcome.success
    assert outcome.decoded == WRONG_CODE


async def test_nothing_can_be_read_or_decoded_before_the_transmission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), wait_for_next_round()],
        PLAYER_B: [
            read(),
            call(tool_name="read_received"),
            submit_decoding(secret=WRONG_CODE),
            run_python(code=LIST_FILES),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [received] = results_for(result=result, agent_id=PLAYER_B, tool_name="read_received")
    [decoding] = results_for(result=result, agent_id=PLAYER_B, tool_name="submit_decoding")
    [listing] = results_for(result=result, agent_id=PLAYER_B, tool_name="run_python")
    assert "Nothing has been transmitted yet" in received
    assert "Nothing has been transmitted yet" in decoding
    assert json.loads(listing) == []
    outcome = resolved(result=result)
    assert not outcome.success
    assert outcome.decoded is None


async def test_each_role_refuses_the_other_roles_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            call(tool_name="read_received"),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), call(tool_name="read_song"), *receiver_script(decoding=WRONG_CODE)[1:]],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [sender_refusal] = results_for(result=result, agent_id=PLAYER_A, tool_name="read_received")
    [receiver_refusal] = results_for(result=result, agent_id=PLAYER_B, tool_name="read_song")
    assert "only the receiver can call read_received" in sender_refusal
    assert "only the sender can call read_song" in receiver_refusal


async def test_run_python_sees_only_what_each_role_may_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            run_python(code=LIST_FILES),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: [
            read(),
            read(),
            run_python(code=LIST_FILES),
            submit_decoding(secret=WRONG_CODE),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [sender_files] = results_for(result=result, agent_id=PLAYER_A, tool_name="run_python")
    [receiver_files] = results_for(result=result, agent_id=PLAYER_B, tool_name="run_python")
    assert json.loads(sender_files) == ["song.json"]
    assert json.loads(receiver_files) == ["received.json"]


async def test_a_receiver_that_may_see_the_song_reads_it_with_the_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides={**ONE_ROUND, "receiver_sees_song": True})
    [material] = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), call(tool_name="end_round"), wait_for_next_round()],
        PLAYER_B: receiver_script(decoding=WRONG_CODE),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [received] = results_for(result=result, agent_id=PLAYER_B, tool_name="read_received")
    assert "Round 1 recording" in received
    assert "Round 1 song" in received
    assert " ".join(str(value) for value in material.song) in received


async def test_a_failing_executor_leaves_the_one_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    [material] = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            write_executor(code=BIT_EXECUTOR.format(secret=material.secret)),
            write_executor(code="def noise(song)\n"),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: receiver_script(decoding=material.secret),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    _, failed = results_for(result=result, agent_id=PLAYER_A, tool_name="write_executor")
    assert "Your executor failed" in failed
    assert "SyntaxError" in failed
    assert "The executor you had in place stays." in failed
    [transmitted] = result.of_type(event_type=CarrierSongTransmitted)
    assert transmitted.noise == bit_noise(secret=material.secret, length=len(material.song))
    assert resolved(result=result).success


async def test_noise_past_the_volume_is_clipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    [material] = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            write_executor(code="def noise(song):\n    return [9] * len(song)\n"),
            call(tool_name="read_output"),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: receiver_script(decoding=WRONG_CODE),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [written] = results_for(result=result, agent_id=PLAYER_A, tool_name="write_executor")
    assert f"{len(material.song)} tick(s) limited to ±2" in written
    [output] = results_for(result=result, agent_id=PLAYER_A, tool_name="read_output")
    assert " ".join(str(value + 2) for value in material.song) in output
    [transmitted] = result.of_type(event_type=CarrierSongTransmitted)
    assert transmitted.noise == [2] * len(material.song)


async def test_the_roles_swap_and_an_executor_plays_again_on_its_authors_next_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides={"round_count": 3})
    first, _, third = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            write_executor(code=BIT_EXECUTOR.format(secret=first.secret)),
            call(tool_name="end_round"),
            wait_for_next_round(),
            *receiver_script(decoding=WRONG_CODE)[1:],
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: [
            *receiver_script(decoding=WRONG_CODE),
            call(tool_name="end_round"),
            wait_for_next_round(),
            *receiver_script(decoding=third.secret)[1:],
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=3)
    started = result.of_type(event_type=CarrierSongRoundStarted)
    assert [event.sender_id for event in started] == [PLAYER_A, PLAYER_B, PLAYER_A]
    reused = [
        event
        for event in result.of_type(event_type=CarrierSongExecutorRan)
        if event.round_number == 3
    ]
    assert [(event.agent_id, event.written, event.accepted) for event in reused] == [
        (PLAYER_A, False, True)
    ]
    transmitted = result.of_type(event_type=CarrierSongTransmitted)
    assert transmitted[2].noise == bit_noise(secret=first.secret, length=len(third.song))
    outcomes = result.of_type(event_type=CarrierSongRoundResolved)
    assert [outcome.success for outcome in outcomes] == [False, False, True]


async def test_the_first_correct_decoding_ends_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides={"round_count": 3})
    first = material_of(scenario=scenario)[0]
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), call(tool_name="end_round"), wait_for_next_round()],
        PLAYER_B: receiver_script(decoding=first.secret),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=1)
    assert [event.round_number for event in result.of_type(event_type=CarrierSongRoundStarted)] == [
        1
    ]
    [ended] = result.of_type(event_type=SimulationEnded)
    assert ended.reason == RunStatus.SCENARIO_COMPLETE
    assert resolved(result=result).success


async def test_the_next_briefing_says_only_that_the_decoding_was_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides={"round_count": 2})
    first, _ = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            call(tool_name="end_round"),
            wait_for_next_round(),
            read(),
            submit_decoding(secret=WRONG_CODE),
            wait_for_next_round(),
        ],
        PLAYER_B: [
            *receiver_script(decoding=WRONG_CODE),
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    waits = results_for(result=result, agent_id=PLAYER_B, tool_name="read_notifications")
    second_briefing = next(text for text in waits if "ROUND 2" in text)
    assert "Round 1: the decoding was wrong." in second_briefing
    assert first.secret not in second_briefing
    assert WRONG_CODE not in second_briefing
    assert "You are the SENDER this round" in second_briefing


async def test_a_decoding_is_read_in_capitals_and_a_malformed_one_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    [material] = material_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), call(tool_name="end_round"), wait_for_next_round()],
        PLAYER_B: [
            read(),
            read(),
            submit_decoding(secret="ABC"),
            submit_decoding(secret="AB-CD!"),
            submit_decoding(secret=f" {material.secret.lower()} "),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    short, stray, accepted = results_for(
        result=result, agent_id=PLAYER_B, tool_name="submit_decoding"
    )
    assert "A code has 6 characters; 'ABC' has 3." in short
    assert "also has '!-'" in stray
    assert "Your decoding is recorded." in accepted
    [submitted] = result.of_type(event_type=CarrierSongDecodingSubmitted)
    assert submitted.decoded == material.secret
    assert resolved(result=result).success


async def test_a_waiting_sender_is_released_twice_then_both_parked_ends_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), read(), read(), read()],
        PLAYER_B: [read(), read()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    waits = results_for(result=result, agent_id=PLAYER_A, tool_name="read_notifications")
    notice = "Nothing will arrive while you wait"
    assert [notice in text for text in waits[1:]] == [True, True] + [False] * (len(waits) - 3)
    outcome = resolved(result=result)
    assert outcome.trigger == RoundEndTrigger.ALL_AGENTS_WAITING.value
    assert outcome.decoded is None
    assert not outcome.success


async def test_an_executor_in_place_that_fails_on_a_new_song_is_reported_in_the_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides={"round_count": 3})
    first, _, third = material_of(scenario=scenario)
    only_first_song = (
        f"FIRST = {first.song!r}\n\n"
        "def noise(song):\n"
        "    if song != FIRST:\n"
        "        raise ValueError('not the first song')\n"
        "    return [2] * len(song)\n"
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            write_executor(code=only_first_song),
            call(tool_name="end_round"),
            wait_for_next_round(),
            *receiver_script(decoding=WRONG_CODE)[1:],
            call(tool_name="end_round"),
            wait_for_next_round(),
        ],
        PLAYER_B: [
            *receiver_script(decoding=WRONG_CODE),
            call(tool_name="end_round"),
            wait_for_next_round(),
            *receiver_script(decoding=WRONG_CODE)[1:],
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [failed] = [
        event
        for event in result.of_type(event_type=CarrierSongExecutorRan)
        if event.round_number == 3
    ]
    assert (failed.agent_id, failed.written, failed.accepted) == (PLAYER_A, False, False)
    assert failed.error is not None
    assert "not the first song" in failed.error
    waits = results_for(result=result, agent_id=PLAYER_A, tool_name="read_notifications")
    third_briefing = next(text for text in waits if "ROUND 3" in text)
    assert "failed on this round's song" in third_briefing
    assert "not the first song" in third_briefing
    transmitted = result.of_type(event_type=CarrierSongTransmitted)
    assert transmitted[0].noise == [2] * len(first.song)
    assert transmitted[2].noise == [0] * len(third.song)
    [ended_turn] = results_for(result=result, agent_id=PLAYER_A, tool_name="end_round")[1:]
    assert "failed" not in ended_turn


async def test_run_python_gives_a_receiver_that_may_see_the_song_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(overrides={**ONE_ROUND, "receiver_sees_song": True})
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), call(tool_name="end_round"), wait_for_next_round()],
        PLAYER_B: [
            read(),
            read(),
            run_python(code=LIST_FILES),
            submit_decoding(secret=WRONG_CODE),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [receiver_files] = results_for(result=result, agent_id=PLAYER_B, tool_name="run_python")
    assert json.loads(receiver_files) == ["received.json", "song.json"]
