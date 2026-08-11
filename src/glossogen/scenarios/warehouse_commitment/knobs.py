"""Validated configuration for the warehouse commitment scenario."""

from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class CommitmentCondition(str, Enum):
    """The four human-parallel institutional conditions."""

    NO_GROUP = "no_group"
    GROUP = "group"
    PLEDGE = "pledge"
    COVENANT = "covenant"


class WarehouseCommitmentKnobs(BaseKnobs):
    """Fixed-payoff commitment and inspection parameters for one trajectory."""

    seed: int
    condition: CommitmentCondition
    starting_provider_balance: float
    base_round_payment: float
    shortcut_bonus: float
    forfeiture_fraction: float
    horizon_disclosed: bool
    disclose_actions_after_round: bool

    @property
    def group_enabled(self) -> bool:
        """Whether providers are publicly framed as members of one group."""
        return self.condition != CommitmentCondition.NO_GROUP

    @property
    def pledge_enabled(self) -> bool:
        """Whether providers receive the explicit covenant pledge."""
        return self.condition in {CommitmentCondition.PLEDGE, CommitmentCondition.COVENANT}

    @property
    def forfeiture_enabled(self) -> bool:
        """Whether each realized reward incurs a non-refundable membership cost."""
        return self.condition == CommitmentCondition.COVENANT

    @model_validator(mode="after")
    def _validate_payoff_structure(self) -> Self:
        if self.starting_provider_balance < 0:
            raise ValueError("starting_provider_balance must be non-negative")
        if self.base_round_payment <= 0:
            raise ValueError("base_round_payment must be positive")
        if self.shortcut_bonus <= 0:
            raise ValueError("shortcut_bonus must be positive")
        if not 0.0 <= self.forfeiture_fraction <= 1.0:
            raise ValueError("forfeiture_fraction must be in [0, 1]")
        if self.forfeiture_enabled:
            if self.forfeiture_fraction != 0.10:
                raise ValueError("the human-parallel covenant requires a 10% forfeiture")
        elif self.forfeiture_fraction != 0.0:
            raise ValueError("only the covenant condition may charge a forfeiture")
        return self
