"""Scripted turns and a runner for signal_game_carrier round-loop tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.signal_game_carrier.boards import Square
from glossogen.scenarios.signal_game_carrier.round_material import (
    RoundMaterial,
    generate_round_material,
)
from glossogen.scenarios.signal_game_carrier.scenario import SignalGameCarrierScenario
from glossogen.scenarios.signal_game_carrier.song import SongShape
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

ONE_ROUND: dict[str, Any] = {"round_count": 1}

ALTERNATING_EXECUTOR = """
def noise(song):
    return [2 if tick % 2 == 0 else -2 for tick in range(len(song))]
"""
"""Plays +2 on even ticks and -2 on odd ones."""

STEADY_EXECUTOR = """
def noise(song):
    return [1 for _ in song]
"""
"""Plays +1 at every tick."""


def alternating_noise(length: int) -> list[int]:
    """What ``ALTERNATING_EXECUTOR`` returns on a song of ``length`` ticks."""
    return [2 if tick % 2 == 0 else -2 for tick in range(length)]


def steady_noise(length: int) -> list[int]:
    """What ``STEADY_EXECUTOR`` returns on a song of ``length`` ticks."""
    return [1] * length


def build(overrides: dict[str, Any]) -> SignalGameCarrierScenario:
    scenario = build_scenario(
        scenario_name="signal_game_carrier", preset_name="knobs_default", overrides=overrides
    )
    assert isinstance(scenario, SignalGameCarrierScenario)
    return scenario


def material_of(scenario: SignalGameCarrierScenario) -> list[RoundMaterial]:
    """Every round's material, drawn from the scenario's knobs as the scenario draws it."""
    knobs = scenario.get_knobs()
    return generate_round_material(
        seed=knobs.seed,
        round_count=knobs.round_count,
        shape=SongShape(
            length=knobs.song_length,
            motif_length=knobs.motif_length,
            amplitude=knobs.song_amplitude,
        ),
        channel_noise_sigma=knobs.channel_noise_sigma,
        grid_size=knobs.grid_size,
        colour_count=knobs.colour_count,
    )


def squares_of_colour(grid: list[list[str]], colour: str) -> list[Square]:
    """Every square of ``grid`` holding ``colour``."""
    return [
        Square(row=row_index + 1, col=col_index + 1)
        for row_index, row in enumerate(grid)
        for col_index, held in enumerate(row)
        if held == colour
    ]


def shared_colour(material: RoundMaterial, first: str, second: str) -> str:
    """A colour both grids hold. The draw guarantees there is one."""
    held = [
        {colour for row in material.grids[agent_id] for colour in row}
        for agent_id in (first, second)
    ]
    return sorted(held[0] & held[1])[0]


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def wait_for_next_round() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})


def call(tool_name: str) -> ToolTurn:
    return ToolTurn(tool_name=tool_name, args={})


def write_executor(code: str) -> ToolTurn:
    return ToolTurn(tool_name="write_executor", args={"code": code})


def end_round(square: Square) -> ToolTurn:
    return ToolTurn(tool_name="end_round", args={"row": square.row, "col": square.col})


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]


def plays(code: str, square: Square) -> list[ScriptedTurn]:
    """Brief, put ``code`` in place, transmit, wait, read the recording, pick ``square``."""
    return [
        read(),
        write_executor(code=code),
        call(tool_name="transmit"),
        read(),
        call(tool_name="read_recording"),
        end_round(square=square),
        wait_for_next_round(),
    ]


async def play(
    scenario: SignalGameCarrierScenario,
    scripts: dict[str, list[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
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
