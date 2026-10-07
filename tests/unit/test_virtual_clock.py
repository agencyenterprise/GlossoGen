"""The virtual clock: responses run in simulated-latency order, not arrival order."""

import asyncio

import pytest

from glossogen.channel_router import ChannelRouter
from glossogen.models.channel import Channel
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.virtual_clock import StepTiming, VirtualClock, VirtualClockConfig
from glossogen.runtime.wait_registry import WaitRegistry, WakeReason

# One second of overhead plus a tenth of a second per output token.
CONFIG = VirtualClockConfig(base_latency_s=1.0, output_tokens_per_second=10.0)


async def settle() -> None:
    """Let every ready task run until it blocks again."""
    for _ in range(5):
        await asyncio.sleep(0)


def respond(clock: VirtualClock, agent_id: str, tokens: int) -> asyncio.Task[StepTiming]:
    return asyncio.create_task(clock.complete_inference(agent_id=agent_id, output_tokens=tokens))


def test_latency_counts_only_the_requests_own_output_tokens():
    assert CONFIG.latency_s(output_tokens=20) == 3.0
    assert CONFIG.minimum_latency_s == 1.0
    with pytest.raises(ValueError):
        VirtualClockConfig(base_latency_s=-1, output_tokens_per_second=1)
    with pytest.raises(ValueError):
        VirtualClockConfig(base_latency_s=0, output_tokens_per_second=0)


async def test_a_short_response_that_arrives_later_still_acts_first():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    slow = respond(clock, "b", tokens=100)  # back first in real time, ends at 11.0
    await settle()
    assert not slow.done(), "a is still thinking and could finish before 11.0"
    fast = respond(clock, "a", tokens=5)  # ends at 1.5
    await settle()
    assert fast.done() and not slow.done()
    assert fast.result() == StepTiming(started_at=0.0, completed_at=1.5)
    assert clock.time() == 1.5
    # a's next request starts at 1.5; it could still end before b does.
    clock.begin_inference(agent_id="a")
    await settle()
    assert not slow.done()
    clock.park(agent_id="a")
    await settle()
    assert slow.done()
    assert clock.time() == 11.0


async def test_only_one_released_agent_executes_at_a_time():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    first = respond(clock, "a", tokens=10)
    second = respond(clock, "b", tokens=10)  # same instant; ties go by agent id
    await settle()
    assert first.done() and not second.done()
    clock.park(agent_id="a")
    await settle()
    assert second.done()
    assert clock.time() == 2.0


async def test_a_woken_agent_starts_its_request_at_the_waking_instant():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    clock.park(agent_id="b")
    released = respond(clock, "a", tokens=10)
    await settle()
    assert released.done() and clock.time() == 2.0
    clock.wake(agent_id="b")  # a's message woke b at 2.0
    clock.park(agent_id="a")
    reply = respond(clock, "b", tokens=5)
    await settle()
    assert reply.result() == StepTiming(started_at=2.0, completed_at=3.5)


async def test_timers_fire_in_virtual_order_before_later_responses():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    fired: list[float] = []
    clock.schedule_timer(5.0, lambda: fired.append(clock.time()))
    clock.park(agent_id="a")
    late = respond(clock, "b", tokens=90)  # ends at 10.0
    await settle()
    assert fired == [5.0]
    assert late.done() and clock.time() == 10.0
    cancelled: list[float] = []
    cancel = clock.schedule_timer(1.0, lambda: cancelled.append(clock.time()))
    cancel()
    clock.park(agent_id="b")
    assert cancelled == []


async def test_starting_a_round_restarts_the_round_elapsed_time():
    clock = VirtualClock(config=CONFIG, agent_ids=["a"])
    first = respond(clock, "a", tokens=90)  # ends at 10.0
    await settle()
    assert first.done() and clock.round_elapsed_s() == 10.0
    clock.start_round()
    assert clock.round_elapsed_s() == 0.0 and clock.time() == 10.0


async def test_retiring_or_stopping_releases_what_would_otherwise_hang():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b", "c"])
    blocked = respond(clock, "b", tokens=10)
    await settle()
    assert not blocked.done()
    clock.retire(agent_id="a")
    await settle()
    assert not blocked.done(), "c is still inferring"
    clock.stop()
    await settle()
    assert blocked.done()
    after = await clock.complete_inference(agent_id="c", output_tokens=1)
    assert after.completed_at == pytest.approx(1.1)


async def test_a_response_reporting_no_tokens_is_not_overtaken():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    one_token = respond(clock, "b", tokens=1)  # ends at 1.1
    await settle()
    assert not one_token.done(), "a could report no usage and end at 1.0"
    no_usage = respond(clock, "a", tokens=0)  # ends at 1.0
    await settle()
    assert no_usage.done() and not one_token.done()
    assert no_usage.result().completed_at == 1.0


async def test_stopping_moves_time_to_the_latest_released_completion():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    held = respond(clock, "a", tokens=100)  # ends at 11.0, held while b infers
    await settle()
    assert not held.done()
    clock.stop()
    await settle()
    assert held.result().completed_at == 11.0
    assert clock.time() == 11.0
    clock.begin_inference(agent_id="a")
    after = await clock.complete_inference(agent_id="a", output_tokens=0)
    assert after == StepTiming(started_at=11.0, completed_at=12.0)


async def test_a_seat_enlisted_after_its_runner_retired_is_scheduled_again():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    clock.retire(agent_id="a")  # a swap drained the old runner
    clock.enlist(agent_id="a")  # and started a new one on the same seat
    slow = respond(clock, "b", tokens=100)  # ends at 11.0
    await settle()
    assert not slow.done(), "the new runner could finish before 11.0"
    fast = respond(clock, "a", tokens=5)
    await settle()
    assert fast.result() == StepTiming(started_at=0.0, completed_at=1.5)
    assert not slow.done()
    clock.enlist(agent_id="a")  # a seat that is not retired is left as it is
    clock.park(agent_id="a")
    await settle()
    assert slow.done() and clock.time() == 11.0


async def test_registry_deadlines_and_waited_time_are_virtual():
    router = ChannelRouter(
        channels=[Channel(channel_id="workspace", name="workspace", member_agent_ids=["a", "b"])]
    )
    sessions = {agent_id: AgentSession(agent_id=agent_id) for agent_id in ("a", "b")}
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    registry = WaitRegistry(
        channel_router=router,
        agent_sessions=sessions,
        current_round=lambda: 1,
        schedule_timer=clock.schedule_timer,
        clock=clock.time,
        on_park=clock.park,
        on_resume=clock.wake,
    )
    long_think = respond(clock, "b", tokens=400)  # ends at 41.0
    first = respond(clock, "a", tokens=10)  # a acts at 2.0
    await settle()
    assert first.done() and not long_think.done()
    wait = registry.register(
        agent_id="a", round_id=1, kind="message", deadline_s=30.0, implicit=False
    )
    signal = await registry.wait_for_resume(wait=wait)
    assert signal.reasons == [WakeReason.DEADLINE]
    assert signal.waited_seconds == 30.0
    assert not long_think.done(), "a woke at 32.0 and could act before 41.0"
    clock.park(agent_id="a")
    await settle()
    assert long_think.done() and clock.time() == 41.0


async def test_an_occupied_agent_lets_teammates_act_and_resumes_after_its_duration():
    clock = VirtualClock(config=CONFIG, agent_ids=["a", "b"])
    a_turn = respond(clock, "a", tokens=10)  # ends at 2.0
    b_turn = respond(clock, "b", tokens=30)  # ends at 4.0
    await settle()
    assert a_turn.done() and not b_turn.done()
    busy = asyncio.create_task(clock.occupy(agent_id="a", duration_s=10.0))
    await settle()
    assert b_turn.done() and not busy.done(), "b acts at 4.0 while a's craft runs"
    assert clock.time() == 4.0
    clock.begin_inference(agent_id="b")
    b_next = respond(clock, "b", tokens=150)  # starts at 4.0, ends at 20.0
    await settle()
    assert busy.done() and not b_next.done()
    assert clock.time() == 12.0
    clock.park(agent_id="a")
    await settle()
    assert b_next.done()
    assert clock.time() == 20.0


async def test_stopping_ends_an_occupied_interval():
    clock = VirtualClock(config=CONFIG, agent_ids=["a"])
    await respond(clock, "a", tokens=10)
    busy = asyncio.create_task(clock.occupy(agent_id="a", duration_s=30.0))
    await settle()
    assert busy.done(), "nobody else can act, so the timer fires at once"
    assert clock.time() == 32.0
    clock.begin_inference(agent_id="a")
    await respond(clock, "a", tokens=10)
    stalled = asyncio.create_task(clock.occupy(agent_id="a", duration_s=30.0))
    clock.stop()
    await settle()
    assert stalled.done()
