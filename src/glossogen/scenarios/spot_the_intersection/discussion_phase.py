"""What one discussion phase has let each viewer send so far.

A ``DiscussionPhase`` opens with each postmortem. It records each viewer's
partner, when the run gives each pair of teammates a channel, and the
characters each viewer has sent on discussion channels. A send checks and
claims both before it is published, with no await in between, and gives them
back if nothing was sent. So two sends a viewer makes at once cannot both pass
a check that only one of them should pass.
"""

from collections.abc import Mapping
from typing import NamedTuple

from glossogen.models.mcp_responses import SendMessageResult
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
    """What one send took from its sender's allowance, to give back if nothing was sent."""

    agent_id: str
    characters: int
    chose_partner: bool


class DiscussionPhase:
    """One phase's partners and characters sent, per viewer.

    ``partner_channels`` maps each pair channel to its two members, and is empty
    in a run with no pair channels. ``role_names`` names viewers in refusals.
    """

    def __init__(
        self,
        round_number: int,
        character_limit: int,
        partner_channels: Mapping[str, tuple[str, str]],
        role_names: Mapping[str, str],
    ) -> None:
        self.round_number = round_number
        self._character_limit = character_limit
        self._partner_channels = partner_channels
        self._role_names = role_names
        self._partners: dict[str, str] = {}
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
        chose_partner = recipient is not None and agent_id not in self._partners
        if recipient is not None and chose_partner:
            self._partners[agent_id] = recipient
        self._characters_sent[agent_id] = self._characters_sent.get(agent_id, 0) + characters
        return DiscussionClaim(
            agent_id=agent_id, characters=characters, chose_partner=chose_partner
        )

    def release(self, claim: DiscussionClaim) -> None:
        """Give back what ``claim`` took, for a send that posted nothing."""
        self._characters_sent[claim.agent_id] -= claim.characters
        if claim.chose_partner:
            del self._partners[claim.agent_id]

    def _recipient(self, agent_id: str, channel_id: str) -> str | None:
        """The other member of ``agent_id``'s pair channel ``channel_id``, or ``None``.

        ``None`` for any channel that is not a pair channel ``agent_id`` belongs to.
        """
        members = self._partner_channels.get(channel_id)
        if members is None or agent_id not in members:
            return None
        first, second = members
        if agent_id == first:
            return second
        return first
