"""``move`` and ``observe`` called directly against a real runtime.

The tool functions are called as the runner builds them for each player, so the
order of calls is the test's, not the scheduler's. A logger that holds one move
open lets a test make the partner's call while that move is still applying.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic_ai import ModelRetry

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


async def test_a_move_made_while_the_partner_moves_reports_its_steps_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """player_a's events are held mid-log; player_b's move still sees player_a's whole call.

    A move is applied in one synchronous step, so player_b's result lists all of
    player_a's steps, and its own event waits until player_a's are logged.
    """
    wired = await wire(monkeypatch=monkeypatch, overrides={})
    a_call = asyncio.create_task(wired.move(PLAYER_A, ["right", "left", "down"]))
    holding = asyncio.create_task(wired.logger.holding.wait())
    await asyncio.wait({a_call, holding}, return_when=asyncio.FIRST_COMPLETED)
    assert not a_call.done(), "player_a's move finished without being held"
    b_call = asyncio.create_task(wired.move(PLAYER_B, ["down"]))
    for _ in range(10):
        await asyncio.sleep(0)
    assert not b_call.done()

    wired.logger.release.set()
    _, b_view = await asyncio.gather(a_call, b_call)

    assert "You moved (your action 1): [down] -> row 2, col 1." in b_view
    assert "1 - [right, left, down] -> row 2, col 1" in b_view
    logged = [
        (event.agent_id, event.sequence)
        for event in wired.logger.events
        if isinstance(event, SignalGameMoveMade)
    ]
    assert logged == [(PLAYER_A, 1), (PLAYER_A, 2), (PLAYER_A, 3), (PLAYER_B, 4)]


async def test_observe_shows_the_whole_round_spends_no_move_and_reports_both_observing(
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
        assert "1 - [right] -> row 1, col 2" in view and "2 - [left] -> row 1, col 1" in view
    assert "both observing" not in observed
    assert wired.scenario.get_world().moves_left(agent_id=PLAYER_B) == 199
    assert "You are both observing" in await wired.call(PLAYER_A, "observe")
    after = await wired.move(PLAYER_B, ["right"])
    assert "No new actions by your partner." in after
    assert "both observing" not in await wired.call(PLAYER_A, "observe")
    assert [move.direction for move in wired.moves_of(agent_id=PLAYER_B)] == ["down", "right"]


async def test_turns_refuse_a_second_move_and_a_move_made_without_seeing_the_partner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wired = await wire(monkeypatch=monkeypatch, overrides={"turn_based": True})
    wired.logger.holding.set()

    assert "It is your partner's turn." in await wired.move(PLAYER_A, ["right"])
    with pytest.raises(ModelRetry, match="It is your partner's turn"):
        await wired.move(PLAYER_A, ["down"])
    with pytest.raises(ModelRetry) as unseen:
        await wired.move(PLAYER_B, ["down"])
    assert "Nothing was moved: your partner acted since you last looked." in str(unseen.value)
    assert "1 - [right] -> row 1, col 2" in str(unseen.value)
    assert "It is your turn." in str(unseen.value)
    assert "It is your partner's turn." in await wired.move(PLAYER_B, ["down"])
    with pytest.raises(ModelRetry, match="1 - \\[down\\] -> row 2, col 1"):
        await wired.move(PLAYER_A, ["left"])
    await wired.move(PLAYER_A, ["left"])

    assert [move.direction for move in wired.moves_of(agent_id=PLAYER_A)] == ["right", "left"]
    assert [move.direction for move in wired.moves_of(agent_id=PLAYER_B)] == ["down"]


def test_observe_and_turns_are_described_only_when_enabled() -> None:
    for enabled in (False, True):
        scenario = build(
            preset_name="knobs_default",
            overrides={"observe_enabled": enabled, "turn_based": enabled},
        )
        agents = scenario.get_agents(default_model="test", default_provider="anthropic")
        suffix = scenario.runner_prompts(agent_id=PLAYER_A)
        assert suffix is not None
        for agent in agents:
            assert ("observe" in agent.tool_names) is enabled
            assert ("take turns" in agent.system_prompt) is enabled
        assert ("observe()" in suffix.system_suffix) is enabled
        assert ("One move call is one turn." in suffix.system_suffix) is enabled


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
    assert move.input_schema["$defs"]["Direction"]["enum"] == ["up", "down", "left", "right"]
    assert move.input_schema["additionalProperties"] is False


def test_no_prompt_states_the_round_count_move_budget_or_time_limit() -> None:
    scenario = build(
        preset_name="knobs_default",
        overrides={"round_count": 7, "moves_per_round": 77, "max_round_duration_seconds": 777},
    )
    [agent, _] = scenario.get_agents(default_model="test", default_provider="anthropic")
    briefing = scenario.get_injection(round_number=1, agent_id=PLAYER_A)
    for text in (agent.system_prompt, briefing):
        assert "7" not in text
        assert " OF " not in text


def test_the_prompts_wait_for_the_partner_with_a_message_wait() -> None:
    """A plain read_notifications() is named only for the round briefing."""
    scenario = build(preset_name="knobs_default", overrides={"turn_based": True})
    [agent, _] = scenario.get_agents(default_model="test", default_provider="anthropic")
    prompts = scenario.runner_prompts(agent_id=PLAYER_A)
    assert prompts is not None
    for text in (agent.system_prompt, prompts.system_suffix, prompts.initial, prompts.continuation):
        assert 'read_notifications(wait_for="message")' in text
    assert "read_notifications(): after startup" not in prompts.system_suffix
    assert "read_notifications() before you move again" not in agent.system_prompt
