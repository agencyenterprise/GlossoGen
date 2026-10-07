"""The wait registry: conditions are read from state, and each wait resumes once."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from glossogen.channel_router import ChannelRouter
from glossogen.models.channel import Channel
from glossogen.models.message import SimulationMessage
from glossogen.runtime.activity_notification import DoneNotification, NewInfoNotification
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.wait_registry import WaitRegistry, WakeReason

CHANNEL = "workspace"


class ManualTimer:
    """A timer the test fires by hand, so no test waits for real time."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[float, Callable[[], None]]] = []
        self.cancelled = 0

    def schedule(self, delay_seconds: float, callback: Callable[[], None]) -> Callable[[], None]:
        entry = (delay_seconds, callback)
        self.scheduled.append(entry)

        def cancel() -> None:
            self.cancelled += 1

        return cancel

    def fire_all(self) -> None:
        for _delay, callback in list(self.scheduled):
            callback()


class Fixture:
    """A router with one public channel, two sessions, and a registry over them."""

    def __init__(self) -> None:
        self.router = ChannelRouter(
            channels=[
                Channel(
                    channel_id=CHANNEL,
                    name="workspace",
                    member_agent_ids=["a", "b"],
                )
            ]
        )
        self.sessions = {"a": AgentSession(agent_id="a"), "b": AgentSession(agent_id="b")}
        self.round = 1
        self.timer = ManualTimer()
        self.now = 100.0
        self.registry = WaitRegistry(
            channel_router=self.router,
            agent_sessions=self.sessions,
            current_round=lambda: self.round,
            schedule_timer=self.timer.schedule,
            clock=lambda: self.now,
            on_park=None,
            on_resume=None,
        )

    def post(self, sender: str, text: str) -> None:
        self.router.append_message(
            message=SimulationMessage(
                message_id=f"m{self.router.get_message_count(channel_id=CHANNEL) + 1}",
                channel_id=CHANNEL,
                sender_agent_id=sender,
                sender_display_name=sender,
                text=text,
                timestamp=datetime.now(tz=UTC),
                round_number=self.round,
            )
        )
        self.registry.publish_channel_message(channel_id=CHANNEL)


async def test_a_message_that_landed_before_the_wait_resumes_it_at_registration():
    fixture = Fixture()
    fixture.post(sender="b", text="already here")
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=None,
        implicit=False,
    )
    assert wait.resumed
    signal = await fixture.registry.wait_for_resume(wait=wait)
    assert signal.reasons == [WakeReason.NEW_PUBLIC_MESSAGE]
    assert fixture.timer.scheduled == []
    # The resumed wait no longer counts as pending, so the agent can park again.
    fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="finish",
        deadline_s=None,
        implicit=False,
    )


async def test_a_message_posted_later_resumes_a_parked_wait_once():
    fixture = Fixture()
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=None,
        implicit=False,
    )
    assert not wait.resumed
    fixture.post(sender="b", text="first")
    fixture.post(sender="b", text="second")
    signal = await fixture.registry.wait_for_resume(wait=wait)
    assert signal.reasons == [WakeReason.NEW_PUBLIC_MESSAGE]


async def test_own_messages_do_not_wake_the_sender():
    fixture = Fixture()
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=None,
        implicit=False,
    )
    fixture.post(sender="a", text="mine")
    assert not wait.resumed
    fixture.post(sender="b", text="theirs")
    assert wait.resumed


async def test_lifecycle_notifications_resume_any_wait_through_the_session():
    fixture = Fixture()
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="finish",
        deadline_s=None,
        implicit=True,
    )
    fixture.sessions["a"].push_notification(notification=NewInfoNotification(text="card"))
    signal = await fixture.registry.wait_for_resume(wait=wait)
    assert signal.reasons == [WakeReason.LIFECYCLE]

    fixture.sessions["b"].push_notification(notification=DoneNotification(reason="over"))
    terminated = fixture.registry.register(
        agent_id="b",
        round_id=1,
        kind="finish",
        deadline_s=None,
        implicit=False,
    )
    assert terminated.resumed


async def test_deadline_fires_through_the_injected_timer_and_is_cancelled_on_wake():
    fixture = Fixture()
    fixture.now = 10.0
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=30.0,
        implicit=False,
    )
    assert [delay for delay, _ in fixture.timer.scheduled] == [30.0]
    fixture.now = 40.0
    fixture.timer.fire_all()
    signal = await fixture.registry.wait_for_resume(wait=wait)
    assert signal.reasons == [WakeReason.DEADLINE]
    assert signal.waited_seconds == 30.0

    woken = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=5.0,
        implicit=False,
    )
    cancelled_before = fixture.timer.cancelled
    fixture.post(sender="b", text="early")
    assert woken.resumed
    assert fixture.timer.cancelled == cancelled_before + 1
    # A deadline firing after the wake changes nothing.
    fixture.timer.fire_all()
    assert (await fixture.registry.wait_for_resume(wait=woken)).reasons == [
        WakeReason.NEW_PUBLIC_MESSAGE
    ]


async def test_messages_from_another_round_do_not_resume_a_wait():
    fixture = Fixture()
    fixture.round = 2
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=None,
        implicit=False,
    )
    fixture.post(sender="b", text="new round chatter")
    assert not wait.resumed
    fixture.sessions["a"].push_notification(notification=NewInfoNotification(text="round 2"))
    assert wait.resumed


async def test_an_agent_holds_at_most_one_pending_wait():
    fixture = Fixture()
    fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=None,
        implicit=False,
    )
    with pytest.raises(ValueError, match="already has a pending wait"):
        fixture.registry.register(
            agent_id="a",
            round_id=1,
            kind="message",
            deadline_s=None,
            implicit=False,
        )


async def test_cancel_drops_the_wait_and_its_listener():
    fixture = Fixture()
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="message",
        deadline_s=20.0,
        implicit=False,
    )
    fixture.registry.cancel(agent_id="a")
    assert fixture.timer.cancelled == 1
    with pytest.raises(asyncio.CancelledError):
        await fixture.registry.wait_for_resume(wait=wait)
    # The detached session no longer reaches the cancelled wait.
    fixture.sessions["a"].push_notification(notification=NewInfoNotification(text="late"))


async def test_a_finish_wait_ignores_messages():
    fixture = Fixture()
    wait = fixture.registry.register(
        agent_id="a",
        round_id=1,
        kind="finish",
        deadline_s=None,
        implicit=False,
    )
    fixture.post(sender="b", text="are you there?")
    assert not wait.resumed
    fixture.sessions["a"].push_notification(notification=DoneNotification(reason="over"))
    assert (await fixture.registry.wait_for_resume(wait=wait)).reasons == [WakeReason.LIFECYCLE]
