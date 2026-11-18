"""Who may post in a discussion phase, and the refusals a viewer reads when it may not.

``PostmortemMode`` sets who posts. With ``whole_team`` every viewer posts on the
team's discussion channel. With ``single_author`` only seat 1 posts there, and
with ``rotating_author`` one seat does, in turn: seat 1 after round 1, seat 2
after round 2, and back to seat 1 after the last seat. The other viewers read.
With ``chosen_partner`` the team has no discussion channel. Each pair of
teammates shares a channel, and a viewer's partner is the first teammate it
messages in that phase. ``postmortem_character_limit`` caps what each viewer
sends in one phase, in any mode.
"""

from enum import StrEnum

NO_CHARACTER_LIMIT = -1


class PostmortemMode(StrEnum):
    """Who may post in a discussion phase, and on which channel."""

    WHOLE_TEAM = "whole_team"
    CHOSEN_PARTNER = "chosen_partner"
    SINGLE_AUTHOR = "single_author"
    ROTATING_AUTHOR = "rotating_author"


def author_index(mode: PostmortemMode, round_number: int, team_size: int) -> int | None:
    """The seat (from 0) that alone posts after ``round_number``, or ``None`` when any may."""
    if mode == PostmortemMode.SINGLE_AUTHOR:
        return 0
    if mode == PostmortemMode.ROTATING_AUTHOR:
        return (round_number - 1) % team_size
    return None


def not_the_author_refusal(author_role_name: str) -> str:
    """What a viewer reads when it posts in a phase another viewer writes."""
    return (
        f"Only {author_role_name} can post on the discussion channel in this discussion "
        "phase. Nothing was sent."
    )


def second_partner_refusal(partner_role_name: str) -> str:
    """What a viewer reads when it messages a teammate other than its partner."""
    return (
        f"Your partner in this discussion phase is {partner_role_name}, the first teammate "
        f"you messaged in it. You can message only {partner_role_name} until the next "
        "discussion phase. Nothing was sent."
    )


def over_limit_refusal(characters: int, characters_left: int, limit: int) -> str:
    """What a viewer reads when a message would take it past the phase's limit."""
    return (
        f"This message has {characters} characters, and you have {characters_left} of your "
        f"{limit} characters left in this discussion phase. Nothing was sent."
    )
