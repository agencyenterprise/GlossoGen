"""Configuration knobs for the Prisoner's Dilemma scenario.

Controls only the payoff matrix; round count, round duration, and every
other timing/runtime knob is inherited unchanged from ``BaseKnobs``. There
is no scenario-specific LLM judge: round outcomes are pure arithmetic over
the two players' submitted decisions, so no ``judge_model`` /
``judge_provider`` fields are declared here.
"""

from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class PrisonersDilemmaKnobs(BaseKnobs):
    """Configuration knobs for the Prisoner's Dilemma scenario.

    ``payoff_temptation`` (T) is the payoff for defecting against a
    cooperating opponent. ``payoff_reward`` (R) is the payoff each player
    gets when both cooperate. ``payoff_punishment`` (P) is the payoff each
    player gets when both defect. ``payoff_sucker`` (S) is the payoff for
    cooperating against a defecting opponent. The classic ordering
    ``T > R > P > S`` and ``2R > T + S`` is enforced so the configured
    values describe a valid Prisoner's Dilemma rather than a different
    game (e.g. Stag Hunt or Chicken).
    """

    payoff_temptation: float
    payoff_reward: float
    payoff_punishment: float
    payoff_sucker: float

    @model_validator(mode="after")
    def _validate_payoff_matrix(self) -> Self:
        temptation = self.payoff_temptation
        reward = self.payoff_reward
        punishment = self.payoff_punishment
        sucker = self.payoff_sucker
        ordering_valid = temptation > reward > punishment > sucker
        if not ordering_valid:
            raise ValueError(
                "Payoff matrix must satisfy T > R > P > S "
                f"(got T={temptation}, R={reward}, P={punishment}, S={sucker})"
            )
        if not 2 * reward > temptation + sucker:
            raise ValueError(
                "Payoff matrix must satisfy 2R > T + S so mutual cooperation "
                f"beats alternating exploitation (got 2R={2 * reward}, T+S={temptation + sucker})"
            )
        return self
