"""Pydantic event types specific to the surprise_party scenario."""

from typing import Literal

from schmidt.models.event_base import EventBase


class PartyDecided(EventBase):
    """Emitted once at simulation start with the ground-truth party details.

    The (where, when) pair is fixed for the whole simulation; this event
    lets post-hoc tools and the ``restore_state_from_events`` hook recover
    the secret without re-running the seeded draw.
    """

    event_type: Literal["party_decided"] = "party_decided"
    where: str
    when: str


class FriendIntroduced(EventBase):
    """Emitted at the start of each round with the rotating Friend's name.

    Authoritative source for the round-specific display name shown when
    rendering historical messages; the deterministic shuffle is mirrored
    here so resume/fork flows do not need to re-derive it from the seed.
    """

    event_type: Literal["friend_introduced"] = "friend_introduced"
    friend_name: str


class GuessJudged(EventBase):
    """Emitted after the LLM judge scores one ``submit_guess`` call.

    ``agent_id`` is either the rotating Friend slot or Chris. ``correct``
    is the judge's boolean verdict on whether the freetext guess identifies
    both the place and the time of the surprise party.
    """

    event_type: Literal["guess_judged"] = "guess_judged"
    agent_id: str
    agent_display_name: str
    guess: str
    correct: bool
    judge_explanation: str


class ChrisCaughtParty(EventBase):
    """Emitted the first time Chris's guess is judged correct.

    The scenario's ``is_finished_early()`` hook reads this and terminates
    the simulation as soon as Chris has decoded the secret.
    """

    event_type: Literal["chris_caught_party"] = "chris_caught_party"
    guess: str
