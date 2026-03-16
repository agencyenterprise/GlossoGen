"""Channel router that manages message delivery and history across simulation channels."""

import logging

from schmidt.models.channel import Channel
from schmidt.models.message import SimulationMessage

logger = logging.getLogger(__name__)


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

    def get_agent_channel_ids(self, agent_id: str) -> list[str]:
        """Return the channel IDs for all channels the given agent belongs to."""
        return [ch.channel_id for ch in self._channels.values() if agent_id in ch.member_agent_ids]

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

    def get_all_messages(self) -> dict[str, list[SimulationMessage]]:
        """Return a copy of all message histories, keyed by channel ID."""
        return {k: list(v) for k, v in self._messages.items()}
