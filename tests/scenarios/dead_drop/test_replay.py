"""Rebuilding the server from a run's log, as a fork or resume does."""

from typing import Any

import pytest
from pydantic_ai import ModelRetry

from glossogen.models.event import InjectionDelivered, SimulationStarted
from glossogen.scenarios.dead_drop.events import DeadDropCaseStarted, DeadDropFsRead
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER
from tests.scenarios.dead_drop.dead_drop_wiring import (
    RecordingLogger,
    Wired,
    bind,
    build,
    codebook_keys,
    local_token_counter,
    wire,
)

pytestmark = pytest.mark.xdist_group("dead_drop")


async def resume(
    monkeypatch: pytest.MonkeyPatch,
    preset_name: str,
    overrides: dict[str, Any],
    events: list[Any],
    round_number: int,
) -> Wired:
    """A fresh scenario restored from ``events`` and entering ``round_number``."""
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter", local_token_counter
    )
    scenario = build(preset_name=preset_name, overrides=overrides)
    logger = RecordingLogger()
    runtime = bind(scenario=scenario, logger=logger)
    scenario.restore_state_from_events(events=list(events))
    runtime.set_current_round(round_number=round_number)
    await scenario.on_round_advanced(round_number=round_number)
    return Wired(scenario=scenario, logger=logger, runtime=runtime)


async def resume_and_read(
    monkeypatch: pytest.MonkeyPatch,
    preset_name: str,
    overrides: dict[str, Any],
    events: list[Any],
    round_number: int,
) -> Wired:
    """``resume`` into a new round, whose briefing both agents then read."""
    resumed = await resume(
        monkeypatch=monkeypatch,
        preset_name=preset_name,
        overrides=overrides,
        events=events,
        round_number=round_number,
    )
    resumed.read_briefings()
    return resumed


async def play_round_one(monkeypatch: pytest.MonkeyPatch, preset_name: str) -> Wired:
    wired = await wire(monkeypatch=monkeypatch, preset_name=preset_name, overrides={})
    await wired.run(agent_id="ana", command="mkdir /tmp/box && echo hello > /tmp/box/note")
    await wired.run(agent_id="ben", command="echo reply >> /tmp/box/note; mv /tmp/box /tmp/kept")
    await wired.run(agent_id="ben", command="echo private > ~/mine")
    await wired.submit(
        agent_id="ana", answers=wired.case(round_number=1).expected_answers(agent_id="ana")
    )
    await wired.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    return wired


async def test_a_fork_into_round_two_sees_round_ones_files_and_authors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = await play_round_one(monkeypatch=monkeypatch, preset_name="knobs_default")
    forked = await resume_and_read(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides={},
        events=source.logger.events,
        round_number=2,
    )
    assert await forked.run(agent_id="ana", command="cat /tmp/kept/note") == "hello\nreply\n"
    assert await forked.run(agent_id="ben", command="cat ~/mine") == "private\n"
    assert forked.of_type(event_type=DeadDropFsRead)[0].authors == ["ana", "ben"]
    cases = await forked.run(agent_id="ana", command="ls ~/cases")
    assert cases == "round_01.txt\nround_02.txt\n"
    assert [event.round_number for event in forked.of_type(event_type=DeadDropCaseStarted)] == [2]
    briefing = forked.scenario.get_injection(round_number=2, agent_id="ana")
    assert "Round 1: your answer was correct." in briefing


def delivered_briefings(round_number: int) -> list[InjectionDelivered]:
    return [
        InjectionDelivered(round_number=round_number, agent_id=agent_id, text="briefing")
        for agent_id in ("ana", "ben")
    ]


async def test_resuming_inside_a_round_keeps_its_answers_and_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_fresh_fs", overrides={})
    await wired.run(agent_id="ana", command="echo note > /tmp/note")
    await wired.submit(
        agent_id="ana", answers=wired.case(round_number=1).expected_answers(agent_id="ana")
    )
    resumed = await resume(
        monkeypatch=monkeypatch,
        preset_name="knobs_fresh_fs",
        overrides={},
        events=[*wired.logger.events, *delivered_briefings(round_number=1)],
        round_number=1,
    )
    # The briefing was delivered before the resume, and is not delivered again.
    assert await resumed.run(agent_id="ben", command="cat /tmp/note") == "note\n"
    assert resumed.scenario.get_world().has_submitted(round_number=1, agent_id="ana")
    assert resumed.of_type(event_type=DeadDropCaseStarted) == []


async def test_a_run_that_rebuilds_each_round_replays_only_the_last_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = await play_round_one(monkeypatch=monkeypatch, preset_name="knobs_fresh_fs")
    forked = await resume_and_read(
        monkeypatch=monkeypatch,
        preset_name="knobs_fresh_fs",
        overrides={},
        events=source.logger.events,
        round_number=2,
    )
    assert (await forked.run(agent_id="ana", command="ls /tmp")).strip() == ""
    assert await forked.run(agent_id="ana", command="ls ~/cases") == "round_02.txt\n"


async def test_resuming_inside_a_round_keeps_the_commands_already_spent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = {"commands_per_round": 2}
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides=limit)
    await wired.run(agent_id="ana", command="pwd")
    resumed = await resume(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides=limit,
        events=[*wired.logger.events, *delivered_briefings(round_number=1)],
        round_number=1,
    )
    await resumed.run(agent_id="ana", command="pwd")
    with pytest.raises(ModelRetry, match="No more commands are accepted"):
        await resumed.run(agent_id="ana", command="pwd")
    assert await resumed.run(agent_id="ben", command="pwd") == "/home/ben\n"


async def test_a_fork_with_another_seed_keeps_the_cases_its_log_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed 9 draws a key of seed 42's first round later on; the fork draws past it."""
    source = await play_round_one(monkeypatch=monkeypatch, preset_name="knobs_default")
    played = source.case(round_number=1)
    forked = await resume_and_read(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides={"seed": 9},
        events=source.logger.events,
        round_number=2,
    )
    assert forked.case(round_number=1) == played
    case_file = await forked.run(agent_id="ana", command="cat ~/cases/round_01.txt")
    for key, value in played.by_agent["ana"].codebook.items():
        assert f"{key} = {value}" in case_file
    assert forked.case(round_number=2) != source.case(round_number=2)
    round_count = forked.scenario.get_knobs().round_count
    later = [forked.case(round_number=number) for number in range(2, round_count + 1)]
    assert not codebook_keys(cases=[played]) & codebook_keys(cases=later)


async def test_a_briefing_run_replays_with_no_case_files(monkeypatch: pytest.MonkeyPatch) -> None:
    briefing = {"case_delivery": "briefing"}
    source = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides=briefing)
    await source.run(agent_id="ana", command="echo hello > /tmp/note")
    await source.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    resumed = await resume_and_read(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides=briefing,
        events=source.logger.events,
        round_number=2,
    )
    assert await resumed.run(agent_id="ana", command="ls ~; cat /tmp/note") == "\nhello\n"
    assert "K-" in resumed.scenario.get_injection(round_number=2, agent_id="ana")


def started_with(knobs: dict[str, Any]) -> SimulationStarted:
    """The ``simulation_started`` event a run with these knobs logs first."""
    return SimulationStarted(
        round_number=0,
        run_id="dead_drop/1",
        scenario_name="dead_drop",
        scenario_description="",
        channel_ids=[],
        scenario_config=knobs,
        provider="self-hosted",
    )


async def play_round_one_with(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any]) -> Wired:
    """Round one under ``overrides``: ana writes a file, ben appends to it, and it ends."""
    source = await wire(monkeypatch=monkeypatch, preset_name="knobs_default", overrides=overrides)
    await source.run(agent_id="ana", command="echo a > /tmp/x")
    await source.run(agent_id="ben", command="echo b >> /tmp/x")
    await source.scenario.on_round_ended(round_number=1, trigger=BOTH_SUBMITTED_TRIGGER)
    return source


@pytest.mark.parametrize(
    ("knob", "recorded", "resumed"),
    [
        ("case_delivery", "file", "briefing"),
        ("case_delivery", "briefing", "file"),
        ("fs_isolated", False, True),
        ("fs_isolated", True, False),
        ("fs_persists_across_rounds", True, False),
        ("fs_persists_across_rounds", False, True),
    ],
)
async def test_a_log_recorded_with_another_layout_is_refused(
    monkeypatch: pytest.MonkeyPatch, knob: str, recorded: Any, resumed: Any
) -> None:
    """Replay rebuilds the logged rounds with this run's knobs, so they must be the logged ones.

    Otherwise a fork that empties the server each round cannot replay a move of an
    earlier round's file, and one that isolates ``/tmp`` splits a shared file in two.
    """
    source = await play_round_one_with(monkeypatch=monkeypatch, overrides={knob: recorded})
    started = started_with(knobs=source.scenario.get_knobs().model_dump(mode="json"))
    with pytest.raises(ValueError, match=f"{knob} is {resumed}, but the log was recorded"):
        await resume(
            monkeypatch=monkeypatch,
            preset_name="knobs_default",
            overrides={knob: resumed},
            events=[started, *source.logger.events],
            round_number=2,
        )


async def test_a_fork_that_changes_another_knob_replays_the_logged_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = await play_round_one_with(monkeypatch=monkeypatch, overrides={})
    started = started_with(knobs=source.scenario.get_knobs().model_dump(mode="json"))
    forked = await resume_and_read(
        monkeypatch=monkeypatch,
        preset_name="knobs_default",
        overrides={"seed": 9},
        events=[started, *source.logger.events],
        round_number=2,
    )
    assert await forked.run(agent_id="ben", command="cat /tmp/x") == "a\nb\n"
