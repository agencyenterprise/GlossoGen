"""Channel router that manages message delivery and history across simulation channels."""

import logging

from glossogen.models.channel import Channel
from glossogen.models.message import SimulationMessage
from glossogen.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFromRound,
    ChannelVisibilityNone,
)

logger = logging.getLogger(__name__)


def compute_per_channel_join_index(
    channel_visibility: dict[str, ChannelVisibility],
    current_channel_message_counts: dict[str, int],
    channel_message_count_at_round_start: dict[int, dict[str, int]],
) -> dict[str, int]:
    """Translate per-channel visibility into concrete ``member_join_index`` values.

    ``ChannelVisibilityFull`` → 0 (visible from the channel's first message).
    ``ChannelVisibilityNone`` → ``current_channel_message_counts[channel_id]``
    (every existing message hidden; new agent only sees post-swap messages).
    ``ChannelVisibilityFromRound(R)`` →
    ``channel_message_count_at_round_start[R].get(channel_id, 0)`` (windowed
    from round R onwards). Channels not present in the visibility dict
    are omitted from the result, signalling to the caller that
    ``member_join_index`` should be left untouched for them.
    """
    result: dict[str, int] = {}
    for channel_id, visibility in channel_visibility.items():
        if isinstance(visibility, ChannelVisibilityNone):
            result[channel_id] = current_channel_message_counts.get(channel_id, 0)
        elif isinstance(visibility, ChannelVisibilityFromRound):
            snapshot = channel_message_count_at_round_start.get(visibility.round_floor, {})
            result[channel_id] = snapshot.get(channel_id, 0)
        else:
            result[channel_id] = 0
    return result


class ChannelRouter:
    """Tracks channels, their membership, and per-channel message histories.

    Each channel is identified by a string channel_id. Messages are stored
    per channel and agents can only interact with channels they belong to.
    """

    def __init__(self, channels: list[Channel]) -> None:
        self._channels = {ch.channel_id: ch for ch in channels}
        self._messages: dict[str, list[SimulationMessage]] = {ch.channel_id: [] for ch in channels}
        logger.debug("ChannelRouter initialized with channels: %s", list(self._channels.keys()))

    def get_history(self, channel_id: str) -> list[SimulationMessage]:
        """Return a copy of the message history for the given channel."""
        return list(self._messages[channel_id])

    def get_visible_history(self, channel_id: str, agent_id: str) -> list[SimulationMessage]:
        """Return the channel history visible to ``agent_id``.

        Members who joined after channel creation only see messages from
        their join index onward; members present from the start see the
        full history.
        """
        channel = self._channels[channel_id]
        full = self._messages[channel_id]
        start = channel.member_join_index.get(agent_id, 0)
        return list(full[start:])

    def get_message_count(self, channel_id: str) -> int:
        """Return the number of messages in the given channel."""
        return len(self._messages[channel_id])

    def get_agent_channel_ids(self, agent_id: str) -> list[str]:
        """Return the channel IDs for all channels the given agent belongs to."""
        return [ch.channel_id for ch in self._channels.values() if agent_id in ch.member_agent_ids]

    def channel_exists(self, channel_id: str) -> bool:
        """Return ``True`` if the channel is registered in the router."""
        return channel_id in self._channels

    def validate_membership(self, agent_id: str, channel_id: str) -> bool:
        """Check whether the agent is a member of the specified channel.

        Returns False if the channel does not exist.
        """
        channel = self._channels.get(channel_id)
        if channel is None:
            logger.debug("Membership check failed: channel %s does not exist", channel_id)
            return False
        is_member = agent_id in channel.member_agent_ids
        if not is_member:
            logger.debug("Agent %s is not a member of channel %s", agent_id, channel_id)
        return is_member

    def append_message(self, message: SimulationMessage) -> None:
        """Append a message to its channel's history.

        Raises ValueError if the message references an unknown channel.
        """
        if message.channel_id not in self._messages:
            raise ValueError(f"Unknown channel: {message.channel_id}")
        self._messages[message.channel_id].append(message)

    def get_channel_member_ids(self, channel_id: str) -> list[str]:
        """Return the member agent IDs for the given channel.

        Raises KeyError if the channel does not exist.
        """
        return self._channels[channel_id].member_agent_ids

    def restore_messages(self, messages_by_channel: dict[str, list[SimulationMessage]]) -> None:
        """Bulk-load messages into channels without logging events.

        Used during resume to pre-populate channel history from a prior run.
        Skips messages for channels that do not exist in the router.
        """
        for channel_id, messages in messages_by_channel.items():
            if channel_id not in self._messages:
                logger.warning("Skipping restore for unknown channel: %s", channel_id)
                continue
            for msg in messages:
                self._messages[channel_id].append(msg)
        total = sum(len(msgs) for msgs in messages_by_channel.values())
        logger.info("Restored %d messages across %d channels", total, len(messages_by_channel))

    def get_all_messages(self) -> dict[str, list[SimulationMessage]]:
        """Return a copy of all message histories, keyed by channel ID."""
        return {k: list(v) for k, v in self._messages.items()}

    def update_membership(self, channel_id: str, member_agent_ids: list[str]) -> None:
        """Replace the member list of an existing channel.

        Newly added members have their join index set to the current message
        count, so subsequent reads for those members return only messages
        arriving after they joined. Removed members have their join-index
        entry discarded. Membership is re-checked on every ``send_message``
        and ``read_channel`` call, so the change takes effect on the next
        tool invocation. Raises KeyError if the channel does not exist.
        """
        channel = self._channels[channel_id]
        old_members = set(channel.member_agent_ids)
        new_members = set(member_agent_ids)
        newly_added = new_members - old_members
        removed = old_members - new_members
        history_len = len(self._messages[channel_id])
        for agent_id in newly_added:
            channel.member_join_index[agent_id] = history_len
        for agent_id in removed:
            channel.member_join_index.pop(agent_id, None)
        channel.member_agent_ids = list(member_agent_ids)
        logger.info("Channel %s membership updated to %s", channel_id, channel.member_agent_ids)

    def apply_replacement_visibility(
        self,
        agent_id: str,
        per_channel_join_index: dict[str, int],
    ) -> None:
        """Set ``member_join_index`` for ``agent_id`` on the listed channels.

        Each ``(channel_id, join_index)`` entry overwrites
        ``channel.member_join_index[agent_id]``. Channels absent from the
        dict are left untouched (preserve existing visibility). Channels
        the agent is not currently a member of are skipped silently.
        Used by the replace-agent resume flow and the in-run agent-swap
        flow to install per-channel windowed visibility for a swapped-in
        agent.
        """
        for channel_id, join_index in per_channel_join_index.items():
            channel = self._channels.get(channel_id)
            if channel is None:
                continue
            if agent_id not in channel.member_agent_ids:
                continue
            channel.member_join_index[agent_id] = join_index

    def clear_history(self, channel_id: str) -> None:
        """Wipe the in-memory message history for a channel.

        Subsequent ``read_channel`` calls return no messages from before the
        wipe. Per-agent join indices are reset to zero so members added
        before the wipe do not remain offset into an empty history. Raises
        KeyError if the channel does not exist.
        """
        if channel_id not in self._messages:
            raise KeyError(f"Unknown channel: {channel_id}")
        cleared_count = len(self._messages[channel_id])
        self._messages[channel_id] = []
        channel = self._channels[channel_id]
        for agent_id in list(channel.member_join_index.keys()):
            channel.member_join_index[agent_id] = 0
        logger.info("Channel %s history cleared (%d messages removed)", channel_id, cleared_count)
