"""``move`` and ``observe`` called directly against a real runtime.

The tool functions are called as the runner builds them for each player, so the
order of calls is the test's, not the scheduler's. A logger that holds one move
open lets a test make the partner's call while that move is still applying.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from glossogen.llm.token_counter import TokenCounter
from glossogen.runners.agent_tools import build_agent_tools, list_tool_definitions
from glossogen.runners.read_notifications_tool import RunTermination
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.notification_payload import NotificationInbox, Wake
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenarios.signal_game.events import SignalGameMoveMade
from glossogen.scenarios.signal_game.ids import (
    MAX_MOVES_PER_CALL,
    PLAYER_A,
    PLAYER_B,
    Direction,
)
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from tests.scenarios.signal_game.signal_game_play import ONE_ROUND, build

pytestmark = pytest.mark.xdist_group("signal_game")


class HoldingLogger:
    """Keeps logged events, and holds player_a's first move until released."""

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.holding = asyncio.Event()
        self.release = asyncio.Event()

    async def log(self, event: Any) -> None:
        self.events.append(event)
        if (
            isinstance(event, SignalGameMoveMade)
            and event.agent_id == PLAYER_A
            and not self.holding.is_set()
        ):
            self.holding.set()
            await self.release.wait()


class WordCounter(TokenCounter):
    """Counts words, so no provider is contacted."""

    async def _count_impl(self, text: str) -> int:
        return len(text.split())


def local_token_counter(provider: str, model: str) -> TokenCounter:
    """Stand in for the provider-backed counter."""
    _ = provider, model
    return WordCounter()


class Wired:
    """An open, briefed round of signal_game, with each player's tools built on demand."""

    def __init__(
        self, scenario: SignalGameScenario, logger: HoldingLogger, runtime: SimulationRuntime
    ) -> None:
        self.scenario = scenario
        self.logger = logger
        self.runtime = runtime

    async def call(self, agent_id: str, tool_name: str, **arguments: Any) -> str:
        tools = build_agent_tools(
            runtime=self.runtime, agent_id=agent_id, termination=RunTermination()
        )
        [tool] = [tool for tool in tools if tool.name == tool_name]
        return await tool.function(**arguments)  # pyright: ignore[reportCallIssue]

    async def move(self, agent_id: str, directions: list[str]) -> str:
        """``move`` with the arguments pydantic-ai would have validated into directions."""
        return await self.call(
            agent_id, "move", directions=[Direction(direction) for direction in directions]
        )

    def moves_of(self, agent_id: str) -> list[SignalGameMoveMade]:
        return [
            event
            for event in self.logger.events
            if isinstance(event, SignalGameMoveMade) and event.agent_id == agent_id
        ]


async def wire(monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any]) -> Wired:
    monkeypatch.setattr(
        "glossogen.runtime.simulation_state.create_token_counter", local_token_counter
    )
    scenario = build(preset_name="knobs_default", overrides={**ONE_ROUND, **overrides})
    agents = scenario.get_agents(default_model="test", default_provider="anthropic")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    logger = HoldingLogger()
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
    await runtime.deliver_round_injections(round_number=1)
    for agent in agents:
        await scenario.read_notifications(
            agent_id=agent.agent_id,
            wake=Wake(
                wait_for=WaitFor.ANY,
                reasons=[WakeReason.NEW_NOTIFICATION],
                waited_seconds=0.0,
                inbox=NotificationInbox(
                    session=sessions[agent.agent_id], channel_router=runtime.channel_router
                ),
                terminated=False,
                done_reason="",
                release_detail="",
            ),
        )
    return Wired(scenario=scenario, logger=logger, runtime=runtime)


async def test_a_move_made_while_the_partner_moves_waits_and_reports_its_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    a_call = asyncio.create_task(wired.move(PLAYER_A, ["right", "left", "stay"]))
    holding = asyncio.create_task(wired.logger.holding.wait())
    await asyncio.wait({a_call, holding}, return_when=asyncio.FIRST_COMPLETED)
    assert not a_call.done(), "player_a's move finished without being held"
    b_call = asyncio.create_task(wired.move(PLAYER_B, ["down"]))
    for _ in range(10):
        await asyncio.sleep(0)
    assert not b_call.done()

    wired.logger.release.set()
    _, b_view = await asyncio.gather(a_call, b_call)

    assert "You moved: down (#4)." in b_view
    for line in ("#1 right", "#2 left", "#3 stay"):
        assert line in b_view, line
    assert [move.sequence for move in wired.moves_of(agent_id=PLAYER_B)] == [4]


async def test_observe_shows_the_whole_round_and_spends_no_move(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={"observe_enabled": True})
    wired.logger.holding.set()
    assert "Your partner has not acted this round." in await wired.call(PLAYER_B, "observe")

    await wired.move(PLAYER_A, ["right"])
    await wired.move(PLAYER_B, ["down"])
    await wired.move(PLAYER_A, ["left"])
    observed = await wired.call(PLAYER_B, "observe")
    observed_again = await wired.call(PLAYER_B, "observe")

    for view in (observed, observed_again):
        assert "Your partner's actions this round" in view
        assert "#1 right" in view and "#3 left" in view
        assert "199 move(s) left" in view
    after = await wired.move(PLAYER_B, ["stay"])
    assert "No new actions by your partner." in after
    a_view = await wired.move(PLAYER_A, ["stay"])
    assert "observe" not in a_view
    assert [move.direction for move in wired.moves_of(agent_id=PLAYER_B)] == ["down", "stay"]


def test_observe_is_offered_only_when_enabled() -> None:
    for enabled in (False, True):
        scenario = build(preset_name="knobs_default", overrides={"observe_enabled": enabled})
        agents = scenario.get_agents(default_model="test", default_provider="anthropic")
        suffix = scenario.runner_prompts(agent_id=PLAYER_A)
        assert suffix is not None
        for agent in agents:
            assert ("observe" in agent.tool_names) is enabled
        assert ("observe()" in suffix.system_suffix) is enabled


async def test_the_move_schema_bounds_the_batch_and_names_each_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    [move] = [
        definition
        for definition in list_tool_definitions(runtime=wired.runtime)
        if definition.name == "move"
    ]
    directions = move.input_schema["properties"]["directions"]
    assert directions["minItems"] == 1
    assert directions["maxItems"] == MAX_MOVES_PER_CALL
    assert move.input_schema["$defs"]["Direction"]["enum"] == [
        "up",
        "down",
        "left",
        "right",
        "stay",
    ]
    assert move.input_schema["additionalProperties"] is False
