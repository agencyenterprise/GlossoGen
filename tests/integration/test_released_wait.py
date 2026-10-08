"""A scenario can resume a parked agent itself, with a reason the agent reads.

A team whose every member waits for a teammate's message is deadlocked: nobody
writes first. A scenario that treats that as a condition to answer rather than
a round to end releases one of them from ``on_agent_parked``.
"""

import json
from pathlib import Path

import pytest

from glossogen.runtime.wait_for import WaitFor
from glossogen.testing.scripted_agent import SayTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

DEADLOCK = "Every teammate is waiting for a message. Nobody will write first; act."


class DeadlockReleasingSmoke(SmokeScenario):
    """Releases the last agent to park once the whole team waits on each other."""

    def on_agent_parked(self, agent_id: str) -> None:
        parked = self.runtime.parked_waits()
        everyone_waits_for_a_message = all(
            agent in parked and parked[agent].wait_for is WaitFor.MESSAGE
            for agent in self.runtime.running_agent_ids()
        )
        if everyone_waits_for_a_message:
            self.runtime.release_wait(agent_id=agent_id, detail=DEADLOCK)


async def run_deadlocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    # The round's briefing is queued before the agents start and satisfies a
    # message wait at registration, so each agent reads it first and parks after.
    read_the_briefing = ToolTurn(tool_name="read_notifications", args={})
    wait_for_a_message = ToolTurn(tool_name="read_notifications", args={"wait_for": "message"})
    return await run_simulation(
        scenario=DeadlockReleasingSmoke(
            knobs=SmokeKnobs(round_count=1, max_round_duration_seconds=45, model_overrides={})
        ),
        scripts={
            FIRST_AGENT_ID: [read_the_briefing, wait_for_a_message, SayTurn(text="done")],
            SECOND_AGENT_ID: [read_the_briefing, wait_for_a_message, SayTurn(text="done")],
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


async def test_the_release_reaches_one_agent_with_the_scenarios_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = await run_deadlocked(tmp_path=tmp_path, monkeypatch=monkeypatch)
    released = [
        e for e in result.of_type(event_type="agent_resumed") if "released" in e["wake_reasons"]
    ]
    assert len(released) == 1
    answers = [
        json.loads(e["result"])
        for e in result.of_type(event_type="tool_result_received")
        if e["tool_name"] == "read_notifications"
        and e["agent_id"] == released[0]["agent_id"]
        and DEADLOCK in e["result"]
    ]
    assert len(answers) == 1
    assert answers[0]["type"] == "no_activity"
    assert answers[0]["detail"] == DEADLOCK
