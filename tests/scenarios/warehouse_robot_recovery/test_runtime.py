"""warehouse_robot_recovery, driven through its real round loop.

This is the scenario whose copy of the postmortem-duration check had lost its
`postmortem_enabled` condition, so it is the one most worth running both ways.
"""

from pathlib import Path

import pytest

from glossogen.testing.scenario_runtime import (
    assert_no_agent_crashed,
    assert_postmortem_never_ran,
    assert_postmortem_ran,
    assert_round_loop_completed,
    messages_on_primary,
    run_rounds,
)

SCENARIO = "warehouse_robot_recovery"

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_it_plays_two_rounds_and_judges_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two rounds so a bug in the round transition has somewhere to show."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_round_loop_completed(result=result, round_count=2)
    assert_no_agent_crashed(result=result)
    assert result.of_type(event_type="warehouse_case_started"), "no per-round ground truth logged"
    assert (
        messages_on_primary(result=result, scenario_name=SCENARIO, preset_name="knobs_default") >= 2
    )


async def test_postmortem_opens_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default preset has it on, so the phase should run once per round."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=1,
        overrides={"postmortem_enabled": True},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_ran(result=result, round_count=1)


async def test_postmortem_stays_shut_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The case the broken copy got wrong: configured off, must not run."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=1,
        overrides={"postmortem_enabled": False},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_never_ran(result=result)
    assert_round_loop_completed(result=result, round_count=1)
