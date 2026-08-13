"""hospital_bed_assignment_privacy's two tools, one per side of the task.

The transport lead routes the patient; the observer tries to intercept the same
routing from the public channel alone. Both executors are the scenario, so both
are driven here with the round's own assignment rather than invented values.
"""

from pathlib import Path

import pytest

from tests.scenarios.custom_tool_harness import (
    assert_the_tool_ran,
    call_tool,
    first_case_of,
)
from tests.scenarios.scenario_runtime import build_scenario

SCENARIO = "hospital_bed_assignment_privacy"

pytestmark = pytest.mark.xdist_group(SCENARIO)


def round_one_assignment() -> tuple[str, str, str]:
    """Return the patient, destination and transport mode the first case assigns."""
    case = first_case_of(scenario=build_scenario(scenario_name=SCENARIO, overrides={}))
    return case.assigned_patient_token, case.assigned_destination, case.assigned_transport_mode


async def test_routing_the_assigned_patient_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transport lead's whole job, executed exactly as the case specifies."""
    patient, destination, transport_mode = round_one_assignment()

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id="transport_lead",
        tool_name="route_patient",
        args={
            "patient_token": patient,
            "destination": destination,
            "transport_mode": transport_mode,
        },
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name="route_patient")
    routed = result.of_type(event_type="hospital_patient_routed")
    assert routed, "the patient was routed but nothing recorded it"
    assert routed[-1]["submitted_patient_token"] == patient
    assert (
        routed[-1]["overall_success"] is True
    ), "routing exactly what the case assigned was scored wrong"


async def test_an_intercept_is_recorded_against_the_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The observer's guess is the scenario's actual measurement, so it must land."""
    patient, destination, _ = round_one_assignment()

    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id="unauthorized_observer",
        tool_name="submit_intercept",
        args={"patient_token": patient, "destination": destination},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name="submit_intercept")
    intercepts = result.of_type(event_type="hospital_intercept_submitted")
    assert intercepts, "the observer submitted an intercept but nothing recorded it"
