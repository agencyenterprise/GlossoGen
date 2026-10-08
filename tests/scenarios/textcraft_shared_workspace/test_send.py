"""``send_message``, direct channels and message wake-ups, against a real runtime.

The tool functions are called directly, as the runner builds them for each
agent, so the order of sends is the test's, not the scheduler's.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic_ai import ModelRetry

from glossogen.llm.token_counter import TokenCounter
from glossogen.runners.agent_tools import build_agent_tools
from glossogen.runners.read_notifications_tool import RunTermination
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.runtime.wait_for import WaitFor
from glossogen.scenarios.textcraft_shared_workspace.scenario import (
    TextcraftSharedWorkspaceScenario,
)
from glossogen.testing.scenario_runtime import build_scenario

pytestmark = pytest.mark.xdist_group("textcraft_shared_workspace")


class RecordingLogger:
    """Keeps logged events in memory."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def log(self, event: Any) -> None:
        self.events.append(event)


class WordCounter(TokenCounter):
    """Counts words, so no provider is contacted."""

    async def _count_impl(self, text: str) -> int:
        return len(text.split())


class Wired:
    """A started round of the workspace scenario, with each agent's tools built on demand."""

    def __init__(self, logger: RecordingLogger, runtime: SimulationRuntime) -> None:
        self.logger = logger
        self.runtime = runtime

    def tools_of(self, agent_id: str) -> dict[str, Any]:
        """The tools the runner would offer ``agent_id``, by name."""
        tools = build_agent_tools(
            runtime=self.runtime, agent_id=agent_id, termination=RunTermination()
        )
        return {tool.name: tool.function for tool in tools}

    async def call(self, agent_id: str, tool_name: str, **arguments: Any) -> Any:
        return await self.tools_of(agent_id=agent_id)[tool_name](**arguments)

    def deliveries(self, agent_id: str) -> list[Any]:
        return [
            event
            for event in self.logger.events
            if event.event_type == "workspace_message_context_delivered"
            and event.agent_id == agent_id
        ]


def local_token_counter(provider: str, model: str) -> TokenCounter:
    """Stand in for the provider-backed counter."""
    _ = provider, model
    return WordCounter()


async def wire(monkeypatch: pytest.MonkeyPatch) -> Wired:
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter",
        local_token_counter,
    )
    scenario = build_scenario(
        scenario_name="textcraft_shared_workspace",
        preset_name="knobs_default",
        overrides={"round_count": 1, "virtual_clock": False},
    )
    agents = scenario.get_agents("test", "self-hosted")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    logger = RecordingLogger()
    world_context = WorldContext(
        agent_sessions=sessions, event_logger=logger  # type: ignore[arg-type]
    )
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=scenario.get_channels(),
        event_logger=logger,  # type: ignore[arg-type]
        agent_sessions=sessions,
        agent_tool_allowlists={agent.agent_id: frozenset(agent.tool_names) for agent in agents},
        world_context=world_context,
        agent_configs=agents,
        simulation_start_time=datetime.now(tz=UTC),
    )
    scenario.bind_runtime(runtime=runtime)
    await scenario.on_round_advanced(round_number=1)
    return Wired(logger=logger, runtime=runtime)


async def test_directed_messages_are_private_and_delivered_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    sent = await wired.call("crafter_1", "send_message", text="Please make A", to=["crafter_2"])
    assert sent["status"] == "sent"
    assert "Depot now" in sent["workspace"]
    hidden = await wired.call("crafter_3", "observe")
    assert "Please make A" not in hidden
    delivered = await wired.call("crafter_2", "observe")
    assert sent["message_id"] in delivered and "Please make A" in delivered
    assert "to=crafter_2" in delivered
    assert "Please make A" not in await wired.call("crafter_2", "observe")
    reply = await wired.call("crafter_2", "send_message", text="Agreed", to=["crafter_1"])
    incoming = await wired.call("crafter_1", "observe")
    assert reply["message_id"] in incoming
    assert wired.runtime.channel_router.get_history("workspace") == []
    assert len(wired.runtime.channel_router.get_history("dm:crafter_1+crafter_2")) == 2
    assert wired.deliveries("crafter_3") == []
    assert [e.delivery_carrier for e in wired.deliveries("crafter_2")] == ["observe"]


async def test_direct_messages_are_charged_to_the_team_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    await wired.call("crafter_1", "send_message", text="abc", to=["crafter_2"])
    await wired.call("crafter_1", "send_message", text="defg")
    scenario = wired.runtime.scenario
    assert isinstance(scenario, TextcraftSharedWorkspaceScenario)
    assert scenario.world.characters_used("workspace") == len("abc") + len("defg")


@pytest.mark.parametrize("to", [[], ["missing"], ["crafter_1"]])
async def test_an_invalid_recipient_does_not_publish_or_charge(
    monkeypatch: pytest.MonkeyPatch, to: list[str]
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    with pytest.raises(ModelRetry, match="teammate"):
        await wired.call("crafter_1", "send_message", text="Hello", to=to)
    assert wired.runtime.channel_router.get_history("workspace") == []


async def test_a_message_wakes_only_the_message_waits_that_can_see_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    registry = wired.runtime.wait_registry
    finished = registry.register(agent_id="crafter_3", wait_for=WaitFor.NEXT_ROUND, deadline_s=None)
    waiting = registry.register(agent_id="crafter_2", wait_for=WaitFor.MESSAGE, deadline_s=None)
    await wired.call("crafter_1", "send_message", text="Only for you", to=["crafter_3"])
    assert not finished.resumed and not waiting.resumed
    await wired.call("crafter_1", "send_message", text="Everyone reconsider")
    assert waiting.resumed
    assert not finished.resumed
    registry.cancel(wait=finished)


async def test_a_wait_registered_after_a_message_arrived_resumes_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    await wired.call("crafter_1", "send_message", text="Change the plan", to=["crafter_2"])
    wait = wired.runtime.wait_registry.register(
        agent_id="crafter_2", wait_for=WaitFor.MESSAGE, deadline_s=None
    )
    assert wait.resumed


async def test_workspace_agents_are_not_offered_the_channel_browsing_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    offered = wired.tools_of(agent_id="crafter_1")
    for tool_name in ("read_channel", "list_channels", "get_channel_members"):
        assert tool_name not in offered
        assert wired.runtime.is_base_tool_hidden(agent_id="crafter_1", tool_name=tool_name)
    assert {"send_message", "act", "observe", "read_notifications"} <= set(offered)


async def test_a_send_receipt_carries_teammates_messages_the_sender_had_not_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch)
    await wired.call("crafter_2", "send_message", text="I take column two")
    receipt = await wired.call("crafter_1", "send_message", text="I take column one")
    assert "I take column two" in receipt["workspace"]
    assert "I take column one" not in receipt["workspace"]
    assert "I take column two" not in await wired.call("crafter_1", "observe")
