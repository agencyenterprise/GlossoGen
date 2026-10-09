"""spillway_release's four tools, the widest custom-tool surface in the tree.

Three agents each hold a different lever and none can see the others' state, so
every tool has to work on its own for the round to be winnable at all. They were
the least covered executors in the repo at 18%.
"""

from pathlib import Path

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.spillway_release.events import (
    SpillwayEvacuated,
    SpillwayGatesOpened,
    SpillwayParkNotified,
)
from tests.scenarios.custom_tool_harness import assert_the_tool_ran, call_tool

SCENARIO = "spillway_release"

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_reading_the_gauge_reports_state_without_changing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The operator's only source of truth. It must answer, and answer something."""
    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id="dam_operator",
        tool_name="read_gauge",
        args={},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name="read_gauge")
    returns = [
        event
        for event in result.of_type(event_type=ToolResultReceived)
        if event.tool_name == "read_gauge"
    ]
    assert returns and returns[0].result.strip(), "read_gauge returned nothing"


async def test_opening_gates_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The release itself, and the event the round outcome is reconstructed from."""
    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id="dam_operator",
        tool_name="open_gates",
        args={"count": 2, "duration_hours": 3.0},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name="open_gates")
    opened = result.of_type(event_type=SpillwayGatesOpened)
    assert opened, "gates were opened but nothing recorded it"
    assert opened[-1].gate_count_opened == 2
    assert opened[-1].duration_hours == 3.0


async def test_notifying_the_park_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ranger's lever, held by an agent who cannot read the gauge."""
    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id="park_ranger",
        tool_name="notify_park",
        args={"action": "close"},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name="notify_park")
    notified = result.of_type(event_type=SpillwayParkNotified)
    assert notified, "the park was notified but nothing recorded it"


async def test_evacuating_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Civil defence's one irreversible action."""
    result = await call_tool(
        scenario_name=SCENARIO,
        caller_agent_id="civil_defense",
        tool_name="evacuate",
        args={},
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_the_tool_ran(result=result, tool_name="evacuate")
    assert result.of_type(event_type=SpillwayEvacuated), "the evacuation was not recorded"
