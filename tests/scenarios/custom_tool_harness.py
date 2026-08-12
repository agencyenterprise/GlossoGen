"""Drive a scenario's own tool through a real simulation, with the judge stubbed.

The round-loop tests deliberately avoid these tools, so the executors sat at
18-35% line coverage: registration ran, the bodies did not. That is where each
scenario actually lives, mutating world state, spending budget, calling its
judge and deciding the round.

Judges reach an LLM, so they are stubbed at one seam. Scenarios build their
judge through ``create_provider`` and, since it is built on first use rather
than at construction, patching that one function replaces every scenario's
judge without touching scenario code.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from glossogen.llm import deferred_provider
from glossogen.scenario_protocol import SimulationScenario
from tests.fakes.scripted_agent_model import SayTurn, ScriptedTurn, ToolTurn
from tests.fakes.stub_llm_provider import StubLLMProvider
from tests.scenarios.scenario_runtime import ROUND_SECONDS, build_scenario
from tests.testbed.simulation_harness import SimulationResult, run_simulation

# Enough queued verdicts that a scenario judging more than once per round (a
# per-team or per-stage judge) does not run dry mid-test.
VERDICTS_QUEUED = 12


def stub_the_judge(monkeypatch: pytest.MonkeyPatch, verdict: BaseModel) -> StubLLMProvider:
    """Make every judge in the process return ``verdict``.

    Returns the stub so a test can assert the judge was actually consulted. A
    tool that silently skips its judge would otherwise look identical to one
    that ran it and was told no.
    """
    stub = StubLLMProvider()
    for _ in range(VERDICTS_QUEUED):
        stub.queue(response=verdict)

    def build_stub(**kwargs: object) -> StubLLMProvider:
        _ = kwargs
        return stub

    monkeypatch.setattr(deferred_provider, "create_provider", build_stub)
    return stub


async def call_tool(
    scenario_name: str,
    caller_agent_id: str,
    tool_name: str,
    args: dict[str, Any],
    overrides: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Run one round in which ``caller_agent_id`` invokes ``tool_name`` once.

    Every other agent idles, so the only scenario-specific behaviour in the run
    is the tool call under test.
    """
    merged: dict[str, Any] = {
        "round_count": 1,
        "max_round_duration_seconds": ROUND_SECONDS,
        "postmortem_enabled": False,
    }
    merged.update(overrides)
    scenario = build_scenario(scenario_name=scenario_name, overrides=merged)
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")
    assert caller_agent_id in {
        agent.agent_id for agent in agents
    }, f"{scenario_name} has no agent {caller_agent_id}"

    scripts: dict[str, list[ScriptedTurn]] = {}
    for agent in agents:
        if agent.agent_id == caller_agent_id:
            scripts[agent.agent_id] = [
                ToolTurn(tool_name=tool_name, args=args),
                SayTurn(text="done"),
            ]
        else:
            scripts[agent.agent_id] = [SayTurn(text="idle")]
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )


def first_case_of(scenario: SimulationScenario) -> Any:
    """Return the first case the scenario's world generated.

    Cases are built at construction from the canonical seed, so the round-one
    case can be read before the run and used to give a tool the arguments the
    scenario is actually asking for. Typed as ``Any`` because each scenario has
    its own case shape and the base world exposes none of them.
    """
    world: Any = scenario.get_world()
    return world._cases[0]


def assert_the_tool_ran(result: SimulationResult, tool_name: str) -> None:
    """The executor has to have been entered, and not by raising on the way in."""
    calls = result.tool_calls(tool_name=tool_name)
    assert calls, f"{tool_name} was never invoked"
    assert not result.failed_tool_calls(), f"tool call failed: {result.failed_tool_calls()}"


def round_verdicts(result: SimulationResult) -> list[bool]:
    """Return each recorded round verdict, in order."""
    return [event["success"] for event in result.of_type(event_type="round_result_recorded")]
