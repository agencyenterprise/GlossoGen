"""A floor call that waited on the scenario's lock past the end of its round lands nothing.

The tool executors are called directly against a real runtime, so the order of
the calls is the test's. operator_b's action is held inside the lock by the event
logger while the round's end and then operator_a's call queue on the lock behind
it. No test waits on a duration. ``lockstep`` is off so a held action cannot wait
on the other operator.
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from glossogen.models.event import SimulationEvent
from glossogen.models.wait_for import WaitFor
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.event_bus import EventBus
from glossogen.runtime.event_logger import EventLogger
from glossogen.runtime.notification_payload import NotificationInbox, Wake
from glossogen.runtime.round_end_trigger import RoundEndTrigger
from glossogen.runtime.scenario_world import WorldContext
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.runtime.wait_registry import WakeReason
from glossogen.scenario_contract.event_types import loggable_event_types
from glossogen.scenarios.move_a_box.events import MoveABoxActionTaken, MoveABoxOperatorFinished
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B, Direction, HaulMethod
from glossogen.scenarios.move_a_box.planned_action import CrateAction, PlannedStep
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario
from tests.scenarios.move_a_box.move_a_box_play import BATCHED_ROUND, ONE_ROUND, build

pytestmark = pytest.mark.xdist_group("move_a_box")

ENDED = "Round 1 ended after 0 of 1 actions landed. Call read_notifications(wait_for='next_round')."

ToolExecutors = dict[str, Callable[..., Awaitable[str]]]
FloorCall = Callable[[ToolExecutors, str], Coroutine[Any, Any, str]]


class HeldLogger(EventLogger):
    """Keeps logged events in memory and holds the first action logged until let through."""

    def __init__(self, log_path: Path) -> None:
        super().__init__(
            log_path=log_path,
            event_bus=EventBus(max_queue_size=100),
            allowed_event_types=loggable_event_types(scenario_cls=MoveABoxScenario),
        )
        self.events: list[SimulationEvent] = []
        self.holding = asyncio.Event()
        self.let_through = asyncio.Event()

    async def log(self, event: SimulationEvent) -> None:
        self.events.append(event)
        if isinstance(event, MoveABoxActionTaken) and not self.let_through.is_set():
            self.holding.set()
            await self.let_through.wait()


class Floor(NamedTuple):
    """A round both operators have read the briefing of, and the tools they call."""

    scenario: MoveABoxScenario
    runtime: SimulationRuntime
    logger: HeldLogger
    tools: ToolExecutors


async def briefed_round(overrides: dict[str, Any], tmp_path: Path) -> Floor:
    """Round 1 started, every operator briefed and its model request issued in round 1."""
    scenario = build(preset_name="knobs_default", overrides=overrides)
    agents = scenario.get_agents(default_model="scripted-model", default_provider="anthropic")
    sessions = {agent.agent_id: AgentSession(agent_id=agent.agent_id) for agent in agents}
    logger = HeldLogger(log_path=tmp_path / "events.jsonl")
    runtime = SimulationRuntime(
        scenario=scenario,
        channels=scenario.get_channels(),
        event_logger=logger,
        agent_sessions=sessions,
        agent_tool_allowlists={agent.agent_id: frozenset(agent.tool_names) for agent in agents},
        world_context=WorldContext(agent_sessions=sessions, event_logger=logger),
        agent_configs=agents,
        simulation_start_time=datetime.now(tz=UTC),
    )
    scenario.bind_runtime(runtime=runtime)
    await scenario.on_round_advanced(round_number=1)
    await runtime.deliver_round_injections(round_number=1)
    for agent in agents:
        scenario.on_model_request_started(agent_id=agent.agent_id)
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
    tools = {tool.name: tool.executor for tool in scenario.get_tools()}
    return Floor(scenario=scenario, runtime=runtime, logger=logger, tools=tools)


async def act_stand_by(tools: ToolExecutors, agent_id: str) -> str:
    return await tools["act"](
        agent_id=agent_id,
        steps=[PlannedStep(action=CrateAction.STAND_BY, direction=None)],
        reasoning="Scripted list.",
    )


async def stand_by(tools: ToolExecutors, agent_id: str) -> str:
    return await tools["stand_by"](agent_id=agent_id, reasoning="Scripted stand by.")


async def haul(tools: ToolExecutors, agent_id: str) -> str:
    return await tools["haul"](
        agent_id=agent_id,
        method=HaulMethod.CART,
        direction=Direction.RIGHT,
        reasoning="Scripted haul.",
    )


async def finish(tools: ToolExecutors, agent_id: str) -> str:
    return await tools["finish"](agent_id=agent_id, reasoning="Scripted finish.")


class QueuedCall(NamedTuple):
    """operator_b's action that holds the lock, and operator_a's call queued behind the end."""

    overrides: dict[str, Any]
    holding: FloorCall
    queued: FloorCall


QUEUED_CALLS = {
    "act": QueuedCall(overrides=BATCHED_ROUND, holding=act_stand_by, queued=act_stand_by),
    "haul": QueuedCall(overrides=ONE_ROUND, holding=stand_by, queued=haul),
    "finish": QueuedCall(overrides=ONE_ROUND, holding=stand_by, queued=finish),
}


async def queued_behind_round_end(
    floor: Floor, call: QueuedCall, end_round: Callable[[], Coroutine[Any, Any, None]]
) -> str:
    """operator_a's result when its call reached the lock after ``end_round`` did.

    Each ``asyncio.sleep(0)`` lets the task just started run to the lock, where it
    queues, since nothing before the lock in either call suspends.
    """
    holder = asyncio.create_task(call.holding(floor.tools, OPERATOR_B))
    await floor.logger.holding.wait()
    ending = asyncio.create_task(end_round())
    await asyncio.sleep(0)
    caller = asyncio.create_task(call.queued(floor.tools, OPERATOR_A))
    await asyncio.sleep(0)
    floor.logger.let_through.set()
    result, _, _ = await asyncio.gather(caller, ending, holder)
    return result


def landed_for(floor: Floor, agent_id: str) -> list[SimulationEvent]:
    """Every action and finish logged for ``agent_id``."""
    return [
        event
        for event in floor.logger.events
        if isinstance(event, (MoveABoxActionTaken, MoveABoxOperatorFinished))
        and event.agent_id == agent_id
    ]


@pytest.mark.parametrize("tool", sorted(QUEUED_CALLS))
async def test_a_call_queued_while_the_round_resolves_lands_nothing(
    tool: str, tmp_path: Path
) -> None:
    call = QUEUED_CALLS[tool]
    floor = await briefed_round(overrides={**call.overrides, "lockstep": False}, tmp_path=tmp_path)

    async def end_round_one() -> None:
        await floor.scenario.on_round_ended(round_number=1, trigger=RoundEndTrigger.ROUND_TIMEOUT)

    result = await queued_behind_round_end(floor=floor, call=call, end_round=end_round_one)

    assert result == ENDED
    assert landed_for(floor=floor, agent_id=OPERATOR_A) == []
    assert len(landed_for(floor=floor, agent_id=OPERATOR_B)) == 1


@pytest.mark.parametrize("tool", sorted(QUEUED_CALLS))
async def test_a_call_queued_until_the_next_round_started_lands_nothing_in_it(
    tool: str, tmp_path: Path
) -> None:
    call = QUEUED_CALLS[tool]
    overrides = {**call.overrides, "lockstep": False, "round_count": 2}
    floor = await briefed_round(overrides=overrides, tmp_path=tmp_path)

    async def end_round_one_and_start_round_two() -> None:
        await floor.scenario.on_round_ended(round_number=1, trigger=RoundEndTrigger.ROUND_TIMEOUT)
        floor.runtime.set_current_round(round_number=2)
        await floor.scenario.on_round_advanced(round_number=2)

    result = await queued_behind_round_end(
        floor=floor, call=call, end_round=end_round_one_and_start_round_two
    )

    assert result == ENDED
    assert landed_for(floor=floor, agent_id=OPERATOR_A) == []
    assert floor.scenario.get_world().steps_used(agent_id=OPERATOR_A) == 0
