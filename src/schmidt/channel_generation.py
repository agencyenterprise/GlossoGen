"""Generates pairwise DM channels for all agent pairs in a scenario.

Provides ``generate_dm_channels`` which creates one ``Channel`` per unique agent pair
with deterministic IDs and per-agent display names.
"""

import itertools
from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel


class GeneratedDMChannels(NamedTuple):
    """DM channels and their per-agent display name mapping.

    Attributes:
        channels: One ``Channel`` per unique agent pair.
        display_names: Maps ``channel_id -> agent_id -> display name``.
    """

    channels: list[Channel]
    display_names: dict[str, dict[str, str]]


def generate_dm_channels(
    agent_configs: list[AgentConfig],
) -> GeneratedDMChannels:
    """Create a DM channel for each unique pair of agents.

    Channel IDs follow the pattern ``dm_{id1}_{id2}`` with IDs sorted alphabetically
    for determinism. Display names are ``"Private conversation with {role_name}"``
    tailored to each agent's perspective.
    """
    channels: list[Channel] = []
    display_names: dict[str, dict[str, str]] = {}

    agent_map = {ac.agent_id: ac for ac in agent_configs}

    for agent_a, agent_b in itertools.combinations(agent_configs, 2):
        sorted_ids = sorted([agent_a.agent_id, agent_b.agent_id])
        channel_id = f"dm_{sorted_ids[0]}_{sorted_ids[1]}"

        channels.append(
            Channel(
                channel_id=channel_id,
                name=channel_id,
                member_agent_ids=[agent_a.agent_id, agent_b.agent_id],
            )
        )

        display_names[channel_id] = {
            agent_a.agent_id: f"Private conversation with {agent_map[agent_b.agent_id].role_name}",
            agent_b.agent_id: f"Private conversation with {agent_map[agent_a.agent_id].role_name}",
        }

    return GeneratedDMChannels(
        channels=channels,
        display_names=display_names,
    )
