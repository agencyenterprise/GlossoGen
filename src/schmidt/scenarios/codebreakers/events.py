"""Pydantic event types specific to the codebreakers scenario."""

from typing import Literal

from schmidt.models.event_base import EventBase


class TargetSelected(EventBase):
    """Emitted once per round when Alice's target is drawn.

    The target is a member of ``REFERENT_POOL``. Only Alice ever sees it
    inside the simulation; this event lets post-hoc tooling and the
    ``restore_state_from_events`` hook recover the per-round ground truth
    without re-running the seeded sampler.
    """

    event_type: Literal["target_selected"] = "target_selected"
    target: str


class GuessSubmitted(EventBase):
    """Emitted after Friend or Chris submits their single per-round guess.

    ``correct`` is the exact-match verdict against ``TargetSelected.target``
    for the same round. Each agent submits at most once per round; the
    tool rejects second calls.
    """

    event_type: Literal["guess_submitted"] = "guess_submitted"
    agent_id: str
    guess: str
    correct: bool


class RoundOutcomeRecorded(EventBase):
    """Emitted in ``finalize_round`` once the round's outcome is settled.

    ``success`` mirrors the scenario's round-success rule: Friend correct
    AND Chris not correct. The other fields preserve enough state to
    reconstruct per-round metrics post hoc.
    """

    event_type: Literal["round_outcome_recorded"] = "round_outcome_recorded"
    target: str
    friend_guess: str | None
    chris_guess: str | None
    friend_correct: bool
    chris_correct: bool
    success: bool
