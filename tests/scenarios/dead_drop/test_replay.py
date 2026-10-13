"""Rebuilding the server from a run's log, as a fork or resume does."""

from typing import Any

import pytest

from glossogen.models.event import InjectionDelivered
from glossogen.scenarios.dead_drop.events import DeadDropCaseStarted, DeadDropFsRead
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER
from tests.scenarios.dead_drop.dead_drop_wiring import (
    RecordingLogger,
    Wired,
    bind,
    build,
    local_token_counter,
    wire,
)

pytestmark = pytest.mark.xdist_group("dead_drop")


async def resume(
    monkeypatch: pytest.MonkeyPatch, preset_name: str, events: list[Any], round_number: int
) -> Wired:
    """A fresh scenario restored from ``events`` and entering ``round_number``."""
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter", local_token_counter
    )
    scenario = build(preset_name=preset_name, overrides={})
    logger = RecordingLogger()
    runtime = bind(scenario=scenario, logger=logger)
    scenario.restore_state_from_events(events=list(events))
    runtime.set_current_round(round_number=round_number)
    await scenario.on_round_advanced(round_number=round_number)
    return Wired(scenario=scenario, logger=logger, runtime=runtime)


async def resume_and_read(
    monkeypatch: pytest.MonkeyPatch, preset_name: str, events: list[Any], round_number: int
) -> Wired:
    """``resume`` into a new round, whose briefing both agents then read."""
    resumed = await resume(
        monkeypatch=monkeypatch, preset_name=preset_name, events=events, round_number=round_number
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


async def test_resuming_inside_a_round_keeps_its_answers_and_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, preset_name="knobs_fresh_fs", overrides={})
    await wired.run(agent_id="ana", command="echo note > /tmp/note")
    await wired.submit(
        agent_id="ana", answers=wired.case(round_number=1).expected_answers(agent_id="ana")
    )
    events = [
        *wired.logger.events,
        *(
            InjectionDelivered(round_number=1, agent_id=agent_id, text="briefing")
            for agent_id in ("ana", "ben")
        ),
    ]
    resumed = await resume(
        monkeypatch=monkeypatch,
        preset_name="knobs_fresh_fs",
        events=events,
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
        events=source.logger.events,
        round_number=2,
    )
    assert (await forked.run(agent_id="ana", command="ls /tmp")).strip() == ""
    assert await forked.run(agent_id="ana", command="ls ~/cases") == "round_02.txt\n"
