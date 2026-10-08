"""The channels a primary channel's metrics score.

A primary channel scores its own messages, and, when it includes direct channels,
those of every ``dm:`` channel created during the run whose members all belong to
it. Read from ``channel_created`` events.
"""

from collections.abc import Sequence

from glossogen.models.channel import DIRECT_CHANNEL_PREFIX
from glossogen.models.event import ChannelCreated, SimulationEvent
from glossogen.scenario_protocol import PrimaryChannel, SimulationScenario


def scored_channel_ids(
    primary: PrimaryChannel, scenario: SimulationScenario, events: Sequence[SimulationEvent]
) -> frozenset[str]:
    """``primary``'s channel id, plus the direct channels it includes."""
    channel_ids = {primary.channel_id}
    if not primary.includes_direct_channels:
        return frozenset(channel_ids)
    members = {
        member
        for channel in scenario.get_channels()
        if channel.channel_id == primary.channel_id
        for member in channel.member_agent_ids
    }
    for event in events:
        if (
            isinstance(event, ChannelCreated)
            and event.channel_id.startswith(DIRECT_CHANNEL_PREFIX)
            and set(event.member_agent_ids) <= members
        ):
            channel_ids.add(event.channel_id)
    return frozenset(channel_ids)
