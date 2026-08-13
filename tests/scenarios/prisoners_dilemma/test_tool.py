"""prisoners_dilemma's submit_decision tool.

The one scenario that resolves a round with no LLM: both players submit, the
payoff matrix decides. That makes it the cleanest end-to-end check that a
custom tool can move a scenario from "no decisions" to a scored round.
"""

from pathlib import Path

import pytest

from tests.fakes.scripted_agent_model import SayTurn, ScriptedTurn, ToolTurn
from tests.scenarios.custom_tool_harness import assert_the_tool_ran, round_verdicts
from tests.scenarios.scenario_runtime import ROUND_SECONDS, build_scenario
from tests.testbed.simulation_harness import SimulationResult, never_times_out, run_simulation

SCENARIO = "prisoners_dilemma"
TOOL = "submit_decision"

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def play(
    decisions: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    """Run one round where each player submits the decision it was given."""
    scenario = build_scenario(
        scenario_name=SCENARIO,
        overrides={"round_count": 1, "max_round_duration_seconds": ROUND_SECONDS},
    )
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")
    scripts: dict[str, list[ScriptedTurn]] = {
        agent.agent_id: [
            ToolTurn(tool_name=TOOL, args={"decision": decisions[agent.agent_id]}),
            SayTurn(text="done"),
        ]
        for agent in agents
    }
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


async def test_both_players_cooperating_resolves_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two decisions in, one payoff out: the whole scenario in one round."""
    result = await play(
        decisions={"player_a": "cooperate", "player_b": "cooperate"},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    assert len(result.of_type(event_type="pd_decision_submitted")) == 2
    payoffs = result.of_type(event_type="pd_round_payoff_computed")
    assert payoffs, "both players decided but no payoff was computed"
    assert round_verdicts(result=result), "the round was never judged"


async def test_a_defection_is_recorded_as_submitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other branch of the matrix, so the tool cannot be hardcoded to one."""
    result = await play(
        decisions={"player_a": "cooperate", "player_b": "defect"},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    submitted = result.of_type(event_type="pd_decision_submitted")
    assert {event["decision"] for event in submitted} == {"cooperate", "defect"}
    assert result.of_type(event_type="pd_round_payoff_computed")
