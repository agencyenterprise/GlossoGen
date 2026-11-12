"""Who a viewer's message reaches, and the rule for addressing one teammate.

With ``Messaging.BROADCAST`` a viewer posts on its team's link and every
teammate reads it. With ``Messaging.ONE_TO_ONE`` a viewer names one teammate
and the message goes to a direct channel only the two of them share. The link
then carries only the world's notices.
"""

from collections.abc import Mapping
from enum import StrEnum

from glossogen.scenarios.spot_the_intersection.seats import Seat


class Messaging(StrEnum):
    """Who a viewer's message reaches."""

    BROADCAST = "broadcast"
    ONE_TO_ONE = "one_to_one"


ONE_TO_ONE_SEND_DESCRIPTION = (
    "Send a message to one teammate. Set 'to' to that teammate's agent id: only that "
    "teammate reads it, attributed to you by name. During the discussion phase, set 'to' to "
    "your team's discussion channel id to post there instead. If new messages from that "
    "teammate arrived since you last read them, the send is held and the new messages are "
    "returned so you can decide what to do. Set force=true to send regardless of new messages."
)

LINK_IS_NOTICES_ONLY = (
    "The link carries only the game's notices. Send each message to one teammate: set 'to' "
    "to that teammate's agent id."
)

DIRECT_MESSAGES_CLOSED_IN_DISCUSSION = (
    "Direct messages are closed during the post-round discussion phase. Use the discussion "
    "channel instead."
)


def direct_channel_refusal(
    seats: Mapping[str, Seat], agent_id: str, recipient_agent_ids: list[str]
) -> str | None:
    """Why ``agent_id`` may not open a direct channel to ``recipient_agent_ids``, or ``None``.

    A direct channel joins the sender and exactly one teammate on the sender's team.
    """
    if len(recipient_agent_ids) != 1:
        return "Address exactly one teammate per message."
    sender = seats.get(agent_id)
    recipient = seats.get(recipient_agent_ids[0])
    if sender is None or recipient is None or recipient.team_id != sender.team_id:
        return f"'{recipient_agent_ids[0]}' is not on your team."
    return None
