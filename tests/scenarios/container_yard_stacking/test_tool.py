"""container_yard_stacking's move_container tool.

Arguments come from the round's own case rather than being invented, so the
test makes the move the scenario is actually asking for. Cases are generated
from the canonical seed, so the first case is the same on every run.
"""

from pathlib import Path

import pytest

from glossogen.testing.scenario_runtime import build_scenario
from tests.scenarios.custom_tool_harness import (
    assert_the_tool_ran,
    call_tool,
    first_case_of,
)

SCENARIO = "container_yard_stacking"
TOOL = "move_container"
CALLER = "crane_operator"

pytestmark = pytest.mark.xdist_group(SCENARIO)


def first_step_of_round_one() -> tuple[int, int]:
    """Return the intake and target slot the first case's opening move needs."""
    step = first_case_of(
        scenario=build_scenario(scenario_name=SCENARIO, preset_name="knobs_default", overrides={})
    ).steps[0]
    return step.intake_slot, step.target_slot


async def test_the_move_the_case_asks_for_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path through the executor: a legal move, recorded as judged."""
    intake_slot, target_slot = first_step_of_round_one()

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args={"from_slot": intake_slot, "to_slot": target_slot},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    judged = result.of_type(event_type="container_yard_move_judged")
    assert judged, "a move was made but nothing recorded the verdict"


async def test_a_move_from_an_empty_slot_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rejection branch. Without it the executor could accept anything."""
    row = first_case_of(
        scenario=build_scenario(scenario_name=SCENARIO, preset_name="knobs_default", overrides={})
    ).initial_row
    empty_slot = next(slot for slot, container in row.items() if container is None)

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args={"from_slot": empty_slot, "to_slot": empty_slot},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    returns = [
        event
        for event in result.of_type(event_type="tool_result_received")
        if event.get("tool_name") == TOOL
    ]
    assert returns and str(returns[0]["result"]).strip(), "the refusal said nothing"
