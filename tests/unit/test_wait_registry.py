"""The wait registry: conditions are read from the queue, and each wait resumes once."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from glossogen.channel_router import ChannelRouter
from glossogen.models.channel import Channel
from glossogen.models.message import SimulationMessage
from glossogen.runtime.activity_notification import (
    DoneNotification,
    NewInfoNotification,
    NewMessagesNotification,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.notification_payload import NotificationInbox
from glossogen.runtime.wait_for import WaitFor
from glossogen.runtime.wait_registry import (
    DEFAULT_ANY_TIMEOUT_SECONDS,
    WaitRegistry,
    WakeReason,
    wait_deadline,
)

CHANNEL = "link"


class ManualTimer:
    """A timer the test fires by hand, so no test waits for real time."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[str, float, Callable[[], None]]] = []
        self.cancelled = 0

    def schedule(
        self, agent_id: str, timeout_s: float, fire: Callable[[], None]
    ) -> Callable[[], None]:
        self.scheduled.append((agent_id, timeout_s, fire))

        def cancel() -> None:
            self.cancelled += 1

        return cancel

    def fire_all(self) -> None:
        for _agent_id, _timeout_s, fire in list(self.scheduled):
            fire()


class Fixture:
    """One channel, two sessions, and a registry over them with a hand-driven clock."""

    def __init__(self) -> None:
        self.router = ChannelRouter(
            channels=[Channel(channel_id=CHANNEL, name="link", member_agent_ids=["a", "b"])]
        )
        self.sessions = {"a": AgentSession(agent_id="a"), "b": AgentSession(agent_id="b")}
        self.timer = ManualTimer()
        self.now = 100.0
        self.parked: list[str] = []
        self.resumed: list[str] = []
        self.registry = WaitRegistry(
            channel_router=self.router,
            session_for=lambda agent_id: self.sessions[agent_id],
            schedule_wait_timeout=self.timer.schedule,
            clock=lambda: self.now,
            on_park=self.parked.append,
            on_resume=self.resumed.append,
        )

    def post_from_b(self, text: str) -> None:
        """Append a message from ``b`` and tell ``a``, as ``send_message`` does."""
        self.router.append_message(
            message=SimulationMessage(
                message_id=f"m{self.router.get_message_count(channel_id=CHANNEL) + 1}",
                channel_id=CHANNEL,
                sender_agent_id="b",
                sender_display_name="b",
                text=text,
                timestamp=datetime.now(tz=UTC),
                round_number=1,
            )
        )
        self.sessions["a"].push_notification(
            notification=NewMessagesNotification(channels=[CHANNEL])
        )


async def test_an_any_wait_resumes_at_once_when_a_notification_is_already_queued() -> None:
    fixture = Fixture()
    fixture.sessions["a"].push_notification(
        notification=NewInfoNotification(text="briefing", kind="injection")
    )
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.ANY, deadline_s=None)
    signal = await wait.future
    assert signal.reasons == [WakeReason.NEW_NOTIFICATION]
    assert fixture.parked == []


async def test_an_any_wait_resumes_on_a_later_notification() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.ANY, deadline_s=None)
    assert fixture.registry.pending_wait(agent_id="a") is wait
    fixture.sessions["a"].push_notification(
        notification=NewInfoNotification(text="budget at 75%", kind="world")
    )
    signal = await wait.future
    assert signal.reasons == [WakeReason.NEW_NOTIFICATION]
    assert fixture.registry.pending_wait(agent_id="a") is None
    assert fixture.parked == ["a"]
    assert fixture.resumed == ["a"]


async def test_a_message_wait_ignores_world_info_and_resumes_on_a_message() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.MESSAGE, deadline_s=None)
    fixture.sessions["a"].push_notification(
        notification=NewInfoNotification(text="budget at 75%", kind="world")
    )
    assert not wait.resumed
    fixture.post_from_b(text="column one is mine")
    signal = await wait.future
    assert signal.reasons == [WakeReason.NEW_MESSAGE]


async def test_a_message_wait_resumes_on_the_next_injection() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.MESSAGE, deadline_s=None)
    fixture.sessions["a"].push_notification(
        notification=NewInfoNotification(text="round 2", kind="injection")
    )
    signal = await wait.future
    assert signal.reasons == [WakeReason.NEXT_ROUND]


async def test_a_next_round_wait_ignores_messages_and_resumes_on_the_next_injection() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.NEXT_ROUND, deadline_s=None)
    fixture.post_from_b(text="are you there")
    assert not wait.resumed
    fixture.sessions["a"].push_notification(
        notification=NewInfoNotification(text="round 2", kind="injection")
    )
    signal = await wait.future
    assert signal.reasons == [WakeReason.NEXT_ROUND]


async def test_a_notice_for_messages_already_read_is_dropped_and_wakes_nothing() -> None:
    fixture = Fixture()
    fixture.post_from_b(text="hello")
    fixture.sessions["a"].record_channel_read(channel_id=CHANNEL, message_count=1)
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.ANY, deadline_s=None)
    assert not wait.resumed
    assert fixture.sessions["a"].pending_notifications() == []


@pytest.mark.parametrize("wait_for", list(WaitFor))
async def test_done_resumes_every_kind_of_wait(wait_for: WaitFor) -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=wait_for, deadline_s=None)
    fixture.sessions["a"].push_notification(notification=DoneNotification(reason="run over"))
    signal = await wait.future
    assert WakeReason.DONE in signal.reasons


async def test_a_deadline_resumes_through_the_scenario_timer_and_reports_the_wait() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.MESSAGE, deadline_s=30.0)
    assert [(agent, seconds) for agent, seconds, _fire in fixture.timer.scheduled] == [("a", 30.0)]
    fixture.now = 130.0
    fixture.timer.fire_all()
    signal = await wait.future
    assert signal.reasons == [WakeReason.TIMEOUT]
    assert signal.waited_seconds == 30.0


async def test_a_wait_resumed_by_a_notification_cancels_its_timer() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.MESSAGE, deadline_s=30.0)
    fixture.post_from_b(text="done")
    await wait.future
    assert fixture.timer.cancelled == 1
    fixture.timer.fire_all()
    assert (await wait.future).reasons == [WakeReason.NEW_MESSAGE]


async def test_an_agent_holds_one_pending_wait_at_a_time() -> None:
    fixture = Fixture()
    fixture.registry.register(agent_id="a", wait_for=WaitFor.ANY, deadline_s=None)
    with pytest.raises(ValueError, match="already has a pending wait"):
        fixture.registry.register(agent_id="a", wait_for=WaitFor.ANY, deadline_s=None)


def test_any_takes_the_scenarios_default_and_the_others_have_none() -> None:
    default = DEFAULT_ANY_TIMEOUT_SECONDS
    assert wait_deadline(wait_for=WaitFor.ANY, timeout_s=None, default_any_timeout_s=default) == (
        default
    )
    assert wait_deadline(wait_for=WaitFor.ANY, timeout_s=None, default_any_timeout_s=None) is None
    assert (
        wait_deadline(wait_for=WaitFor.MESSAGE, timeout_s=None, default_any_timeout_s=default)
        is None
    )
    assert (
        wait_deadline(wait_for=WaitFor.NEXT_ROUND, timeout_s=5.0, default_any_timeout_s=default)
        == 5.0
    )


async def test_cancelling_a_parked_wait_removes_its_timer_and_listener_and_unparks() -> None:
    fixture = Fixture()
    wait = fixture.registry.register(agent_id="a", wait_for=WaitFor.MESSAGE, deadline_s=30.0)
    waiter = asyncio.ensure_future(wait.future)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert wait.future.cancelled()
    fixture.registry.cancel(wait=wait)
    assert fixture.timer.cancelled == 1
    assert fixture.resumed == ["a"]
    assert fixture.registry.pending_wait(agent_id="a") is None
    fixture.post_from_b(text="too late")
    assert fixture.resumed == ["a"]
    assert fixture.registry.register(
        agent_id="a", wait_for=WaitFor.MESSAGE, deadline_s=None
    ).future.done()


def test_taking_lifecycle_leaves_message_notices_and_read_positions_alone() -> None:
    fixture = Fixture()
    fixture.post_from_b(text="unread")
    briefing = NewInfoNotification(text="round 2", kind="injection")
    fixture.sessions["a"].push_notification(notification=briefing)
    inbox = NotificationInbox(session=fixture.sessions["a"], channel_router=fixture.router)
    assert inbox.take_lifecycle() == [briefing]
    assert fixture.sessions["a"].get_last_seen_count(channel_id=CHANNEL) == 0
    assert fixture.sessions["a"].pending_notifications() == [
        NewMessagesNotification(channels=[CHANNEL])
    ]
