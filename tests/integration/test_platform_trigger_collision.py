"""A scenario's early round-end trigger must not spell one of the platform's."""

from pathlib import Path

import pytest

from glossogen.runtime.round_end_trigger import RoundEndTrigger
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)


class CollidingSmokeScenario(SmokeScenario):
    """Ends every round with the platform's own idle trigger."""

    def get_early_round_end_trigger(self) -> str | None:
        return RoundEndTrigger.ALL_AGENTS_IDLE.value


async def test_a_platform_trigger_returned_by_a_scenario_ends_the_run_in_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The round-ended metrics would otherwise count the round as one the clock ended.

    The supervisor records the failure as a ``simulation_ended`` with reason
    ``error``; the harness re-raises what it caught.
    """
    scenario = CollidingSmokeScenario(
        knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
    )
    briefing = ToolTurn(tool_name="read_notifications", args={})
    with pytest.raises(ValueError, match="is a platform trigger"):
        await run_simulation(
            scenario=scenario,
            scripts={
                FIRST_AGENT_ID: [briefing, SayTurn(text="done")],
                SECOND_AGENT_ID: [briefing, SayTurn(text="done")],
            },
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )
