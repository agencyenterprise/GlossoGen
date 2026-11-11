"""Where the Veyru run detail anchors the observer swap and the intern's join and takeover.

Each anchor is the first link-channel message at or after the channel event that
marks the moment, so the timeline can scroll to it. The swap is marked by the
history wipe; the intern moments by a membership change carrying their reason.
"""

from datetime import UTC, datetime, timedelta

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import (
    ChannelHistoryCleared,
    ChannelMembershipChanged,
    SimulationEvent,
)
from glossogen.scenario_contract.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    INTERN_JOIN_REASON,
    INTERN_TAKEOVER_REASON,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    OBSERVER_SWAP_REASON,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
)
from glossogen.scenarios.veyru.run_detail_extension import (
    VeyruInternAnchor,
    VeyruRunDetailExtension,
    VeyruRunExtras,
    VeyruSwapPoint,
)

START = datetime(year=2026, month=11, day=10, tzinfo=UTC)


def at(seconds: int) -> datetime:
    """The moment ``seconds`` after the run's start."""
    return START + timedelta(seconds=seconds)


def message(message_id: str, channel_id: str, seconds: int) -> ChannelMessage:
    """A message sent on ``channel_id`` ``seconds`` after the run's start."""
    return ChannelMessage(
        message_id=message_id,
        channel_id=channel_id,
        sender_agent_id="sender",
        sender_display_name="Sender",
        text="text",
        timestamp=at(seconds=seconds),
        round_number=1,
        token_count=1,
    )


def agent(agent_id: str, role_name: str) -> AgentDetail:
    """An agent detail carrying only the identity the anchors read."""
    return AgentDetail(
        agent_id=agent_id,
        role_name=role_name,
        channel_ids=[],
        tool_names=[],
        model="model",
        provider="provider",
        model_settings=AgentModelSettings(),
        system_prompt="",
    )


OBSERVERS = {
    OBSERVER_A_ID: agent(agent_id=OBSERVER_A_ID, role_name=FIELD_OBSERVER_A_ROLE),
    OBSERVER_B_ID: agent(agent_id=OBSERVER_B_ID, role_name=FIELD_OBSERVER_B_ROLE),
}


def extras(
    events: list[SimulationEvent],
    agents_by_id: dict[str, AgentDetail],
    messages: list[ChannelMessage],
) -> VeyruRunExtras:
    """The Veyru run-detail extras built from the given views of a run."""
    return VeyruRunDetailExtension().build_extras(
        events=events, agents_by_id=agents_by_id, messages=messages
    )


def test_the_swap_anchors_on_the_first_link_message_from_the_history_wipe() -> None:
    """Messages before the wipe, and messages off the links, are passed over."""
    events: list[SimulationEvent] = [
        ChannelMembershipChanged(
            channel_id=LINK_A_CHANNEL_ID,
            member_agent_ids=[OBSERVER_B_ID],
            reason=OBSERVER_SWAP_REASON,
            round_number=3,
            timestamp=at(seconds=10),
        ),
        ChannelHistoryCleared(
            channel_id=LINK_A_CHANNEL_ID,
            reason=OBSERVER_SWAP_REASON,
            round_number=3,
            timestamp=at(seconds=20),
        ),
    ]
    messages = [
        message(message_id="before-wipe", channel_id=LINK_A_CHANNEL_ID, seconds=15),
        message(message_id="postmortem", channel_id=POSTMORTEM_A_CHANNEL_ID, seconds=20),
        message(message_id="first-after", channel_id=LINK_B_CHANNEL_ID, seconds=21),
        message(message_id="later", channel_id=LINK_A_CHANNEL_ID, seconds=30),
    ]

    built = extras(events=events, agents_by_id=OBSERVERS, messages=messages)

    assert built.swap_point == VeyruSwapPoint(
        round_number=3,
        target_message_id="first-after",
        swapped_observer_display_names=[FIELD_OBSERVER_A_ROLE, FIELD_OBSERVER_B_ROLE],
    )


def test_a_link_message_at_the_wipes_own_timestamp_is_the_anchor() -> None:
    events: list[SimulationEvent] = [
        ChannelHistoryCleared(
            channel_id=LINK_A_CHANNEL_ID,
            reason=OBSERVER_SWAP_REASON,
            round_number=2,
            timestamp=at(seconds=20),
        ),
    ]
    messages = [message(message_id="same-moment", channel_id=LINK_A_CHANNEL_ID, seconds=20)]

    built = extras(events=events, agents_by_id=OBSERVERS, messages=messages)

    assert built.swap_point is not None
    assert built.swap_point.target_message_id == "same-moment"


def test_the_swap_has_no_anchor_without_a_link_message_after_it() -> None:
    events: list[SimulationEvent] = [
        ChannelHistoryCleared(
            channel_id=LINK_A_CHANNEL_ID,
            reason=OBSERVER_SWAP_REASON,
            round_number=2,
            timestamp=at(seconds=20),
        ),
    ]
    messages = [message(message_id="before", channel_id=LINK_A_CHANNEL_ID, seconds=5)]

    assert extras(events=events, agents_by_id=OBSERVERS, messages=messages).swap_point is None


def test_the_swap_has_no_anchor_without_both_observers() -> None:
    events: list[SimulationEvent] = [
        ChannelHistoryCleared(
            channel_id=LINK_A_CHANNEL_ID,
            reason=OBSERVER_SWAP_REASON,
            round_number=2,
            timestamp=at(seconds=20),
        ),
    ]
    messages = [message(message_id="after", channel_id=LINK_A_CHANNEL_ID, seconds=25)]
    only_a = {OBSERVER_A_ID: OBSERVERS[OBSERVER_A_ID]}

    assert extras(events=events, agents_by_id=only_a, messages=messages).swap_point is None


def test_a_history_wipe_for_another_reason_is_not_the_swap() -> None:
    events: list[SimulationEvent] = [
        ChannelHistoryCleared(
            channel_id=LINK_A_CHANNEL_ID,
            reason="something_else",
            round_number=2,
            timestamp=at(seconds=20),
        ),
    ]
    messages = [message(message_id="after", channel_id=LINK_A_CHANNEL_ID, seconds=25)]

    assert extras(events=events, agents_by_id=OBSERVERS, messages=messages).swap_point is None


def test_the_intern_join_and_takeover_each_anchor_on_their_own_membership_change() -> None:
    """The takeover also moves the postmortem; its first change, on the link, is the anchor."""
    events: list[SimulationEvent] = [
        ChannelMembershipChanged(
            channel_id=LINK_CHANNEL_ID,
            member_agent_ids=["intern"],
            reason=INTERN_JOIN_REASON,
            round_number=2,
            timestamp=at(seconds=10),
        ),
        ChannelMembershipChanged(
            channel_id=LINK_CHANNEL_ID,
            member_agent_ids=["intern"],
            reason=INTERN_TAKEOVER_REASON,
            round_number=4,
            timestamp=at(seconds=40),
        ),
        ChannelMembershipChanged(
            channel_id=POSTMORTEM_CHANNEL_ID,
            member_agent_ids=["intern"],
            reason=INTERN_TAKEOVER_REASON,
            round_number=4,
            timestamp=at(seconds=50),
        ),
    ]
    messages = [
        message(message_id="join-anchor", channel_id=LINK_CHANNEL_ID, seconds=11),
        message(message_id="takeover-postmortem", channel_id=POSTMORTEM_CHANNEL_ID, seconds=41),
        message(message_id="takeover-anchor", channel_id=LINK_CHANNEL_ID, seconds=45),
        message(message_id="after-postmortem-change", channel_id=LINK_CHANNEL_ID, seconds=55),
    ]

    built = extras(events=events, agents_by_id={}, messages=messages)

    assert built.intern_join == VeyruInternAnchor(round_number=2, target_message_id="join-anchor")
    assert built.intern_takeover == VeyruInternAnchor(
        round_number=4, target_message_id="takeover-anchor"
    )
    assert built.swap_point is None


def test_a_run_without_intern_mode_has_no_intern_anchors() -> None:
    messages = [message(message_id="any", channel_id=LINK_CHANNEL_ID, seconds=1)]

    built = extras(events=[], agents_by_id={}, messages=messages)

    assert built.intern_join is None
    assert built.intern_takeover is None
