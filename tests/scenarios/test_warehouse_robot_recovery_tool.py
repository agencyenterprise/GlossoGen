"""warehouse_robot_recovery's perform_recovery tool, driven with its judge stubbed.

The executor is where the scenario mutates its world, spends budget, records
its verdict event and decides the round. Nothing else in the suite enters it,
so a break here surfaces as a run that completes and reports a wrong number.

The assertion is on the recorded verdict event rather than the round outcome.
A round can need several judged actions before it is won, so the round result
cannot tell "the judge said no" apart from "the work is not finished yet".
"""

from pathlib import Path
from typing import Any

import pytest

from glossogen.scenarios.warehouse_robot_recovery.events import WarehouseRecoveryJudgment
from glossogen.scenarios.warehouse_robot_recovery.recovery_judge import (
    RecoveryJudgmentResult,
)
from tests.scenarios.custom_tool_harness import (
    assert_the_tool_ran,
    call_tool,
    round_verdicts,
    stub_the_judge,
)

SCENARIO = "warehouse_robot_recovery"
TOOL = "perform_recovery"
CALLER = "floor_associate"
ARGS: dict[str, Any] = {"action": "carry out every recovery step in order"}
OVERRIDES: dict[str, Any] = {}
JUDGED_EVENT = "warehouse_recovery_judged"
VERDICT_FIELD = "overall_success"

pytestmark = pytest.mark.xdist_group(SCENARIO)


def verdict(*, met: bool) -> RecoveryJudgmentResult:
    """Build a judge verdict where every criterion is ``met``."""
    return RecoveryJudgmentResult(
        judgment=WarehouseRecoveryJudgment(
            targets_correct_robot=met,
            addresses_all_faults=met,
            correct_order=met,
            correct_wait_times=met,
            respects_safety_constraints=met,
            no_forbidden_actions=met,
            final_state_safe=met,
        ),
        explanation="stubbed",
    )


async def test_a_passing_judgement_is_recorded_as_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor turns the judge's answer into an event; this is that wiring."""
    stub = stub_the_judge(monkeypatch=monkeypatch, verdict=verdict(met=True))

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args=ARGS,
        overrides=OVERRIDES,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    assert stub.calls, "the tool reached a verdict without consulting its judge"
    judged = result.of_type(event_type=JUDGED_EVENT)
    assert judged, f"the tool ran but logged no {JUDGED_EVENT}"
    assert judged[-1][VERDICT_FIELD] is True, "a passing judgement was recorded as a failure"


async def test_a_failing_judgement_is_recorded_and_loses_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mirror case. Without it, a tool hardcoded to pass still looks correct."""
    stub = stub_the_judge(monkeypatch=monkeypatch, verdict=verdict(met=False))

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id=CALLER,
        tool_name=TOOL,
        args=ARGS,
        overrides=OVERRIDES,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name=TOOL)
    assert stub.calls, "the tool refused the action without consulting its judge"
    judged = result.of_type(event_type=JUDGED_EVENT)
    assert judged, f"the tool ran but logged no {JUDGED_EVENT}"
    assert judged[-1][VERDICT_FIELD] is False, "a failing judgement was recorded as a pass"
    assert round_verdicts(result=result) == [False], "a refused action still won the round"
