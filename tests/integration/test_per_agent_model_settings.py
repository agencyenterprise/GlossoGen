"""An agent whose ``model_overrides`` entry names its own ``model_settings`` runs with them.

The supervisor gives each agent its settings and the agent's ``AgentRegistered``
event records them. The test reads them back from that event.
"""

from pathlib import Path

import pytest

from glossogen.model_catalog import Provider
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered
from glossogen.scenarios.base_knobs import AgentModelOverride
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

RUN_SETTINGS = AgentModelSettings(max_tokens=2048, thinking="medium")
SEAT_SETTINGS = AgentModelSettings(
    max_tokens=1024,
    temperature=0.7,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)


async def test_each_agent_registers_with_its_own_settings_or_the_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = SmokeScenario(
        knobs=SmokeKnobs(
            round_count=1,
            max_round_duration_seconds=45,
            model_overrides={
                SECOND_AGENT_ID: AgentModelOverride(
                    model=f"scripted::{SECOND_AGENT_ID}",
                    provider=Provider.SELF_HOSTED,
                    model_settings=SEAT_SETTINGS,
                )
            },
            agent_model_settings=RUN_SETTINGS,
        )
    )

    result = await run_simulation(
        scenario=scenario,
        scripts={FIRST_AGENT_ID: [], SECOND_AGENT_ID: []},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    registered = {
        event.agent_id: event.model_settings for event in result.of_type(event_type=AgentRegistered)
    }
    assert registered == {FIRST_AGENT_ID: RUN_SETTINGS, SECOND_AGENT_ID: SEAT_SETTINGS}
