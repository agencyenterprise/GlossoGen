"""Channel ID generation for the software procurement scenario.

Provides a factory function that generates channel IDs for an arbitrary
number of seller teams, plus a constant for the cross-team chat channel.
"""

from typing import NamedTuple

SELLER_CROSSCHAT_CHANNEL = "seller_crosschat"


class SellerChannelIds(NamedTuple):
    """Generated channel IDs for N seller teams."""

    buyer_seller_channels: dict[str, str]
    internal_channels: dict[str, str]


def generate_seller_channel_ids(team_ids: list[str]) -> SellerChannelIds:
    """Generate buyer-seller and internal channel IDs for each team."""
    buyer_seller_channels: dict[str, str] = {}
    internal_channels: dict[str, str] = {}

    for team_id in team_ids:
        buyer_seller_channels[team_id] = f"buyer_{team_id}"
        internal_channels[team_id] = f"{team_id}_internal"

    return SellerChannelIds(
        buyer_seller_channels=buyer_seller_channels,
        internal_channels=internal_channels,
    )
