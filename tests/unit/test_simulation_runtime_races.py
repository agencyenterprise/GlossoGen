"""Runtime checks repeated after awaited pre-send work."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from glossogen.llm.token_counter import TokenCounter
from glossogen.runtime.activity_notification import DoneNotification
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.testing.scenario_runtime import build_scenario


class RecordingLogger:
    """Keep logged events in memory."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        self.events.append(event)


class BlockingCounter(TokenCounter):
    """Expose the await between the initial authorization check and the write."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def _count_impl(self, text: str) -> int:
        self.started.set()
        await self.release.wait()
        return len(text.split())


async def _runtime(
    monkeypatch: pytest.MonkeyPatch,
    counter: BlockingCounter,
) -> SimulationRuntime:
    def token_counter(provider: str, model: str) -> TokenCounter:
        del provider, model
        return counter

    scenario = build_scenario(
        scenario_name="textcraft_shared_workspace",
        preset_name="knobs_default",
        overrides={"round_count": 1, "virtual_clock": False},
    )
    agents = scenario.get_agents("test", "self-hosted")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    logger = RecordingLogger()
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter",
        token_counter,
    )
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=scenario.get_channels(),
        event_logger=logger,  # type: ignore[arg-type]
        agent_sessions=sessions,
        agent_tool_allowlists={agent.agent_id: frozenset(agent.tool_names) for agent in agents},
        world_context=WorldContext(
            agent_sessions=sessions,
            event_logger=logger,  # type: ignore[arg-type]
        ),
        agent_configs=agents,
        simulation_start_time=datetime.now(tz=UTC),
    )
    scenario.bind_runtime(runtime=runtime)
    await scenario.on_round_advanced(round_number=1)
    return runtime


@pytest.mark.asyncio
async def test_send_rechecks_membership_after_token_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An agent removed while token counting must not publish afterwards."""
    counter = BlockingCounter()
    runtime = await _runtime(monkeypatch=monkeypatch, counter=counter)
    send = asyncio.create_task(
        runtime.publish_message(
            agent_id="crafter_1",
            channel_id="workspace",
            text="message in flight",
            force=False,
        )
    )

    await counter.started.wait()
    runtime.channel_router.update_membership(
        channel_id="workspace",
        member_agent_ids=["crafter_2", "crafter_3"],
    )
    counter.release.set()

    with pytest.raises(ValueError, match="not a member"):
        await send
    assert runtime.channel_router.get_history(channel_id="workspace") == []


@pytest.mark.asyncio
async def test_send_rechecks_session_termination_after_token_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runner being swapped out must not complete an in-flight send."""
    counter = BlockingCounter()
    runtime = await _runtime(monkeypatch=monkeypatch, counter=counter)
    send = asyncio.create_task(
        runtime.publish_message(
            agent_id="crafter_1",
            channel_id="workspace",
            text="message in flight",
            force=False,
        )
    )

    await counter.started.wait()
    runtime.resolve_session(agent_id="crafter_1").push_notification(
        DoneNotification(reason="agent_swap")
    )
    counter.release.set()

    with pytest.raises(ValueError, match="no longer active"):
        await send
    assert runtime.channel_router.get_history(channel_id="workspace") == []
