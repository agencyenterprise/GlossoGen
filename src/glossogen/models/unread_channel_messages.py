"""Messages an agent has not read on one channel, as the runtime hands them to a scenario."""

from typing import NamedTuple

from glossogen.models.message import SimulationMessage


class UnreadChannelMessages(NamedTuple):
    """The messages on ``channel_id`` past the agent's read position, oldest first."""

    channel_id: str
    messages: list[SimulationMessage]
