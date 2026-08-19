"""A finished runner marks the session it belonged to, and only that one.

`AgentSession.mark_runner_finished` is the clock's answer to "will this agent take
another turn?", and it is wired as a done callback on the runner's task because
that task is the one thing that knows every way a runner can stop.

The subtle half is which session gets marked. A mid-run swap replaces the session
while the outgoing runner is still settling: `execute_agent_swap` drains the old
task and then installs the new session, and done callbacks run through
`call_soon`, so there is no fixed order between the callback and the replacement.
A callback that resolved the agent id when it ran could therefore mark the
incoming session finished, and the clock would treat an agent that had only just
started as one that would never speak again.

The callback is bound to the session instead, which is what the last test pins:
one agent id, two sessions, and the mark lands on the one the callback was given.
Order stops mattering once that holds.
"""

import asyncio

import pytest

from glossogen.runtime.agent_session import AgentSession

AGENT_ID = "field_observer"


async def settle() -> None:
    """Yield once so `call_soon` callbacks run.

    Not a wait: `add_done_callback` schedules on the next loop iteration, so one
    yield is the whole requirement. There is no duration here to race.
    """
    await asyncio.sleep(0)


def watched_session(agent_id: str) -> AgentSession:
    """A session that has not yet heard from its runner."""
    session = AgentSession(agent_id=agent_id)
    assert not session.runner_finished
    return session


async def test_a_runner_that_returns_marks_its_session() -> None:
    """The ordinary end: the runner hits its turn cap and returns."""
    session = watched_session(agent_id=AGENT_ID)

    async def runner() -> str:
        return "done"

    task = asyncio.create_task(runner())
    task.add_done_callback(session.mark_runner_finished)
    await task
    await settle()

    assert session.runner_finished


async def test_a_runner_that_raises_marks_its_session() -> None:
    """A failed runner takes no more turns either, so the clock hears the same thing."""
    session = watched_session(agent_id=AGENT_ID)

    async def runner() -> None:
        raise RuntimeError("provider gave up")

    task = asyncio.create_task(runner())
    task.add_done_callback(session.mark_runner_finished)
    with pytest.raises(RuntimeError):
        await task
    await settle()

    assert session.runner_finished


async def test_a_cancelled_runner_marks_its_session() -> None:
    """The swap's force-cancel path, which fires when a drained runner will not exit."""
    session = watched_session(agent_id=AGENT_ID)
    started = asyncio.Event()

    async def runner() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(runner())
    task.add_done_callback(session.mark_runner_finished)
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await settle()

    assert session.runner_finished


async def test_a_replaced_session_does_not_inherit_its_predecessors_mark() -> None:
    """The swap hazard: the outgoing runner must not mark the incoming session.

    Both sessions carry the same agent id, as they do through a swap, so the only
    thing distinguishing them is which one the callback was handed. That is the
    property the swap needs, and it is what makes the callback's timing irrelevant.
    """
    outgoing = watched_session(agent_id=AGENT_ID)
    incoming = watched_session(agent_id=AGENT_ID)

    async def runner() -> None:
        return None

    task = asyncio.create_task(runner())
    task.add_done_callback(outgoing.mark_runner_finished)
    await task
    await settle()

    assert outgoing.runner_finished
    assert not incoming.runner_finished
