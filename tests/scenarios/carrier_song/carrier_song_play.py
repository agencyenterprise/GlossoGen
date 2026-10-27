"""Scripted turns and a runner for carrier_song round-loop tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.carrier_song.round_material import (
    RoundMaterial,
    SongShape,
    generate_round_material,
)
from glossogen.scenarios.carrier_song.scenario import CarrierSongScenario
from glossogen.scenarios.carrier_song.secret_code import CODE_ALPHABET
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

ONE_ROUND: dict[str, Any] = {"round_count": 1}

BIT_EXECUTOR = """
SECRET = "{secret}"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def noise(song):
    bits = [(ALPHABET.index(char) >> shift) & 1 for char in SECRET for shift in range(6)]
    return [2 if bits[tick % len(bits)] else -2 for tick in range(len(song))]
"""
"""Plays six bits per character of SECRET, low bit first, one tick each, cycling."""

WRONG_CODE = "AAAAAA"
"""A well-formed decoding that is no round's secret under seed 42."""


def build(overrides: dict[str, Any]) -> CarrierSongScenario:
    scenario = build_scenario(
        scenario_name="carrier_song", preset_name="knobs_default", overrides=overrides
    )
    assert isinstance(scenario, CarrierSongScenario)
    return scenario


def material_of(scenario: CarrierSongScenario) -> list[RoundMaterial]:
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
        code_length=knobs.code_length,
        channel_noise_sigma=knobs.channel_noise_sigma,
    )


def bit_noise(secret: str, length: int) -> list[int]:
    """What ``BIT_EXECUTOR`` returns for ``secret`` on a song of ``length`` ticks."""
    bits = [(CODE_ALPHABET.index(char) >> shift) & 1 for char in secret for shift in range(6)]
    return [2 if bits[tick % len(bits)] else -2 for tick in range(length)]


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def wait_for_next_round() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})


def call(tool_name: str) -> ToolTurn:
    return ToolTurn(tool_name=tool_name, args={})


def write_executor(code: str) -> ToolTurn:
    return ToolTurn(tool_name="write_executor", args={"code": code})


def submit_decoding(secret: str) -> ToolTurn:
    return ToolTurn(tool_name="submit_decoding", args={"secret": secret})


def run_python(code: str) -> ToolTurn:
    return ToolTurn(tool_name="run_python", args={"code": code})


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]


async def play(
    scenario: CarrierSongScenario,
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
