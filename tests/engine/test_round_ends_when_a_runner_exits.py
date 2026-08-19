"""A round still ends after an agent's runner has stopped taking turns.

`is_idle` is written in one place, inside `wait_for_notification`, and only when
the queue is empty. Every wake and every enqueue sets it back to False. So an
agent that stops between notifications leaves it False for good, and the ordinary
way to stop between notifications is to reach the `max_turns` cap and return.

The scripted harness switches the wall-clock limit off, on purpose: a limit that
fires first truncates a scripted run and changes what the scenario decided. That
leaves idle detection as the only way a phase can end, so one session stuck at
`is_idle == False` hangs the run rather than ending it a round early.

This is what `run-notebooks` was failing on in CI, roughly one run in five:
`03_compare_runs.ipynb` generates runs through this harness, and nbmake killed
the cell at its 300s limit. It reproduced on demand with the turn cap lowered so
the agents exhaust it mid-phase instead of after the last round had closed.

The cap is lowered here to reach that state directly. Waiting to see whether a
default run happens to hang would be testing the bug with the bug.
"""

from pathlib import Path

import pytest

import glossogen.testing.simulation_harness as simulation_harness
from glossogen.testing.scenario_runtime import run_rounds

SCENARIO = "warehouse_robot_recovery"
PRESET = "knobs_default"

# Low enough that both agents reach it while a round is still open. At the
# harness default they reach it after the last round has already ended, which is
# the case that always passed.
TURNS_BEFORE_A_ROUND_CAN_END = 3

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_a_round_ends_after_its_agents_run_out_of_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run reaches its end.

    No timeout is asserted and none is needed: before the fix this did not run
    slowly, it did not finish at all, so the test hanging is the failure.
    """
    monkeypatch.setattr(simulation_harness, "MAX_AGENT_TURNS", TURNS_BEFORE_A_ROUND_CAN_END)

    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name=PRESET,
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert result.events


async def test_a_run_whose_agents_keep_their_turns_still_ends_on_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix must not end a phase early, which is what the switched-off limit protects.

    With turns to spare, no runner has returned while a round is open, so every
    session answers on `is_idle` exactly as before and the round ends the same way.
    """
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name=PRESET,
        round_count=2,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert result.events
