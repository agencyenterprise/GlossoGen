"""hospital_bed_assignment_privacy, driven through its real round loop.

Only the model is faked. The world, the game clock, the postmortem phase and
the round verdict all run for real, so a break in any of them fails here rather
than minutes into a paid run.
"""

from pathlib import Path

import pytest

from tests.scenarios.scenario_runtime import (
    assert_no_agent_crashed,
    assert_postmortem_never_ran,
    assert_postmortem_ran,
    assert_round_loop_completed,
    messages_on_primary,
    run_rounds,
)

SCENARIO = "hospital_bed_assignment_privacy"

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_it_plays_two_rounds_and_judges_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two rounds so a bug in the round transition has somewhere to show."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_round_loop_completed(result=result, round_count=2)
    assert_no_agent_crashed(result=result)
    assert messages_on_primary(result=result, scenario_name=SCENARIO) >= 2


async def test_postmortem_opens_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phase should open and close once per round while it is switched on."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        round_count=1,
        overrides={"postmortem_enabled": True},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_ran(result=result, round_count=1)


async def test_postmortem_stays_shut_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switched off, the phase must not open at all."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        round_count=1,
        overrides={"postmortem_enabled": False},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_never_ran(result=result)
    assert_round_loop_completed(result=result, round_count=1)
