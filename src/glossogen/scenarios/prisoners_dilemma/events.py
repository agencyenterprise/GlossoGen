"""Prisoner's Dilemma scenario-specific events."""

from typing import Literal

from glossogen.models.event_base import EventBase


class DecisionSubmitted(EventBase):
    """Emitted when a player locks in a decision for the current round."""

    event_type: Literal["pd_decision_submitted"] = "pd_decision_submitted"
    agent_id: str
    decision: Literal["cooperate", "defect"]


class RoundPayoffComputed(EventBase):
    """Emitted once a round resolves (both decisions in, or the round ended
    early with a missing decision treated as a defection) and its payoff
    has been computed.
    """

    event_type: Literal["pd_round_payoff_computed"] = "pd_round_payoff_computed"
    player_a_decision: Literal["cooperate", "defect"]
    player_b_decision: Literal["cooperate", "defect"]
    player_a_payoff: float
    player_b_payoff: float
    resolved_early: bool
