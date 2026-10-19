"""Scripted turns and a runner for leaderboard_leak round-loop tests."""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.runtime.game_clock import PhaseTimeoutCheck
from glossogen.scenarios.leaderboard_leak.ids import AGENT_IDS, TEAM_OF
from glossogen.scenarios.leaderboard_leak.scenario import LeaderboardLeakScenario
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, run_simulation

ONE_ROUND: dict[str, Any] = {"round_count": 1}


def build(preset_name: str, overrides: dict[str, Any]) -> LeaderboardLeakScenario:
    scenario = build_scenario(
        scenario_name="leaderboard_leak", preset_name=preset_name, overrides=overrides
    )
    assert isinstance(scenario, LeaderboardLeakScenario)
    return scenario


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def wait_for_message() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "message"})


def wait_for_next_round() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})


def submit(task: int, answer: str, comment: str) -> ToolTurn:
    return ToolTurn(
        tool_name="submit_answer", args={"task": task, "answer": answer, "comment": comment}
    )


def answer_for(
    scenario: LeaderboardLeakScenario, round_number: int, agent_id: str, task: int
) -> str:
    """The value ``agent_id``'s team's task asks for."""
    return scenario.round_sheets(round_number=round_number).expected_answer(
        team_id=TEAM_OF[agent_id], task=task
    )


GUESS = "000000"
"""A task 4 answer no sheet holds: every value is at least 100000."""


def correct_round(
    scenario: LeaderboardLeakScenario, round_number: int, agent_id: str, bonus_answer: str
) -> list[ScriptedTurn]:
    """Read the briefing, answer tasks 1 to 3 correctly and task 4 with ``bonus_answer``,
    then wait for the next round."""
    return [
        read(),
        *[
            submit(
                task=task,
                answer=answer_for(
                    scenario=scenario, round_number=round_number, agent_id=agent_id, task=task
                ),
                comment=f"{agent_id} on task {task}",
            )
            for task in range(1, 4)
        ],
        submit(task=4, answer=bonus_answer, comment=f"{agent_id} on task 4"),
        wait_for_next_round(),
    ]


def assert_every_agent_scripted(scripts: Mapping[str, list[ScriptedTurn]]) -> None:
    """Fail when an agent has no script."""
    missing = set(AGENT_IDS) - set(scripts)
    assert not missing, f"no script for {sorted(missing)}"


async def play(
    scenario: LeaderboardLeakScenario,
    scripts: dict[str, list[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase_timed_out: PhaseTimeoutCheck,
) -> SimulationResult:
    assert_every_agent_scripted(scripts=scripts)
    async with asyncio.timeout(60):
        result = await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=phase_timed_out,
        )
    assert_no_agent_crashed(result=result)
    return result


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]
