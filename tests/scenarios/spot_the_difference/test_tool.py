"""spot_the_difference's submit_differences tool.

Two things make this one shaped differently from the other tool tests. Its judge
returns which planted differences were matched rather than a verdict, and a
team is scored only once *both* its viewers have submitted, so a single caller
gets "waiting for your partner" and no verdict at all. Both viewers act here.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.spot_the_difference.difference_judge import SubmissionJudgment
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from tests.scenarios.custom_tool_harness import first_case_of, stub_the_judge

SCENARIO = "spot_the_difference"
TOOL = "submit_differences"
TEAM_A = ("viewer_left_a", "viewer_right_a")

pytestmark = pytest.mark.xdist_group(SCENARIO)


def planted_difference_count() -> int:
    """Return how many differences the first case plants."""
    case = first_case_of(
        scenario=build_scenario(scenario_name=SCENARIO, preset_name="knobs_default", overrides={})
    )
    return len(case.differences)


async def both_viewers_submit(
    items: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimulationResult:
    """Run one round where both of team A's viewers submit ``items``."""
    scenario = build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
        },
    )
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")
    scripts: dict[str, list[ScriptedTurn]] = {}
    for agent in agents:
        if agent.agent_id in TEAM_A:
            scripts[agent.agent_id] = [
                ToolTurn(tool_name=TOOL, args={"differences": items}),
                SayTurn(text="done"),
            ]
        else:
            scripts[agent.agent_id] = [SayTurn(text="idle")]
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


async def test_one_viewer_alone_does_not_get_the_team_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The partner gate. Scoring a half-submitted team would score a guess."""
    count = planted_difference_count()
    stub_the_judge(
        monkeypatch=monkeypatch,
        verdict=SubmissionJudgment(
            matched_difference_indices=list(range(1, count + 1)),
            false_positive_count=0,
            explanation="stubbed",
        ),
    )
    scenario = build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
        },
    )
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")
    scripts: dict[str, list[ScriptedTurn]] = {}
    for agent in agents:
        if agent.agent_id == TEAM_A[0]:
            scripts[agent.agent_id] = [
                ToolTurn(tool_name=TOOL, args={"differences": ["a difference"]}),
                SayTurn(text="done"),
            ]
        else:
            scripts[agent.agent_id] = [SayTurn(text="idle")]
    result = await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert result.tool_calls(tool_name=TOOL), "the tool was never invoked"
    assert not result.of_type(
        event_type="difference_submission_judged"
    ), "a team was scored on one viewer's answer"


async def test_matching_every_planted_difference_passes_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All matched and nothing invented is the only way `found_all` is true."""
    count = planted_difference_count()
    stub_the_judge(
        monkeypatch=monkeypatch,
        verdict=SubmissionJudgment(
            matched_difference_indices=list(range(1, count + 1)),
            false_positive_count=0,
            explanation="stubbed",
        ),
    )

    result = await both_viewers_submit(
        items=[f"difference {index}" for index in range(1, count + 1)],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    judged = result.of_type(event_type="difference_submission_judged")
    assert judged, "both viewers submitted but no verdict was recorded"
    assert judged[-1]["found_all"] is True, "a complete, clean submission failed the gate"


async def test_a_false_positive_fails_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate is all-or-nothing, so one invented difference has to sink it."""
    count = planted_difference_count()
    stub_the_judge(
        monkeypatch=monkeypatch,
        verdict=SubmissionJudgment(
            matched_difference_indices=list(range(1, count + 1)),
            false_positive_count=1,
            explanation="stubbed",
        ),
    )

    result = await both_viewers_submit(
        items=[f"difference {index}" for index in range(1, count + 2)],
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    judged = result.of_type(event_type="difference_submission_judged")
    assert judged, "both viewers submitted but no verdict was recorded"
    assert judged[-1]["found_all"] is False, "a submission with a false positive passed the gate"
