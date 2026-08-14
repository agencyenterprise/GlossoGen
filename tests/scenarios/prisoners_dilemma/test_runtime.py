"""prisoners_dilemma, driven through its real round loop.

The one scenario that resolves rounds with no LLM anywhere: two players, a
payoff matrix, a deterministic verdict. It declares no postmortem channel, so
the phase never opens and there is nothing to switch off.
"""

from pathlib import Path

import pytest

from glossogen.testing.scenario_runtime import (
    assert_no_agent_crashed,
    assert_postmortem_never_ran,
    assert_round_loop_completed,
    messages_on_primary,
    run_rounds,
)

SCENARIO = "prisoners_dilemma"

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
    assert (
        messages_on_primary(result=result, scenario_name=SCENARIO, preset_name="knobs_default") >= 2
    )


async def test_it_never_opens_a_postmortem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Declaring no postmortem channel has to mean no phase, not an empty one."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        round_count=1,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_postmortem_never_ran(result=result)
