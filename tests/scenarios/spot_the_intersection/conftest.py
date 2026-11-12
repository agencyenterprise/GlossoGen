"""Helpers shared by spot_the_intersection's tests that play scripted rounds."""

import inspect
from pathlib import Path

import pytest

from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject, cell_label
from glossogen.scenarios.spot_the_intersection.world import SpotTheIntersectionWorld
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

SCENARIO = "spot_the_intersection"
TOOL = "submit_object"
TEAM_A = ("viewer_a_1", "viewer_a_2", "viewer_a_3", "viewer_a_4")
TEAM_B = ("viewer_b_1", "viewer_b_2", "viewer_b_3", "viewer_b_4")


def one_round_scenario() -> SimulationScenario:
    """The shipped two-team preset, cut to one round with no debrief."""
    return build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
        },
    )


def one_to_one_scenario(overrides: dict[str, object]) -> SimulationScenario:
    """The one-to-one preset, cut to one round with no debrief, then ``overrides``."""
    return build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_one_to_one",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
            **overrides,
        },
    )


def world_of(scenario: SimulationScenario) -> SpotTheIntersectionWorld:
    """The scenario's world, typed."""
    world = scenario.get_world()
    assert isinstance(world, SpotTheIntersectionWorld)
    return world


def answer_of(scenario: SimulationScenario) -> BoardObject:
    """Round one's answer."""
    return world_of(scenario=scenario).round_boards(round_number=1).certificate.answer


def submit(obj: BoardObject) -> ToolTurn:
    """A turn submitting ``obj``."""
    return ToolTurn(
        tool_name=TOOL,
        args={
            "shape": obj.shape,
            "color": obj.color,
            "cell": cell_label(column=obj.column, row=obj.row),
        },
    )


async def play(
    scenario: SimulationScenario,
    scripts: dict[str, list[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Run one round; agents without a script idle."""
    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        scripts.setdefault(agent.agent_id, [SayTurn(text="idle")])
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def say_to(to: str, text: str) -> ToolTurn:
    """A one-to-one turn sending ``text`` to the teammate or channel ``to``."""
    return ToolTurn(tool_name="send_message", args={"to": to, "text": text, "force": True})


def say_on(scenario: SimulationScenario, channel_id: str, text: str) -> ToolTurn:
    """A turn sending ``text``, with the arguments this scenario's send takes."""
    parameters = inspect.signature(scenario.send_message_executor()).parameters
    arguments: dict[str, object] = {"text": text}
    if "channel_id" in parameters:
        arguments["channel_id"] = channel_id
    if "force" in parameters:
        arguments["force"] = True
    return ToolTurn(tool_name="send_message", args=arguments)
