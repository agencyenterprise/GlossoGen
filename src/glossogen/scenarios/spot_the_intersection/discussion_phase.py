"""What one discussion phase has let each viewer send so far.

A ``DiscussionPhase`` opens with each postmortem. It records each viewer's
partner, when the run gives each pair of teammates a channel, and the
characters each viewer has sent on discussion channels. A send checks and
claims both before it is published, with no await in between, and gives them
back if nothing was sent. So two sends a viewer makes at once cannot both pass
a check that only one of them should pass. A partner stays chosen while any
send to it is in flight or was sent, so a failed send does not undo the choice
another send relies on.
"""

from collections.abc import Mapping
from typing import NamedTuple

from glossogen.models.mcp_responses import SendMessageResult
from glossogen.scenarios.spot_the_intersection.partner_channels import PartnerChannel
from glossogen.scenarios.spot_the_intersection.postmortem_modes import (
    NO_CHARACTER_LIMIT,
    over_limit_refusal,
    second_partner_refusal,
)


class DiscussionSendResult(SendMessageResult):
    """A ``send_message`` result in a discussion phase that has a character limit.

    ``discussion_characters_left`` is how many characters the sender may still
    send in this phase.
    """

    discussion_characters_left: int


class DiscussionClaim(NamedTuple):
    """What one send took from its sender's allowance, to give back if nothing was sent.

    ``to_partner`` is whether the send went on a pair channel, to the sender's partner.
    """

    agent_id: str
    characters: int
    to_partner: bool


class DiscussionPhase:
    """One phase's partners and characters sent, per viewer.

    ``partner_channels`` lists the run's pair channels, and is empty in a run
    with none. ``role_names`` names viewers in refusals.
    """

    def __init__(
        self,
        round_number: int,
        character_limit: int,
        partner_channels: tuple[PartnerChannel, ...],
        role_names: Mapping[str, str],
    ) -> None:
        self.round_number = round_number
        self._character_limit = character_limit
        self._partner_channels = {pair.channel_id: pair for pair in partner_channels}
        self._role_names = role_names
        self._partners: dict[str, str] = {}
        self._sends_to_partner: dict[str, int] = {}
        self._characters_sent: dict[str, int] = {}

    @property
    def has_character_limit(self) -> bool:
        """Whether this phase caps the characters each viewer sends."""
        return self._character_limit != NO_CHARACTER_LIMIT

    def characters_left(self, agent_id: str) -> int:
        """How many characters ``agent_id`` may still send in this phase."""
        return self._character_limit - self._characters_sent.get(agent_id, 0)

    def refusal_for(self, agent_id: str, channel_id: str, characters: int) -> str | None:
        """Why ``agent_id`` may not send ``characters`` on ``channel_id`` now, or ``None``."""
        recipient = self._recipient(agent_id=agent_id, channel_id=channel_id)
        partner = self._partners.get(agent_id)
        if recipient is not None and partner is not None and partner != recipient:
            return second_partner_refusal(partner_role_name=self._role_names[partner])
        if self.has_character_limit and characters > self.characters_left(agent_id=agent_id):
            return over_limit_refusal(
                characters=characters,
                characters_left=self.characters_left(agent_id=agent_id),
                limit=self._character_limit,
            )
        return None

    def claim(self, agent_id: str, channel_id: str, characters: int) -> DiscussionClaim:
        """Take ``characters``, and the partner a pair channel names, for one send.

        Call only after ``refusal_for`` returned ``None`` for the same send.
        """
        recipient = self._recipient(agent_id=agent_id, channel_id=channel_id)
        if recipient is not None:
            self._partners[agent_id] = recipient
            self._sends_to_partner[agent_id] = self._sends_to_partner.get(agent_id, 0) + 1
        self._characters_sent[agent_id] = self._characters_sent.get(agent_id, 0) + characters
        return DiscussionClaim(
            agent_id=agent_id, characters=characters, to_partner=recipient is not None
        )

    def release(self, claim: DiscussionClaim) -> None:
        """Give back what ``claim`` took, for a send that posted nothing.

        The partner is unchosen only when no other send to it is in flight or sent.
        """
        self._characters_sent[claim.agent_id] -= claim.characters
        if not claim.to_partner:
            return
        self._sends_to_partner[claim.agent_id] -= 1
        if self._sends_to_partner[claim.agent_id] == 0:
            del self._sends_to_partner[claim.agent_id]
            del self._partners[claim.agent_id]

    def _recipient(self, agent_id: str, channel_id: str) -> str | None:
        """The other member of ``agent_id``'s pair channel ``channel_id``, or ``None``.

        ``None`` for any channel that is not a pair channel ``agent_id`` belongs to.
        """
        pair = self._partner_channels.get(channel_id)
        if pair is None or not pair.has_member(agent_id=agent_id):
            return None
        return pair.other(agent_id=agent_id)
