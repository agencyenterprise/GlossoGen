"""A tool call whose model request began in a round that has since ended, against a real
runtime.

The scripted harness cannot produce this: it issues a request and runs its tool calls
inside one round. Here the scenario's tools are called directly, with the round
advanced between the request and the call.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.notification_payload import NotificationInbox, Wake
from glossogen.runtime.round_end_trigger import RoundEndTrigger
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.runtime.wait_for import WaitFor
from glossogen.scenarios.carrier_song.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.carrier_song.scenario import CarrierSongScenario
from glossogen.testing.recording_logger import RecordingLogger
from tests.scenarios.carrier_song.carrier_song_play import build

pytestmark = pytest.mark.xdist_group("carrier_song")


async def wire(scenario: CarrierSongScenario) -> SimulationRuntime:
    """A started run of ``scenario``: round 1 open and both players briefed."""
    agents = scenario.get_agents(default_model="test", default_provider="self-hosted")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    logger = RecordingLogger()
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=scenario.get_channels(),
        event_logger=logger,  # type: ignore[arg-type]  # in-memory stand-in for the log
        agent_sessions=sessions,
        agent_tool_allowlists={agent.agent_id: frozenset(agent.tool_names) for agent in agents},
        world_context=WorldContext(agent_sessions=sessions, event_logger=logger),  # type: ignore[arg-type]
        agent_configs=agents,
        simulation_start_time=datetime.now(tz=UTC),
    )
    scenario.bind_runtime(runtime=runtime)
    await scenario.on_round_advanced(round_number=1)
    await runtime.deliver_round_injections(round_number=1)
    for agent_id in (PLAYER_A, PLAYER_B):
        await scenario.read_notifications(
            agent_id=agent_id, wake=_wake(runtime=runtime, agent_id=agent_id)
        )
        scenario.on_model_request_started(agent_id=agent_id)
    return runtime


def _wake(runtime: SimulationRuntime, agent_id: str) -> Wake:
    """The wake the runner would hand ``agent_id``, carrying whatever it was sent."""
    session = runtime.resolve_session(agent_id=agent_id)
    return Wake(
        wait_for=WaitFor.ANY,
        reasons=[],
        waited_seconds=0.0,
        inbox=NotificationInbox(session=session, channel_router=runtime.channel_router),
        terminated=False,
        done_reason="",
        release_detail="",
    )


def executor_of(scenario: CarrierSongScenario, tool_name: str) -> Any:
    [tool] = [tool for tool in scenario.get_tools() if tool.name == tool_name]
    return tool.executor


async def test_a_call_from_a_round_that_has_ended_names_both_rounds() -> None:
    scenario = build(overrides={"round_count": 3})
    runtime = await wire(scenario=scenario)
    await scenario.on_round_ended(round_number=1, trigger=RoundEndTrigger.ALL_AGENTS_WAITING.value)
    runtime.set_current_round(round_number=2)
    await scenario.on_round_advanced(round_number=2)

    with pytest.raises(ValueError) as refused:
        await executor_of(scenario=scenario, tool_name="read_song")(agent_id=PLAYER_A)

    assert str(refused.value) == (
        "Round 1 has ended. Call read_notifications() for the round 2 briefing."
    )


async def test_a_call_while_no_round_is_open_points_at_the_next_briefing() -> None:
    scenario = build(overrides={"round_count": 3})
    await wire(scenario=scenario)
    await scenario.on_round_ended(round_number=1, trigger=RoundEndTrigger.ALL_AGENTS_WAITING.value)

    with pytest.raises(ValueError) as refused:
        await executor_of(scenario=scenario, tool_name="read_received")(agent_id=PLAYER_B)

    assert str(refused.value) == (
        "Round 1 has ended. Call read_notifications(wait_for='next_round')."
    )
