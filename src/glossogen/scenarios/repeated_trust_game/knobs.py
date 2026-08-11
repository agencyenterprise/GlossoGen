"""Validated configuration for repeated human-parallel trust-game runs."""

from enum import Enum
from typing import Self

from pydantic import model_validator

from glossogen.scenarios.base_knobs import BaseKnobs


class TrustGameCondition(str, Enum):
    """The three conditions in the human comparison."""

    NO_GROUP = "no_group"
    NO_COMMITMENT_GROUP = "no_commitment_group"
    COVENANT = "covenant"


class RepeatedTrustGameKnobs(BaseKnobs):
    """Parameters for one counterbalanced repeated trust-game trajectory."""

    seed: int
    condition: TrustGameCondition
    trustor_endowment: int
    fixed_partner_send: int
    transfer_multiplier: int
    forfeiture_fraction: float
    horizon_disclosed: bool

    @property
    def group_enabled(self) -> bool:
        """Return whether the participant belongs to a named group."""
        return self.condition != TrustGameCondition.NO_GROUP

    @property
    def pledge_enabled(self) -> bool:
        """Return whether the participant receives the covenant pledge."""
        return self.condition == TrustGameCondition.COVENANT

    @property
    def forfeiture_enabled(self) -> bool:
        """Return whether retained game earnings incur the covenant fee."""
        return self.condition == TrustGameCondition.COVENANT

    @property
    def fixed_trustee_endowment(self) -> int:
        """Return the standardized receipt for every reciprocity decision."""
        return self.fixed_partner_send * self.transfer_multiplier

    @model_validator(mode="after")
    def validate_human_parallel_structure(self) -> Self:
        """Require the fixed decision values used by the human study."""
        if self.trustor_endowment != 10:
            raise ValueError("the human-parallel trustor endowment must equal 10")
        if self.fixed_partner_send != 7:
            raise ValueError("the human-parallel fixed partner send must equal 7")
        if self.transfer_multiplier != 3:
            raise ValueError("the human-parallel transfer multiplier must equal 3")
        if self.round_count % 2 != 0:
            raise ValueError("round_count must be even so roles are counterbalanced")
        if self.forfeiture_enabled:
            if self.forfeiture_fraction != 0.10:
                raise ValueError("the covenant condition requires a 10% forfeiture")
        elif self.forfeiture_fraction != 0.0:
            raise ValueError("only the covenant condition may charge a forfeiture")
        return self
