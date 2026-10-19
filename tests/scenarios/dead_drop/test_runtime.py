"""dead_drop through the real runner, tools and game clock, with scripted models."""

import asyncio
import json
from pathlib import Path

import pytest

from glossogen.models.event import AgentResumed, RoundEnded, RoundResultRecorded, ToolResultReceived
from glossogen.scenarios.dead_drop.events import DeadDropFsRead, DeadDropRoundResolved
from glossogen.scenarios.dead_drop.ids import BOTH_SUBMITTED_TRIGGER
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from tests.scenarios.dead_drop.dead_drop_wiring import build

pytestmark = pytest.mark.xdist_group("dead_drop")


def read(wait_for: str | None) -> ToolTurn:
    args: dict[str, object] = {}
    if wait_for is not None:
        args["wait_for"] = wait_for
    return ToolTurn(tool_name="read_notifications", args=args)


def run(command: str) -> ToolTurn:
    return ToolTurn(tool_name="run_command", args={"command": command})


def submit(answers: dict[str, str]) -> ToolTurn:
    return ToolTurn(tool_name="submit_answer", args={"answers": answers})


async def play(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    """Two rounds: ana leaves a file in round one, ben reads it in round two.

    Round one ends only once both have submitted, and ana writes before she
    submits, so the file is there when ben looks.
    """
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    cases = scenario._cases  # pyright: ignore[reportPrivateUsage]
    scripts: dict[str, list[ScriptedTurn]] = {
        "ana": [
            read(wait_for=None),
            run(command="echo hello > /tmp/from_ana"),
            read(wait_for=None),
            submit(answers=cases[0].expected_answers(agent_id="ana")),
            read(wait_for="next_round"),
            submit(answers=cases[1].expected_answers(agent_id="ana")),
            read(wait_for="next_round"),
        ],
        "ben": [
            read(wait_for=None),
            submit(answers=cases[0].expected_answers(agent_id="ben")),
            read(wait_for="next_round"),
            run(command="cat /tmp/from_ana"),
            submit(answers=cases[1].expected_answers(agent_id="ben")),
            read(wait_for="next_round"),
        ],
    }
    async with asyncio.timeout(60):
        result = await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )
    assert_no_agent_crashed(result=result)
    return result


async def test_both_rounds_end_on_submission_and_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert_round_loop_completed(result=result, round_count=2)
    assert [event.trigger for event in result.of_type(event_type=RoundEnded)] == [
        BOTH_SUBMITTED_TRIGGER,
        BOTH_SUBMITTED_TRIGGER,
    ]
    assert [event.success for event in result.of_type(event_type=RoundResultRecorded)] == [
        True,
        True,
    ]
    assert all(event.success for event in result.of_type(event_type=DeadDropRoundResolved))


async def test_a_file_left_in_round_one_is_read_in_round_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(tmp_path=tmp_path, monkeypatch=monkeypatch)
    [read_event] = [
        event for event in result.of_type(event_type=DeadDropFsRead) if event.agent_id == "ben"
    ]
    assert (read_event.round_number, read_event.authors, read_event.content) == (
        2,
        ["ana"],
        "hello\n",
    )


async def test_waiting_before_submitting_is_cut_short_with_a_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await play(tmp_path=tmp_path, monkeypatch=monkeypatch)
    ana_waits = [
        json.loads(event.result)
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == "ana" and event.tool_name == "read_notifications"
    ]
    briefing, released = ana_waits[0], ana_waits[1]
    assert briefing["briefings"] and "round_01.txt" in briefing["briefings"][0]
    assert released["wake_reasons"] == ["released"]
    assert "not submitted an answer for round 1" in released["notice"]
    assert any(
        "released" in event.wake_reasons
        for event in result.of_type(event_type=AgentResumed)
        if event.agent_id == "ana"
    )
