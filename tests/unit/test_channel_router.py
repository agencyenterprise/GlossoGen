"""Tests for channel membership and per-agent history visibility.

`member_join_index` is what makes a swapped-in agent see part of a channel
rather than all of it, and it is the whole mechanism behind the protocol-
learnability experiments: if a newcomer can read the messages that defined the
protocol, the run measures nothing. Nothing raises when it is wrong. The
simulation runs to completion and the transcript looks fine, so these
assertions are the only place the window is checked.
"""

from datetime import datetime, timezone

import pytest

from glossogen.channel_router import ChannelRouter, compute_per_channel_join_index
from glossogen.models.channel import Channel
from glossogen.models.message import SimulationMessage
from glossogen.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFromRound,
    ChannelVisibilityFull,
    ChannelVisibilityNone,
)

FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def build_message(*, channel_id: str, text: str, round_number: int) -> SimulationMessage:
    """Build a message addressed to one channel."""
    return SimulationMessage(
        message_id=f"m-{channel_id}-{text}",
        channel_id=channel_id,
        sender_agent_id="agent_a",
        sender_display_name="Agent A",
        text=text,
        timestamp=FIXED_TIME,
        round_number=round_number,
    )


def build_router(*, members: list[str]) -> ChannelRouter:
    """A router with one channel, `link`, shared by `members`."""
    return ChannelRouter(
        channels=[Channel(channel_id="link", name="Link", member_agent_ids=list(members))]
    )


def fill(*, router: ChannelRouter, count: int, round_number: int) -> None:
    """Append `count` messages to `link`, all tagged with one round."""
    for index in range(count):
        router.append_message(
            message=build_message(
                channel_id="link", text=f"r{round_number}-{index}", round_number=round_number
            )
        )


def texts(messages: list[SimulationMessage]) -> list[str]:
    """Reduce messages to their text, which is what the assertions compare."""
    return [message.text for message in messages]


def test_full_visibility_shows_the_channel_from_its_first_message() -> None:
    """`full` is join index 0, whatever the channel already holds."""
    result = compute_per_channel_join_index(
        channel_visibility={"link": ChannelVisibilityFull()},
        current_channel_message_counts={"link": 40},
        channel_message_count_at_round_start={},
    )
    assert result == {"link": 0}


def test_no_visibility_hides_everything_sent_so_far() -> None:
    """`none` is the current message count, so only post-swap messages remain."""
    result = compute_per_channel_join_index(
        channel_visibility={"link": ChannelVisibilityNone()},
        current_channel_message_counts={"link": 40},
        channel_message_count_at_round_start={},
    )
    assert result == {"link": 40}


def test_from_round_windows_to_that_round_start() -> None:
    """`from_round` reads the recorded message count at that round's boundary."""
    result = compute_per_channel_join_index(
        channel_visibility={"link": ChannelVisibilityFromRound(round_floor=16)},
        current_channel_message_counts={"link": 40},
        channel_message_count_at_round_start={16: {"link": 22}},
    )
    assert result == {"link": 22}


def test_from_round_with_no_recorded_snapshot_shows_everything() -> None:
    """An absent snapshot falls back to 0, which is full visibility.

    Worth pinning: this is the direction the fallback goes, and it is the
    permissive one. A swap whose `round_floor` never had its message counts
    recorded shows the newcomer the entire channel.
    """
    result = compute_per_channel_join_index(
        channel_visibility={"link": ChannelVisibilityFromRound(round_floor=16)},
        current_channel_message_counts={"link": 40},
        channel_message_count_at_round_start={},
    )
    assert result == {"link": 0}


def test_unlisted_channels_are_left_out_entirely() -> None:
    """Absent means "do not touch", which is not the same as `full`.

    The caller applies only the keys it is given, so omitting a channel
    preserves whatever visibility the agent already had.
    """
    visibility: dict[str, ChannelVisibility] = {"link": ChannelVisibilityNone()}
    result = compute_per_channel_join_index(
        channel_visibility=visibility,
        current_channel_message_counts={"link": 40, "postmortem": 12},
        channel_message_count_at_round_start={},
    )
    assert result == {"link": 40}


def test_a_member_from_the_start_sees_the_whole_channel() -> None:
    """No join-index entry means no window."""
    router = build_router(members=["agent_a", "agent_b"])
    fill(router=router, count=3, round_number=1)
    assert len(router.get_visible_history(channel_id="link", agent_id="agent_b")) == 3


def test_a_member_added_later_sees_only_what_arrives_after() -> None:
    """The join index is the message count at the moment they were added."""
    router = build_router(members=["agent_a"])
    fill(router=router, count=3, round_number=1)

    router.update_membership(channel_id="link", member_agent_ids=["agent_a", "newcomer"])
    fill(router=router, count=2, round_number=2)

    assert texts(router.get_visible_history(channel_id="link", agent_id="newcomer")) == [
        "r2-0",
        "r2-1",
    ]
    # The incumbent is unaffected by someone else joining.
    assert len(router.get_visible_history(channel_id="link", agent_id="agent_a")) == 5
    # And the channel itself still holds everything, which is what the JSONL
    # and the run viewer show.
    assert router.get_message_count(channel_id="link") == 5


def test_a_removed_member_is_stopped_by_the_membership_check_not_the_window() -> None:
    """Removal drops the join index, so the window reopens to the full channel.

    `get_visible_history` answers "what would this agent see", not "may this
    agent read". `read_channel` calls `validate_membership` first, and that is
    what keeps a removed agent out. Calling `get_visible_history` on its own
    for an agent you have not membership-checked returns the entire history.
    """
    router = build_router(members=["agent_a"])
    fill(router=router, count=3, round_number=1)
    router.update_membership(channel_id="link", member_agent_ids=["agent_a", "newcomer"])
    router.update_membership(channel_id="link", member_agent_ids=["agent_a"])

    assert router.get_channel_member_ids(channel_id="link") == ["agent_a"]
    assert router.validate_membership(agent_id="newcomer", channel_id="link") is False
    assert len(router.get_visible_history(channel_id="link", agent_id="newcomer")) == 3


def test_rejoining_windows_from_the_rejoin_point() -> None:
    """A re-added agent gets a fresh index, not the one it had before."""
    router = build_router(members=["agent_a"])
    fill(router=router, count=3, round_number=1)
    router.update_membership(channel_id="link", member_agent_ids=["agent_a", "newcomer"])
    router.update_membership(channel_id="link", member_agent_ids=["agent_a"])
    fill(router=router, count=2, round_number=2)

    router.update_membership(channel_id="link", member_agent_ids=["agent_a", "newcomer"])
    fill(router=router, count=1, round_number=3)

    assert texts(router.get_visible_history(channel_id="link", agent_id="newcomer")) == ["r3-0"]


def test_replacement_visibility_windows_an_existing_member() -> None:
    """The swap path: same agent id, but from now on it sees less."""
    router = build_router(members=["agent_a", "agent_b"])
    fill(router=router, count=4, round_number=1)

    router.apply_replacement_visibility(agent_id="agent_b", per_channel_join_index={"link": 4})
    fill(router=router, count=1, round_number=2)

    assert texts(router.get_visible_history(channel_id="link", agent_id="agent_b")) == ["r2-0"]
    assert len(router.get_visible_history(channel_id="link", agent_id="agent_a")) == 5


def test_replacement_visibility_ignores_channels_the_agent_is_not_in() -> None:
    """A swap config may name channels this agent never joined."""
    router = ChannelRouter(
        channels=[
            Channel(channel_id="link", name="Link", member_agent_ids=["agent_a"]),
            Channel(channel_id="postmortem", name="Postmortem", member_agent_ids=["agent_b"]),
        ]
    )
    router.apply_replacement_visibility(
        agent_id="agent_a",
        per_channel_join_index={"postmortem": 9, "absent_channel": 3},
    )
    assert router.get_visible_history(channel_id="postmortem", agent_id="agent_b") == []


def test_clearing_history_also_resets_the_windows() -> None:
    """A join index left pointing past the end would hide everything after.

    Wiping the messages without resetting the indices leaves a member offset
    into an empty list, so every later message is invisible to them and their
    `read_channel` returns nothing for the rest of the run.
    """
    router = build_router(members=["agent_a"])
    fill(router=router, count=3, round_number=1)
    router.update_membership(channel_id="link", member_agent_ids=["agent_a", "newcomer"])

    router.clear_history(channel_id="link")
    fill(router=router, count=2, round_number=2)

    assert len(router.get_visible_history(channel_id="link", agent_id="newcomer")) == 2
    assert len(router.get_visible_history(channel_id="link", agent_id="agent_a")) == 2


def test_membership_checks_reject_non_members_and_unknown_channels() -> None:
    """`send_message` and `read_channel` gate on this before doing anything."""
    router = build_router(members=["agent_a"])
    assert router.validate_membership(agent_id="agent_a", channel_id="link") is True
    assert router.validate_membership(agent_id="stranger", channel_id="link") is False
    assert router.validate_membership(agent_id="agent_a", channel_id="absent") is False
    assert router.channel_exists(channel_id="link") is True
    assert router.channel_exists(channel_id="absent") is False


def test_agents_see_the_channels_they_belong_to() -> None:
    """This list becomes the channel roster in the agent's system prompt."""
    router = ChannelRouter(
        channels=[
            Channel(channel_id="link", name="Link", member_agent_ids=["agent_a", "agent_b"]),
            Channel(channel_id="postmortem", name="Postmortem", member_agent_ids=["agent_b"]),
        ]
    )
    assert router.get_agent_channel_ids(agent_id="agent_a") == ["link"]
    assert router.get_agent_channel_ids(agent_id="agent_b") == ["link", "postmortem"]


def test_sending_to_an_unknown_channel_raises() -> None:
    """A typo'd channel id has to fail rather than drop the message."""
    router = build_router(members=["agent_a"])
    with pytest.raises(ValueError):
        router.append_message(
            message=build_message(channel_id="absent", text="hello", round_number=1)
        )


def test_clearing_an_unknown_channel_raises() -> None:
    """Same reasoning: a silent no-op would leave the history in place."""
    router = build_router(members=["agent_a"])
    with pytest.raises(KeyError):
        router.clear_history(channel_id="absent")


def test_restore_loads_prior_history_and_skips_channels_that_are_gone() -> None:
    """Resume replays a source run's messages into a fresh router.

    A scenario can be resumed under knobs that drop a channel (veyru's
    postmortem, for one), so the source's history for it has nowhere to land.
    Skipping is deliberate; raising would make those resumes impossible.
    """
    router = build_router(members=["agent_a"])
    router.restore_messages(
        messages_by_channel={
            "link": [build_message(channel_id="link", text="prior", round_number=1)],
            "postmortem": [build_message(channel_id="postmortem", text="gone", round_number=1)],
        }
    )
    assert texts(router.get_history(channel_id="link")) == ["prior"]
    assert list(router.get_all_messages()) == ["link"]
